"""Tracing / observability: spans, per-episode accounting, and loop detection.

Contract
--------
* ``Tracer.span(name, **attrs)`` is a context manager. It records a ``Span``
  (name, parent *name*, start/end/duration from the injected clock, status,
  error text, attrs) when the block *finishes*, so spans are stored in finish
  order (children before parents), including when the block raises; the
  exception always propagates. Parent tracking uses ``contextvars`` so each
  thread has an independent stack.
* ``Tracer.episode(episode_id)`` opens an "episode" span and an
  ``EpisodeTrace`` accumulating latency, cost, error messages (explicit via
  ``add_error`` or an escaping exception) and loop alerts.
* ``LoopDetector`` counts occurrences of a hashable key and returns a
  ``LoopAlert`` at every multiple of ``threshold`` (3, 6, 9, ...). The tracer
  keeps one detector for repeated *states* and one for repeated *prompts* per
  episode (agents oscillating between cells revisit the same state).
* Memory is bounded: at most ``max_spans`` spans / ``max_alerts`` alerts are
  stored (extra ones are counted in ``dropped_*``/``alerts_total``; the
  per-name span summary still counts every span).
* ``report()`` returns a JSON-serialisable dict (episodes sorted by id).
"""

from __future__ import annotations

import contextlib
import contextvars
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Hashable, Iterator
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Span:
    name: str
    parent: str | None
    start: float
    end: float
    status: str  # "ok" | "error"
    error: str | None
    episode_id: str | None
    attrs: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class LoopAlert:
    kind: str
    key: Any
    count: int
    episode_id: str | None = None


class LoopDetector:
    def __init__(self, kind: str, threshold: int = 3) -> None:
        if threshold < 1:
            raise ValueError("threshold must be >= 1")
        self.kind = kind
        self.threshold = threshold
        self._counts: dict[Hashable, int] = defaultdict(int)

    def observe(self, key: Hashable) -> LoopAlert | None:
        self._counts[key] += 1
        count = self._counts[key]
        if count % self.threshold == 0:
            return LoopAlert(kind=self.kind, key=key, count=count)
        return None


@dataclass
class EpisodeTrace:
    episode_id: str
    start: float
    end: float | None = None
    cost: float = 0.0
    errors: list[str] = field(default_factory=list)
    alerts: int = 0
    status: str = "ok"
    _state: LoopDetector | None = None
    _prompt: LoopDetector | None = None

    @property
    def latency(self) -> float | None:
        return None if self.end is None else self.end - self.start


class Tracer:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        *,
        loop_threshold: int = 3,
        max_spans: int = 50_000,
        max_alerts: int = 1_000,
        on_alert: Callable[[LoopAlert], None] | None = None,
    ) -> None:
        self._clock = clock
        self._loop_threshold = loop_threshold
        self._max_spans = max_spans
        self._max_alerts = max_alerts
        self._on_alert = on_alert
        self._lock = threading.Lock()
        self._spans: list[Span] = []
        self._dropped = 0
        self._summary: dict[str, dict[str, float]] = {}
        self._episodes: dict[str, EpisodeTrace] = {}
        self._alerts: list[LoopAlert] = []
        self._alerts_total = 0
        self._stack: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
            f"tracer_stack_{id(self)}", default=()
        )
        self._current: contextvars.ContextVar[EpisodeTrace | None] = contextvars.ContextVar(
            f"tracer_episode_{id(self)}", default=None
        )

    @property
    def spans(self) -> list[Span]:
        with self._lock:
            return list(self._spans)

    @contextlib.contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[None]:
        stack = self._stack.get()
        token = self._stack.set((*stack, name))
        start = self._clock()
        status, error = "ok", None
        try:
            yield
        except BaseException as exc:
            status, error = "error", f"{type(exc).__name__}: {exc}"
            raise
        finally:
            end = self._clock()
            self._stack.reset(token)
            ep = self._current.get()
            self._record(
                Span(
                    name=name,
                    parent=stack[-1] if stack else None,
                    start=start,
                    end=end,
                    status=status,
                    error=error,
                    episode_id=ep.episode_id if ep else None,
                    attrs=attrs,
                )
            )

    def _record(self, span: Span) -> None:
        with self._lock:
            agg = self._summary.setdefault(span.name, {"count": 0, "total_s": 0.0, "errors": 0})
            agg["count"] += 1
            agg["total_s"] += span.duration
            agg["errors"] += span.status == "error"
            if len(self._spans) < self._max_spans:
                self._spans.append(span)
            else:
                self._dropped += 1

    @contextlib.contextmanager
    def episode(self, episode_id: str) -> Iterator[EpisodeTrace]:
        ep = EpisodeTrace(
            episode_id=episode_id,
            start=self._clock(),
            _state=LoopDetector("state", self._loop_threshold),
            _prompt=LoopDetector("prompt", self._loop_threshold),
        )
        with self._lock:
            self._episodes[episode_id] = ep
        token = self._current.set(ep)
        try:
            with self.span("episode", episode_id=episode_id):
                yield ep
        except BaseException as exc:
            ep.status = "error"
            ep.errors.append(f"{type(exc).__name__}: {exc}")
            raise
        finally:
            ep.end = self._clock()
            self._current.reset(token)

    def _require_episode(self) -> EpisodeTrace:
        ep = self._current.get()
        if ep is None:
            raise RuntimeError("no active episode; wrap the call in tracer.episode(...)")
        return ep

    def add_cost(self, amount: float) -> None:
        self._require_episode().cost += amount

    def add_error(self, message: str) -> None:
        self._require_episode().errors.append(message)

    def _observe(self, detector_name: str, key: Hashable) -> LoopAlert | None:
        ep = self._require_episode()
        detector = ep._state if detector_name == "state" else ep._prompt
        assert detector is not None
        alert = detector.observe(key)
        if alert is None:
            return None
        alert = LoopAlert(alert.kind, alert.key, alert.count, ep.episode_id)
        ep.alerts += 1
        with self._lock:
            self._alerts_total += 1
            if len(self._alerts) < self._max_alerts:
                self._alerts.append(alert)
        if self._on_alert is not None:
            self._on_alert(alert)
        return alert

    def observe_state(self, key: Hashable) -> LoopAlert | None:
        return self._observe("state", key)

    def observe_prompt(self, key: Hashable) -> LoopAlert | None:
        return self._observe("prompt", key)

    def report(self, *, include_spans: bool = False) -> dict[str, Any]:
        with self._lock:
            out: dict[str, Any] = {
                "episodes": [
                    {
                        "episode_id": e.episode_id,
                        "status": e.status,
                        "latency_s": e.latency,
                        "cost": e.cost,
                        "errors": list(e.errors),
                        "alerts": e.alerts,
                    }
                    for _, e in sorted(self._episodes.items())
                ],
                "span_summary": {k: dict(v) for k, v in sorted(self._summary.items())},
                "dropped_spans": self._dropped,
                "alerts_total": self._alerts_total,
                "alerts": [
                    {"kind": a.kind, "key": list(a.key) if isinstance(a.key, tuple) else a.key,
                     "count": a.count, "episode_id": a.episode_id}
                    for a in self._alerts
                ],
            }
            if include_spans:
                out["spans"] = [
                    {**asdict(s), "duration": s.duration} for s in self._spans
                ]
            return out
