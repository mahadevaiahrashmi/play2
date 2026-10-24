"""Episode logging, deterministic replay, idempotent run IDs, dead letters.

Contract
--------
* ``make_run_id(policy, tier, seed)`` is a pure hash of its inputs (length
  prefixed, so delimiters cannot collide): re-running the same triple yields
  the same ID.
* ``EpisodeLog`` stores one JSON object per line (JSONL) per finished
  episode: identity, optimal length, every step (action, robot position,
  visited flags, reward, done, invalid) and the final score. ``append``
  returns ``False`` and writes nothing when the run ID is already present
  (checked against the file at construction time, so dedupe survives
  restarts). Unparseable lines (e.g. a crash mid-write) are skipped and
  counted in ``corrupt_lines``. Thread-safe.
* ``replay_episode(record)`` regenerates the variation from (tier, seed,
  attempt), re-applies the logged actions to a fresh ``GridEnv`` and checks
  that positions, visited flags, rewards, the ``done`` flag and the final score
  all match the log (``ReplayMismatch`` otherwise). It never calls a policy or
  an LLM, so it is fully deterministic.
* ``DeadLetterLog`` records episodes that failed (error text + attempt
  count). ``replay_dead_letters`` re-runs each via a caller-supplied function;
  successes are removed, failures stay with ``attempts`` incremented and the
  new error.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from warehouse_routing.grader import grade_variation
from warehouse_routing.models import Action
from warehouse_routing.reward import compute_reward
from warehouse_routing.sim import GridEnv
from warehouse_routing.tasks import ALL_TASKS, make_variation


class ReplayMismatch(AssertionError):
    """Replaying the logged actions did not reproduce the logged outcome."""


def make_run_id(policy: str, tier: str, seed: int) -> str:
    parts = [policy, tier, str(seed)]
    canonical = "".join(f"{len(p)}:{p};" for p in parts)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class StepRecord:
    action: str
    robot_pos: tuple[int, int]
    visited: list[bool]
    reward: float
    done: bool
    invalid: bool


@dataclass
class EpisodeRecord:
    run_id: str
    policy: str
    tier: str
    seed: int
    attempt: int
    optimal_length: int
    steps: list[StepRecord]
    final_score: float
    success: bool
    cost: float = 0.0
    fallbacks: int = 0
    alerts: int = 0
    llm_calls: int = 0
    extras: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> EpisodeRecord:
        data = json.loads(text)
        data["steps"] = [
            StepRecord(**{**s, "robot_pos": tuple(s["robot_pos"])}) for s in data["steps"]
        ]
        return cls(**data)


class EpisodeLog:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self.corrupt_lines = 0
        self._ids: set[str] = {r.run_id for r in self._read()}

    def _read(self) -> list[EpisodeRecord]:
        if not self.path.exists():
            return []
        out: list[EpisodeRecord] = []
        corrupt = 0
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                out.append(EpisodeRecord.from_json(line))
            except (ValueError, TypeError, KeyError):
                corrupt += 1
        self.corrupt_lines = corrupt
        return out

    def has(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._ids

    def append(self, record: EpisodeRecord) -> bool:
        with self._lock:
            if record.run_id in self._ids:
                return False
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as fh:
                fh.write(record.to_json() + "\n")
                fh.flush()
            self._ids.add(record.run_id)
            return True

    def load(self) -> list[EpisodeRecord]:
        with self._lock:
            return self._read()


def replay_episode(record: EpisodeRecord) -> float:
    spec = next((t for t in ALL_TASKS if t.tier == record.tier), None)
    if spec is None:
        raise ReplayMismatch(f"unknown tier {record.tier!r}")
    variation = make_variation(spec, seed=record.seed, attempt=record.attempt)
    if variation.optimal_length != record.optimal_length:
        raise ReplayMismatch(
            f"optimal length {variation.optimal_length} != logged {record.optimal_length}"
        )
    env = GridEnv(variation.observation)
    for i, logged in enumerate(record.steps):
        result = env.step(Action(move=logged.action))
        o = result.observation
        pos = (o.robot_pos.row, o.robot_pos.col)
        if pos != tuple(logged.robot_pos) or list(o.visited) != list(logged.visited):
            raise ReplayMismatch(f"step {i + 1}: state diverged ({pos} vs {logged.robot_pos})")
        reward = compute_reward(result, variation.optimal_length).value
        if abs(reward - logged.reward) > 1e-9:
            raise ReplayMismatch(f"step {i + 1}: reward {reward} != logged {logged.reward}")
        if result.done != logged.done:
            raise ReplayMismatch(f"step {i + 1}: done flag {result.done} != {logged.done}")
    score = grade_variation(env.observation, variation.optimal_length)
    if abs(score - record.final_score) > 1e-9:
        raise ReplayMismatch(f"score {score} != logged {record.final_score}")
    return score


@dataclass
class DeadLetter:
    run_id: str
    policy: str
    tier: str
    seed: int
    error: str
    attempts: int


class DeadLetterLog:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def append(self, entry: DeadLetter) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as fh:
                fh.write(json.dumps(asdict(entry), sort_keys=True) + "\n")
                fh.flush()

    def load(self) -> list[DeadLetter]:
        with self._lock:
            return self._load()

    def _load(self) -> list[DeadLetter]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            if line.strip():
                try:
                    out.append(DeadLetter(**json.loads(line)))
                except (ValueError, TypeError):
                    continue
        return out

    def _rewrite(self, entries: list[DeadLetter]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text("".join(json.dumps(asdict(e), sort_keys=True) + "\n" for e in entries))
        os.replace(tmp, self.path)

    def replace_all(self, entries: list[DeadLetter]) -> None:
        with self._lock:
            self._rewrite(entries)


def replay_dead_letters(
    dead: DeadLetterLog, run: Callable[[DeadLetter], None]
) -> tuple[list[str], list[DeadLetter]]:
    """Re-run every dead-lettered episode; return (succeeded ids, still-failing entries)."""
    succeeded: list[str] = []
    remaining: list[DeadLetter] = []
    for entry in dead.load():
        try:
            run(entry)
        except Exception as exc:
            entry.attempts += 1
            entry.error = f"{type(exc).__name__}: {exc}"
            remaining.append(entry)
        else:
            succeeded.append(entry.run_id)
    dead.replace_all(remaining)
    return succeeded, remaining
