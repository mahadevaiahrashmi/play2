# agent-notes: { ctx: "easy task variation generator + end-to-end smoke", deps: [src/warehouse_routing/tasks.py, src/warehouse_routing/sim.py, src/warehouse_routing/grader.py], state: active, last: "sato@2026-04-14" }
from warehouse_routing.grader import grade_variation
from warehouse_routing.models import Action
from warehouse_routing.sim import GridEnv
from warehouse_routing.tasks import EASY, make_variation


def test_easy_spec_shape() -> None:
    assert EASY.tier == "easy"
    assert EASY.grid_rows == 8 and EASY.grid_cols == 8
    assert EASY.n_skus == 3


def test_variation_is_deterministic() -> None:
    v1 = make_variation(EASY, seed=42)
    v2 = make_variation(EASY, seed=42)
    assert v1.observation == v2.observation
    assert v1.optimal_length == v2.optimal_length


def test_different_seeds_differ() -> None:
    v1 = make_variation(EASY, seed=1)
    v2 = make_variation(EASY, seed=2)
    assert v1.observation.sku_locations != v2.observation.sku_locations


def test_variation_starts_at_warehouse_unvisited() -> None:
    v = make_variation(EASY, seed=7)
    assert v.observation.robot_pos == v.observation.warehouse
    assert v.observation.visited == [False, False, False]
    assert v.observation.steps_taken == 0
    assert not v.observation.done


def test_easy_optimal_length_nontrivial() -> None:
    v = make_variation(EASY, seed=7)
    assert v.optimal_length > 0


def _walk_to(env: GridEnv, target_row: int, target_col: int) -> None:
    while env.observation.robot_pos.row != target_row:
        env.step(Action(move="S" if env.observation.robot_pos.row < target_row else "N"))
    while env.observation.robot_pos.col != target_col:
        env.step(Action(move="E" if env.observation.robot_pos.col < target_col else "W"))


def test_end_to_end_manhattan_tour_in_spec_order() -> None:
    """Manually tour SKUs in spec order; grader returns a bounded score."""
    v = make_variation(EASY, seed=13)
    env = GridEnv(v.observation)
    for sku in v.observation.sku_locations:
        _walk_to(env, sku.row, sku.col)
    _walk_to(env, v.observation.warehouse.row, v.observation.warehouse.col)
    final = env.observation
    assert final.done
    assert all(final.visited)
    score = grade_variation(final, v.optimal_length)
    assert 0.0 < score <= 1.0
