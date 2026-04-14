# agent-notes: { ctx: "shared eval harness: runs a policy across curriculum variations", deps: [src/warehouse_routing/curriculum.py, src/warehouse_routing/sim.py, src/warehouse_routing/grader.py, src/warehouse_routing/tasks.py], state: active, last: "sato@2026-04-14" }
"""Reusable evaluation harness.

Drives a `Policy` through curriculum-selected variations and returns
per-episode scores plus aggregate stats. Used by `inference.py` and the
baseline comparison in `docs/baseline-scores.md`, and shareable with any
future policy.

The harness does not emit [START]/[STEP]/[END] logs — that format is
hackathon-specific and lives in `inference.py`. Here we care about
numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from warehouse_routing.curriculum import Curriculum
from warehouse_routing.grader import grade_variation
from warehouse_routing.models import Action, Move, Observation
from warehouse_routing.sim import GridEnv
from warehouse_routing.tasks import make_variation


class Policy(Protocol):
    def choose(self, obs: Observation) -> Move: ...


@dataclass
class EpisodeResult:
    tier: str
    seed: int
    attempt: int
    steps: int
    score: float
    success: bool


@dataclass
class EvalReport:
    episodes: list[EpisodeResult]

    @property
    def n(self) -> int:
        return len(self.episodes)

    @property
    def mean_score(self) -> float:
        return sum(e.score for e in self.episodes) / self.n if self.n else 0.0

    @property
    def success_rate(self) -> float:
        return sum(1 for e in self.episodes if e.success) / self.n if self.n else 0.0

    def by_tier(self) -> dict[str, float]:
        buckets: dict[str, list[float]] = {}
        for e in self.episodes:
            buckets.setdefault(e.tier, []).append(e.score)
        return {t: sum(xs) / len(xs) for t, xs in buckets.items()}


def evaluate(
    policy: Policy,
    *,
    master_seed: int = 0,
    max_variations: int = 0,
    time_limit_seconds: float | None = None,
) -> EvalReport:
    """Run `policy` through curriculum variations until done or capped.

    Args:
        policy: anything implementing `choose(obs) -> Move`.
        master_seed: curriculum reproducibility seed.
        max_variations: hard cap on episodes (0 = run until curriculum
            terminates via mastery, force-promote, or wall-clock).
        time_limit_seconds: override the curriculum's 19-minute default.
            Pass `None` to disable the cap (useful for testing).
    """
    curriculum = Curriculum(master_seed=master_seed, time_limit_seconds=time_limit_seconds)
    results: list[EpisodeResult] = []

    while not curriculum.is_done():
        if max_variations and len(results) >= max_variations:
            break
        spec, seed, attempt = curriculum.next_variation()
        variation = make_variation(spec, seed=seed, attempt=attempt)
        env = GridEnv(variation.observation)

        while not env.observation.done:
            move = policy.choose(env.observation)
            env.step(Action(move=move))

        final = env.observation
        score = grade_variation(final, variation.optimal_length)
        success = all(final.visited) and final.robot_pos == final.warehouse
        results.append(
            EpisodeResult(
                tier=spec.tier,
                seed=seed,
                attempt=attempt,
                steps=final.steps_taken,
                score=score,
                success=success,
            )
        )
        curriculum.record_score(score)

    return EvalReport(episodes=results)
