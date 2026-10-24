"""resilient_llm: timeout without blocking, backoff with injected sleep, circuit breaker."""

import threading
import time

import pytest

from warehouse_routing.resilient_llm import (
    CircuitBreaker,
    CircuitOpenError,
    LLMTimeoutError,
    ResilientLLM,
    RetriesExhaustedError,
    call_with_timeout,
)


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_call_with_timeout_returns_value_and_reraises() -> None:
    assert call_with_timeout(lambda x: x + 1, 1.0, 41) == 42
    with pytest.raises(KeyError):
        call_with_timeout(lambda: {}["k"], 1.0)


def test_hung_call_does_not_block_the_caller() -> None:
    release = threading.Event()
    started = time.monotonic()
    try:
        with pytest.raises(LLMTimeoutError):
            call_with_timeout(release.wait, 0.05)
        elapsed = time.monotonic() - started
        # A `with ThreadPoolExecutor` block would wait for release.wait() (never set) -> hang.
        assert elapsed < 1.0
        workers = [t for t in threading.enumerate() if t.name.startswith("llm-call")]
        assert workers and all(t.daemon for t in workers)
    finally:
        release.set()


def test_backoff_delays_are_exponential_capped_and_jittered() -> None:
    sleeps: list[float] = []
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 5:
            raise ConnectionError("down")
        return "ok"

    llm = ResilientLLM(
        flaky, timeout_s=None, max_retries=5, base_delay=1.0, max_delay=5.0,
        jitter=0.5, rand=lambda: 1.0, sleep=sleeps.append,
    )
    assert llm() == "ok"
    # delay_n = min(max_delay, base*2**n) * (1 + jitter*rand) with rand pinned to 1.0
    assert sleeps == [1.5, 3.0, 6.0, 7.5]
    assert calls["n"] == 5


def test_exhausted_retries_raise_with_attempt_count_and_cause() -> None:
    sleeps: list[float] = []

    def always_fail() -> str:
        raise ConnectionError("boom")

    llm = ResilientLLM(always_fail, timeout_s=None, max_retries=2, sleep=sleeps.append,
                       rand=lambda: 0.0, breaker=None)
    with pytest.raises(RetriesExhaustedError) as exc:
        llm()
    assert exc.value.attempts == 3
    assert isinstance(exc.value.last_error, ConnectionError)
    assert len(sleeps) == 2  # no sleep after the final attempt


def test_non_retryable_errors_propagate_immediately() -> None:
    n = {"c": 0}

    def bad() -> str:
        n["c"] += 1
        raise ValueError("programming error")

    llm = ResilientLLM(bad, timeout_s=None, max_retries=3, sleep=lambda s: None,
                       retry_on=(ConnectionError, LLMTimeoutError))
    with pytest.raises(ValueError):
        llm()
    assert n["c"] == 1


def test_timeout_is_retried() -> None:
    gate = threading.Event()
    n = {"c": 0}

    def slow_then_fast() -> str:
        n["c"] += 1
        if n["c"] == 1:
            gate.wait(5)
        return "fast"

    llm = ResilientLLM(slow_then_fast, timeout_s=0.05, max_retries=1, sleep=lambda s: None)
    try:
        assert llm() == "fast"
    finally:
        gate.set()
    assert n["c"] == 2


def test_circuit_breaker_state_machine() -> None:
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=10.0, clock=clock)
    assert cb.state == "closed"
    cb.record_failure()
    assert cb.state == "closed"
    cb.record_success()  # resets the consecutive-failure count
    cb.record_failure()
    assert cb.state == "closed"
    cb.record_failure()
    assert cb.state == "open"
    assert cb.allow() is False
    clock.t = 9.9
    assert cb.state == "open"
    clock.t = 10.0
    assert cb.state == "half_open"
    assert cb.allow() is True   # the single probe
    assert cb.allow() is False  # others are rejected while the probe is in flight
    cb.record_failure()         # failed probe re-opens and restarts the timer
    assert cb.state == "open"
    clock.t = 19.9
    assert cb.state == "open"
    clock.t = 20.0
    assert cb.allow() is True
    cb.record_success()
    assert cb.state == "closed"
    assert cb.allow() is True


def test_open_circuit_short_circuits_calls_then_recovers() -> None:
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=30.0, clock=clock)
    calls = {"n": 0, "healthy": False}

    def fn() -> str:
        calls["n"] += 1
        if not calls["healthy"]:
            raise ConnectionError("down")
        return "ok"

    llm = ResilientLLM(fn, timeout_s=None, max_retries=0, breaker=cb, sleep=lambda s: None)
    for _ in range(2):
        with pytest.raises(RetriesExhaustedError):
            llm()
    assert cb.state == "open"
    before = calls["n"]
    with pytest.raises(CircuitOpenError):
        llm()
    assert calls["n"] == before  # underlying function not invoked
    calls["healthy"] = True
    clock.t = 31.0
    assert llm() == "ok"
    assert cb.state == "closed"


def test_breaker_opening_mid_retry_stops_retrying() -> None:
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=60.0, clock=FakeClock())
    n = {"c": 0}

    def fn() -> str:
        n["c"] += 1
        raise ConnectionError("x")

    llm = ResilientLLM(fn, timeout_s=None, max_retries=10, breaker=cb, sleep=lambda s: None)
    with pytest.raises(CircuitOpenError):
        llm()
    assert n["c"] == 2


def test_non_retryable_error_in_half_open_releases_the_probe() -> None:
    clock = FakeClock()
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=5.0, clock=clock)
    cb.record_failure()
    clock.t = 5.0
    assert cb.state == "half_open"

    def bug() -> str:
        raise ValueError("not a service failure")

    llm = ResilientLLM(bug, timeout_s=None, breaker=cb, retry_on=(ConnectionError,))
    with pytest.raises(ValueError):
        llm()
    # Without cancel() the breaker would stay half-open with a probe "in flight" forever.
    assert cb.allow() is True
