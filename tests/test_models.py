# agent-notes: { ctx: "Pydantic model round-trip + validation tests", deps: [src/warehouse_routing/models.py], state: active, last: "sato@2026-04-14" }
import pytest
from pydantic import ValidationError

from warehouse_routing.models import Action, Cell, Observation, Reward


def _obs() -> Observation:
    return Observation(
        grid_rows=8,
        grid_cols=8,
        warehouse=Cell(row=0, col=0),
        sku_locations=[Cell(row=2, col=3), Cell(row=5, col=6)],
        robot_pos=Cell(row=0, col=0),
        visited=[False, False],
        steps_taken=0,
        step_budget=64,
        tier="easy",
        attempt=1,
        variation_seed=42,
    )


def test_observation_roundtrip() -> None:
    obs = _obs()
    data = obs.model_dump()
    restored = Observation.model_validate(data)
    assert restored == obs


def test_observation_json_roundtrip() -> None:
    obs = _obs()
    restored = Observation.model_validate_json(obs.model_dump_json())
    assert restored == obs


def test_action_valid_moves() -> None:
    for m in ("N", "S", "E", "W"):
        assert Action(move=m).move == m  # type: ignore[arg-type]


def test_action_rejects_invalid_move() -> None:
    with pytest.raises(ValidationError):
        Action(move="UP")  # type: ignore[arg-type]


def test_reward_defaults() -> None:
    r = Reward(value=0.5)
    assert r.progress == 0.0 and r.penalty == 0.0 and r.terminal == 0.0


def test_cell_rejects_negative() -> None:
    with pytest.raises(ValidationError):
        Cell(row=-1, col=0)


def test_observation_rejects_zero_grid() -> None:
    with pytest.raises(ValidationError):
        Observation(
            grid_rows=0,
            grid_cols=8,
            warehouse=Cell(row=0, col=0),
            sku_locations=[],
            robot_pos=Cell(row=0, col=0),
            visited=[],
            steps_taken=0,
            step_budget=1,
            tier="easy",
            attempt=1,
            variation_seed=0,
        )
