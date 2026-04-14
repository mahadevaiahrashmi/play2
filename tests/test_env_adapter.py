# agent-notes: { ctx: "OpenEnv Environment wrapper: reset/step/state contract", deps: [src/warehouse_routing/env.py], state: active, last: "sato@2026-04-14" }
"""Smoke coverage for the OpenEnv adapter.

Drives reset/step directly (no HTTP) to confirm the wrapper bridges
curriculum + sim + reward + grader without drifting from the pure
`GridEnv` contract.
"""

from warehouse_routing import env as env_mod
from warehouse_routing.env import WarehouseRoutingEnvironment, reset_session
from warehouse_routing.models import Action


def test_reset_returns_easy_tier_fresh_episode() -> None:
    reset_session(master_seed=0)
    env = WarehouseRoutingEnvironment()
    obs = env.reset()
    assert obs.tier == "easy"
    assert obs.steps_taken == 0
    assert obs.done is False
    assert obs.reward == 0.0
    assert env.state.step_count == 0


def test_step_advances_state_and_returns_shaped_reward() -> None:
    reset_session(master_seed=0)
    env = WarehouseRoutingEnvironment()
    env.reset()
    obs = env.step(Action(move="E"))
    assert obs.steps_taken == 1
    assert env.state.step_count == 1
    assert obs.reward is not None


def test_reset_after_terminal_advances_curriculum_state() -> None:
    reset_session(master_seed=0)
    env = WarehouseRoutingEnvironment()
    env.reset()
    # Exhaust the budget by hammering an invalid move
    while not env.step(Action(move="N")).done:
        pass
    assert env_mod._SESSION.last_score == 0.0  # budget exhaustion -> 0
    env.reset()
    # Streak was broken, still on easy attempt 2
    assert env_mod._SESSION.curriculum.state.tier_index == 0
    assert env_mod._SESSION.curriculum.state.attempt_in_tier == 2
