# agent-notes: { ctx: "reward shaping: progress/penalty/terminal components", deps: [src/warehouse_routing/reward.py, src/warehouse_routing/sim.py], state: active, last: "sato@2026-04-14" }
import pytest

from warehouse_routing.models import Cell, Observation
from warehouse_routing.reward import (
    BUDGET_EXHAUST_PENALTY,
    INVALID_PENALTY,
    SKU_VISIT_BONUS,
    TIME_PENALTY,
    compute_reward,
)
from warehouse_routing.sim import StepResult


def _obs(**k) -> Observation:  # type: ignore[no-untyped-def]
    defaults = dict(
        grid_rows=4,
        grid_cols=4,
        warehouse=Cell(row=0, col=0),
        sku_locations=[Cell(row=0, col=1)],
        robot_pos=Cell(row=0, col=0),
        visited=[False],
        steps_taken=1,
        step_budget=64,
        tier="easy",
        attempt=1,
        variation_seed=0,
        done=False,
    )
    defaults.update(k)
    return Observation(**defaults)  # type: ignore[arg-type]


def test_valid_move_time_penalty_only() -> None:
    r = compute_reward(
        StepResult(_obs(), invalid=False, newly_visited_index=-1, at_warehouse=False, done=False),
        optimal_length=4,
    )
    assert r.progress == 0.0
    assert r.penalty == TIME_PENALTY
    assert r.terminal == 0.0
    assert r.value == TIME_PENALTY


def test_invalid_move_stacks_penalty() -> None:
    r = compute_reward(
        StepResult(_obs(), invalid=True, newly_visited_index=-1, at_warehouse=False, done=False),
        optimal_length=4,
    )
    assert r.penalty == TIME_PENALTY + INVALID_PENALTY


def test_newly_visited_adds_bonus() -> None:
    r = compute_reward(
        StepResult(_obs(visited=[True]), invalid=False, newly_visited_index=0, at_warehouse=False, done=False),
        optimal_length=4,
    )
    assert r.progress == SKU_VISIT_BONUS


def test_terminal_success_is_optimal_over_agent() -> None:
    r = compute_reward(
        StepResult(
            _obs(visited=[True], robot_pos=Cell(row=0, col=0), steps_taken=4, done=True),
            invalid=False,
            newly_visited_index=-1,
            at_warehouse=True,
            done=True,
        ),
        optimal_length=4,
    )
    assert r.terminal == 1.0


def test_terminal_failure_penalty() -> None:
    # Done but not all visited -> explicit budget-exhaustion penalty
    r = compute_reward(
        StepResult(
            _obs(visited=[False], steps_taken=64, done=True),
            invalid=False,
            newly_visited_index=-1,
            at_warehouse=True,
            done=True,
        ),
        optimal_length=4,
    )
    assert r.terminal == BUDGET_EXHAUST_PENALTY


def test_reward_is_bounded_scalar() -> None:
    # Non-terminal step reward is bounded by components — sanity check signs
    r = compute_reward(
        StepResult(_obs(), invalid=True, newly_visited_index=0, at_warehouse=False, done=False),
        optimal_length=4,
    )
    # progress + penalty + 0 terminal
    assert r.value == pytest.approx(SKU_VISIT_BONUS + TIME_PENALTY + INVALID_PENALTY)
