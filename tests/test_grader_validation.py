# agent-notes: { ctx: "cross-task grader validation: bounds + monotonicity", deps: [src/warehouse_routing/tasks.py, src/warehouse_routing/grader.py, src/warehouse_routing/sim.py], state: active, last: "sato@2026-04-14" }
"""Grader validation across all tiers.

Guards the contract with the hackathon validator: scores must live in
[0, 1], failures score 0, and shorter completed tours score at least as
high as longer ones on the same task.
"""

import random

from warehouse_routing.grader import grade_variation
from warehouse_routing.models import Action, Cell, Move, Observation
from warehouse_routing.sim import GridEnv
from warehouse_routing.tasks import ALL_TASKS, EASY, make_variation

MOVES: tuple[Move, ...] = ("N", "S", "E", "W")
RANDOM_SEEDS = (1, 7, 42, 101, 255)


def _run_random(env: GridEnv, rng: random.Random) -> Observation:
    while not env.observation.done:
        env.step(Action(move=rng.choice(MOVES)))
    return env.observation


def _walk_to(env: GridEnv, target: Cell) -> None:
    while not env.observation.done and env.observation.robot_pos != target:
        pos = env.observation.robot_pos
        if pos.row != target.row:
            env.step(Action(move="S" if pos.row < target.row else "N"))
        else:
            env.step(Action(move="E" if pos.col < target.col else "W"))


def test_scores_bounded_on_random_trajectories_all_tiers() -> None:
    for spec in ALL_TASKS:
        for seed in RANDOM_SEEDS:
            variation = make_variation(spec, seed=seed)
            env = GridEnv(variation.observation)
            final = _run_random(env, random.Random(seed))
            score = grade_variation(final, variation.optimal_length)
            assert 0.0 <= score <= 1.0, f"{spec.tier}/{seed} score={score}"


def test_incomplete_tour_is_zero() -> None:
    variation = make_variation(EASY, seed=13)
    env = GridEnv(variation.observation)
    # Single step then force done via budget exhaustion by exceeding budget
    # using a rigged trajectory is overkill; simulate by taking one move and
    # then asserting grader rejects the non-terminated observation.
    env.step(Action(move="E"))
    score = grade_variation(env.observation, variation.optimal_length)
    assert score == 0.0  # not done -> 0


def test_monotonic_in_agent_length_same_task() -> None:
    variation = make_variation(EASY, seed=13)
    base = variation.observation

    short = base.model_copy(
        update={
            "visited": [True] * len(base.sku_locations),
            "robot_pos": base.warehouse,
            "steps_taken": variation.optimal_length,
            "done": True,
        }
    )
    long = base.model_copy(
        update={
            "visited": [True] * len(base.sku_locations),
            "robot_pos": base.warehouse,
            "steps_taken": variation.optimal_length * 2,
            "done": True,
        }
    )
    short_score = grade_variation(short, variation.optimal_length)
    long_score = grade_variation(long, variation.optimal_length)
    assert short_score >= long_score
    assert short_score == 1.0
    assert long_score == 0.5


def test_task_enumeration_covers_three_tiers() -> None:
    tiers = [spec.tier for spec in ALL_TASKS]
    assert tiers == ["easy", "medium", "hard"]


def test_every_tier_produces_valid_optimal_length() -> None:
    for spec in ALL_TASKS:
        for seed in RANDOM_SEEDS:
            variation = make_variation(spec, seed=seed)
            assert variation.optimal_length > 0
            assert variation.optimal_length < 10_000
