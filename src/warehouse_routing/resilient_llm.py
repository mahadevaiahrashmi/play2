"""Resilience wrapper for any LLM-call function: timeout, backoff, circuit breaker.

Contract
--------
* ``call_with_timeout(fn, timeout_s, *a, **kw)`` runs ``fn`` in a *daemon*
  thread and waits on an Event. On timeout it raises ``LLMTimeoutError``
  immediately and abandons the thread. We deliberately do NOT use
  ``with ThreadPoolExecutor(...)``: its ``__exit__`` calls
  ``shutdown(wait=True)`` and would block the caller until the hung call
  returns, defeating the timeout. Limitation: Python cannot kill a thread, so
  an abandoned call keeps running (and may still be billed) in the background.
* ``CircuitBreaker`` is closed -> open (after N consecutive failures) ->
  half-open (after ``reset_timeout`` on the injected clock, allowing exactly one
  probe) -> closed on probe success / open again on probe failure. Thread-safe.
* ``ResilientLLM`` retries ``retry_on`` errors up to ``max_retries`` extra
  times with delay ``min(max_delay, base_delay * 2**n) * (1 + jitter * rand())``
  using the injected ``sleep`` and ``rand`` (no real sleeping in tests), never
  sleeps after the last attempt, and honours the breaker: an open circuit
  raises ``CircuitOpenError`` without calling the function, also mid-retry.
  Errors outside ``retry_on`` propagate immediately and do not trip the breaker.
"""

from __future__ import annotations

import itertools
import random
import threading
import time
from collections.abc import Callable
from typing import Any

_thread_ids = itertools.count(1)


class LLMTimeoutError(TimeoutError):
    """A call exceeded its per-call timeout."""


class CircuitOpenError(RuntimeError):
    """The circuit breaker is open; the call was not attempted."""


class RetriesExhaustedError(RuntimeError):
    def __init__(self, attempts: int, last_error: BaseException) -> None:
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(f"failed after {attempts} attempts: {last_error!r}")


def call_with_timeout[T](
    fn: Callable[..., T], timeout_s: float | None, *args: Any, **kwargs: Any
) -> T:
    if timeout_s is None:
        return fn(*args, **kwargs)
    done = threading.Event()
    box: dict[str, Any] = {}

    def runner() -> None:
        try:
            box["value"] = fn(*args, **kwargs)
        except BaseException as exc:  # delivered to the caller thread
            box["error"] = exc
        finally:
            done.set()

    worker = threading.Thread(target=runner, name=f"llm-call-{next(_thread_ids)}", daemon=True)
    worker.start()
    if not done.wait(timeout_s):
        raise LLMTimeoutError(f"LLM call exceeded {timeout_s}s")
    if "error" in box:
        raise box["error"]
    return box["value"]  # type: ignore[no-any-return]


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._clock = clock
        self._lock = threading.Lock()
        self._state = "closed"
        self._failures = 0
        self._opened_at = 0.0
        self._probe_in_flight = False

    def _refresh(self) -> None:
        if self._state == "open" and self._clock() - self._opened_at >= self.reset_timeout:
            self._state = "half_open"
            self._probe_in_flight = False

    @property
    def state(self) -> str:
        with self._lock:
            self._refresh()
            return self._state

    def allow(self) -> bool:
        with self._lock:
            self._refresh()
            if self._state == "closed":
                return True
            if self._state == "half_open" and not self._probe_in_flight:
                self._probe_in_flight = True
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._state = "closed"
            self._failures = 0
            self._probe_in_flight = False

    def record_failure(self) -> None:
        with self._lock:
            self._probe_in_flight = False
            if self._state == "half_open":
                self._open()
                return
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._open()

    def cancel(self) -> None:
        """Release a half-open probe whose outcome says nothing about service health."""
        with self._lock:
            self._probe_in_flight = False

    def _open(self) -> None:
        self._state = "open"
        self._opened_at = self._clock()


class ResilientLLM[T]:
    def __init__(
        self,
        fn: Callable[..., T],
        *,
        timeout_s: float | None = 30.0,
        max_retries: int = 3,
        base_delay: float = 0.5,
        max_delay: float = 8.0,
        jitter: float = 0.25,
        rand: Callable[[], float] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        breaker: CircuitBreaker | None = None,
        retry_on: tuple[type[BaseException], ...] = (Exception,),
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self._fn = fn
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self._rand: Callable[[], float] = rand if rand is not None else random.Random(0).random
        self._sleep = sleep
        self.breaker = breaker
        self._retry_on = retry_on

    def delay_for(self, retry_index: int) -> float:
        base = min(self.max_delay, self.base_delay * float(2**retry_index))
        return base * (1 + self.jitter * self._rand())

    def __call__(self, *args: Any, **kwargs: Any) -> T:
        last_attempt = self.max_retries
        for attempt in range(self.max_retries + 1):
            if self.breaker is not None and not self.breaker.allow():
                raise CircuitOpenError("circuit breaker is open")
            try:
                result = call_with_timeout(self._fn, self.timeout_s, *args, **kwargs)
            except CircuitOpenError:
                raise
            except self._retry_on as exc:
                if self.breaker is not None:
                    self.breaker.record_failure()
                if attempt == last_attempt:
                    raise RetriesExhaustedError(attempt + 1, exc) from exc
                if self.breaker is not None and self.breaker.state == "open":
                    raise CircuitOpenError("circuit breaker opened during retries") from exc
                self._sleep(self.delay_for(attempt))
            except BaseException:
                if self.breaker is not None:
                    self.breaker.cancel()
                raise
            else:
                if self.breaker is not None:
                    self.breaker.record_success()
                return result
        raise AssertionError("unreachable")  # pragma: no cover
