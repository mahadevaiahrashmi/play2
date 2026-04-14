# agent-notes: { ctx: "grid simulator state transitions", deps: [src/warehouse_routing/sim.py], state: active, last: "sato@2026-04-14" }
from warehouse_routing.models import Action, Cell, Observation
from warehouse_routing.sim import GridEnv


def _obs(sku: list[tuple[int, int]] | None = None, obstacles: list[tuple[int, int]] | None = None, pos: tuple[int, int] = (0, 0), budget: int = 64) -> Observation:
    sku = sku or [(0, 2)]
    obstacles = obstacles or []
    return Observation(
        grid_rows=4,
        grid_cols=4,
        warehouse=Cell(row=0, col=0),
        sku_locations=[Cell(row=r, col=c) for r, c in sku],
        obstacles=[Cell(row=r, col=c) for r, c in obstacles],
        robot_pos=Cell(row=pos[0], col=pos[1]),
        visited=[False] * len(sku),
        steps_taken=0,
        step_budget=budget,
        tier="easy",
        attempt=1,
        variation_seed=0,
    )


def test_each_move_direction() -> None:
    env = GridEnv(_obs(pos=(1, 1)))
    assert env.step(Action(move="N")).observation.robot_pos == Cell(row=0, col=1)
    env = GridEnv(_obs(pos=(1, 1)))
    assert env.step(Action(move="S")).observation.robot_pos == Cell(row=2, col=1)
    env = GridEnv(_obs(pos=(1, 1)))
    assert env.step(Action(move="E")).observation.robot_pos == Cell(row=1, col=2)
    env = GridEnv(_obs(pos=(1, 1)))
    assert env.step(Action(move="W")).observation.robot_pos == Cell(row=1, col=0)


def test_out_of_bounds_invalid_no_move() -> None:
    env = GridEnv(_obs(pos=(0, 0)))
    r = env.step(Action(move="N"))
    assert r.invalid
    assert r.observation.robot_pos == Cell(row=0, col=0)
    assert r.observation.steps_taken == 1


def test_obstacle_blocks() -> None:
    env = GridEnv(_obs(pos=(0, 0), obstacles=[(0, 1)]))
    r = env.step(Action(move="E"))
    assert r.invalid
    assert r.observation.robot_pos == Cell(row=0, col=0)


def test_auto_visit_on_sku() -> None:
    env = GridEnv(_obs(sku=[(0, 1)], pos=(0, 0)))
    r = env.step(Action(move="E"))
    assert not r.invalid
    assert r.newly_visited_index == 0
    assert r.observation.visited == [True]


def test_revisit_does_not_reflag() -> None:
    env = GridEnv(_obs(sku=[(0, 1)], pos=(0, 0)))
    env.step(Action(move="E"))
    env.step(Action(move="W"))
    r = env.step(Action(move="E"))
    assert r.newly_visited_index == -1


def test_terminal_on_all_visited_and_home() -> None:
    env = GridEnv(_obs(sku=[(0, 1)], pos=(0, 0)))
    env.step(Action(move="E"))
    r = env.step(Action(move="W"))
    assert r.done
    assert r.at_warehouse


def test_budget_exhaustion_terminates() -> None:
    env = GridEnv(_obs(sku=[(3, 3)], pos=(0, 0), budget=2))
    env.step(Action(move="E"))
    r = env.step(Action(move="E"))
    assert r.done
    assert r.observation.steps_taken == 2


def test_determinism_same_seed_same_trace() -> None:
    moves = [Action(move=m) for m in ("E", "E", "S", "W")]  # type: ignore[arg-type]
    env_a = GridEnv(_obs(sku=[(1, 2)], pos=(0, 0)))
    env_b = GridEnv(_obs(sku=[(1, 2)], pos=(0, 0)))
    for m in moves:
        ra = env_a.step(m)
        rb = env_b.step(m)
        assert ra == rb
