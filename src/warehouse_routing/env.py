# agent-notes: { ctx: "OpenEnv Environment adapter: curriculum-driven reset/step", deps: [src/warehouse_routing/sim.py, src/warehouse_routing/reward.py, src/warehouse_routing/curriculum.py, src/warehouse_routing/tasks.py, src/warehouse_routing/grader.py], state: active, last: "sato@2026-04-14" }
"""OpenEnv Environment wrapper for warehouse routing.

The framework's HTTP shim calls the env factory on every request, so
all cross-call state (curriculum, active grid, current variation) lives
in a module-level `_Session` singleton. The `Environment` subclass is a
thin view over it.
"""

from dataclasses import dataclass, field
from uuid import uuid4

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

from warehouse_routing.curriculum import Curriculum
from warehouse_routing.grader import grade_variation
from warehouse_routing.models import Action, Observation
from warehouse_routing.reward import compute_reward
from warehouse_routing.sim import GridEnv
from warehouse_routing.tasks import Variation, make_variation


@dataclass
class _Session:
    curriculum: Curriculum = field(default_factory=Curriculum)
    grid: GridEnv | None = None
    variation: Variation | None = None
    last_score: float | None = None
    state: State = field(default_factory=lambda: State(episode_id=str(uuid4()), step_count=0))


_SESSION: _Session = _Session()


def reset_session(master_seed: int = 0) -> None:
    """Test hook: rebuild the singleton with a fresh curriculum."""
    global _SESSION
    _SESSION = _Session(curriculum=Curriculum(master_seed=master_seed))


class WarehouseRoutingEnvironment(Environment):
    """Curriculum-driven OpenEnv environment for AMR routing."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = False

    def reset(self) -> Observation:
        s = _SESSION

        if s.last_score is not None:
            if s.curriculum.is_done():
                s.curriculum.reset()
            s.curriculum.record_score(s.last_score)
            s.last_score = None
        if s.curriculum.is_done():
            s.curriculum.reset()

        spec, seed, attempt = s.curriculum.next_variation()
        s.variation = make_variation(spec, seed=seed, attempt=attempt)
        s.grid = GridEnv(s.variation.observation)
        s.state = State(episode_id=str(uuid4()), step_count=0)

        return s.variation.observation.model_copy(
            update={"reward": 0.0, "metadata": _meta(score=None)}
        )

    def step(self, action: Action) -> Observation:  # type: ignore[override]
        s = _SESSION
        if s.grid is None or s.variation is None:
            raise RuntimeError("step() called before reset()")

        result = s.grid.step(action)
        reward = compute_reward(result, s.variation.optimal_length)
        s.state.step_count += 1

        score: float | None = None
        if result.done:
            score = grade_variation(result.observation, s.variation.optimal_length)
            s.last_score = score

        return result.observation.model_copy(
            update={
                "reward": reward.value,
                "metadata": _meta(
                    score=score,
                    progress=reward.progress,
                    penalty=reward.penalty,
                    terminal=reward.terminal,
                    invalid=result.invalid,
                ),
            }
        )

    @property
    def state(self) -> State:
        return _SESSION.state


def _meta(**fields: object) -> dict[str, object]:
    s = _SESSION
    meta: dict[str, object] = {k: v for k, v in fields.items() if v is not None}
    if s.variation is not None:
        meta["optimal_length"] = s.variation.optimal_length
    meta["curriculum"] = {
        "tier_index": s.curriculum.state.tier_index,
        "attempt_in_tier": s.curriculum.state.attempt_in_tier,
        "streak": s.curriculum.state.streak,
        "mastered": dict(s.curriculum.state.mastered),
        "done": s.curriculum.is_done(),
    }
    return meta
