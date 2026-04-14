# agent-notes: { ctx: "adaptive curriculum: 3-in-a-row >=0.9, max 20 attempts, force-promote", deps: [src/warehouse_routing/tasks.py, src/warehouse_routing/models.py], state: active, last: "sato@2026-04-14" }
"""Adaptive curriculum state machine.

Walks the agent through Easy -> Medium -> Hard. A tier is "mastered"
after 3 consecutive variations score >= MASTERY_SCORE; force-promoted
after MAX_ATTEMPTS attempts without mastery.

Seed derivation is deterministic in (master_seed, tier_index,
attempt_in_tier), so runs are reproducible.
"""

from dataclasses import dataclass, field

from warehouse_routing.models import Tier
from warehouse_routing.tasks import ALL_TASKS, TaskSpec

MASTERY_SCORE: float = 0.9
MASTERY_STREAK: int = 3
MAX_ATTEMPTS: int = 20
_TIER_STRIDE: int = 1009  # prime to keep seeds across tiers far apart


@dataclass
class AttemptRecord:
    tier: Tier
    attempt: int
    seed: int
    score: float


@dataclass
class CurriculumState:
    tier_index: int = 0
    attempt_in_tier: int = 1
    streak: int = 0
    mastered: dict[Tier, bool] = field(default_factory=dict)
    history: list[AttemptRecord] = field(default_factory=list)
    done: bool = False


class Curriculum:
    """Stateful adaptive curriculum driver."""

    def __init__(
        self,
        tasks: tuple[TaskSpec, ...] = ALL_TASKS,
        master_seed: int = 0,
    ) -> None:
        self.tasks = tasks
        self.master_seed = master_seed
        self.state = CurriculumState()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def is_done(self) -> bool:
        return self.state.done

    def current_spec(self) -> TaskSpec:
        if self.state.done:
            raise RuntimeError("curriculum already done; call reset()")
        return self.tasks[self.state.tier_index]

    def current_seed(self) -> int:
        return (
            self.master_seed
            + self.state.tier_index * _TIER_STRIDE
            + self.state.attempt_in_tier
        )

    def next_variation(self) -> tuple[TaskSpec, int, int]:
        """Return (TaskSpec, seed, attempt) for the variation about to run."""
        return self.current_spec(), self.current_seed(), self.state.attempt_in_tier

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def record_score(self, score: float) -> None:
        if self.state.done:
            raise RuntimeError("curriculum already done; call reset()")

        spec = self.current_spec()
        self.state.history.append(
            AttemptRecord(
                tier=spec.tier,
                attempt=self.state.attempt_in_tier,
                seed=self.current_seed(),
                score=score,
            )
        )

        if score >= MASTERY_SCORE:
            self.state.streak += 1
        else:
            self.state.streak = 0

        if self.state.streak >= MASTERY_STREAK:
            self.state.mastered[spec.tier] = True
            self._promote()
            return

        if self.state.attempt_in_tier >= MAX_ATTEMPTS:
            self.state.mastered.setdefault(spec.tier, False)
            self._promote()
            return

        self.state.attempt_in_tier += 1

    def reset(self) -> None:
        self.state = CurriculumState()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _promote(self) -> None:
        self.state.tier_index += 1
        self.state.streak = 0
        self.state.attempt_in_tier = 1
        if self.state.tier_index >= len(self.tasks):
            self.state.done = True

    def summary(self) -> dict[str, object]:
        return {
            "done": self.state.done,
            "mastered": dict(self.state.mastered),
            "n_attempts": len(self.state.history),
            "history": [
                {"tier": r.tier, "attempt": r.attempt, "seed": r.seed, "score": r.score}
                for r in self.state.history
            ],
        }
