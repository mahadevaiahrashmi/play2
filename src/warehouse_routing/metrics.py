"""Process-wide episode counters for the HTTP server (thread-safe).

Contract: ``episode_started`` / ``episode_finished(score)`` /
``episode_abandoned`` / ``step`` update counters under one lock;
``snapshot()`` returns a consistent JSON-ready dict. ``active_episodes`` is
``started - completed - abandoned``; ``mean_score`` is over completed
episodes (``None`` if there are none).
"""

from __future__ import annotations

import threading
from typing import Any


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._started = 0
            self._completed = 0
            self._abandoned = 0
            self._steps = 0
            self._score_sum = 0.0

    def episode_started(self) -> None:
        with self._lock:
            self._started += 1

    def episode_finished(self, score: float) -> None:
        with self._lock:
            self._completed += 1
            self._score_sum += score

    def episode_abandoned(self) -> None:
        with self._lock:
            self._abandoned += 1

    def step(self) -> None:
        with self._lock:
            self._steps += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "episodes_started": self._started,
                "episodes_completed": self._completed,
                "episodes_abandoned": self._abandoned,
                "active_episodes": self._started - self._completed - self._abandoned,
                "mean_score": self._score_sum / self._completed if self._completed else None,
                "steps_total": self._steps,
            }


METRICS = Metrics()
