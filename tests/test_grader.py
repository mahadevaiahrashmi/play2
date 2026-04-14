# agent-notes: { ctx: "grader: success/failure paths and ratio bounds", deps: [src/warehouse_routing/grader.py], state: active, last: "sato@2026-04-14" }
from warehouse_routing.grader import grade_variation
from warehouse_routing.models import Cell, Observation


def _final(
    *,
    visited: list[bool],
    pos: tuple[int, int],
    steps: int,
    done: bool,
) -> Observation:
    return Observation(
        grid_rows=4,
        grid_cols=4,
        warehouse=Cell(row=0, col=0),
        sku_locations=[Cell(row=0, col=1), Cell(row=0, col=2)],
        robot_pos=Cell(row=pos[0], col=pos[1]),
        visited=visited,
        steps_taken=steps,
        step_budget=64,
        tier="easy",
        attempt=1,
        variation_seed=0,
        done=done,
    )


def test_not_done_is_zero() -> None:
    obs = _final(visited=[True, True], pos=(0, 0), steps=5, done=False)
    assert grade_variation(obs, optimal_length=4) == 0.0


def test_unvisited_sku_is_zero() -> None:
    obs = _final(visited=[True, False], pos=(0, 0), steps=5, done=True)
    assert grade_variation(obs, optimal_length=4) == 0.0


def test_not_at_warehouse_is_zero() -> None:
    obs = _final(visited=[True, True], pos=(0, 2), steps=4, done=True)
    assert grade_variation(obs, optimal_length=4) == 0.0


def test_perfect_tour_is_one() -> None:
    obs = _final(visited=[True, True], pos=(0, 0), steps=4, done=True)
    assert grade_variation(obs, optimal_length=4) == 1.0


def test_longer_tour_is_ratio() -> None:
    obs = _final(visited=[True, True], pos=(0, 0), steps=8, done=True)
    assert grade_variation(obs, optimal_length=4) == 0.5


def test_ratio_clamped_in_unit_interval() -> None:
    obs = _final(visited=[True, True], pos=(0, 0), steps=4, done=True)
    assert 0.0 <= grade_variation(obs, optimal_length=4) <= 1.0
