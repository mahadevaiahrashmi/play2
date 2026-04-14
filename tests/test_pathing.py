# agent-notes: { ctx: "A* shortest-path correctness + obstacle-aware solver integration", deps: [src/warehouse_routing/pathing.py, src/warehouse_routing/solver.py], state: active, last: "sato@2026-04-14" }
from warehouse_routing.models import Cell
from warehouse_routing.pathing import astar_distance
from warehouse_routing.solver import obstacle_aware_distance, optimal_tour_length


def test_same_point_zero_distance() -> None:
    assert astar_distance(4, 4, [], Cell(row=1, col=1), Cell(row=1, col=1)) == 0


def test_straight_line_no_obstacles() -> None:
    assert astar_distance(4, 4, [], Cell(row=0, col=0), Cell(row=0, col=3)) == 3


def test_diagonal_manhattan_on_open_grid() -> None:
    assert astar_distance(4, 4, [], Cell(row=0, col=0), Cell(row=3, col=3)) == 6


def test_obstacle_forces_detour() -> None:
    # Block (0,1) forces going down and around
    obstacles = [Cell(row=0, col=1)]
    d = astar_distance(4, 4, obstacles, Cell(row=0, col=0), Cell(row=0, col=2))
    assert d == 4  # 0,0 -> 1,0 -> 1,1 -> 1,2 -> 0,2


def test_unreachable_returns_none() -> None:
    # Wall of obstacles cutting off the target
    obstacles = [Cell(row=1, col=c) for c in range(4)]
    d = astar_distance(4, 4, obstacles, Cell(row=0, col=0), Cell(row=3, col=3))
    assert d is None


def test_start_on_obstacle_unreachable() -> None:
    obstacles = [Cell(row=0, col=0)]
    d = astar_distance(4, 4, obstacles, Cell(row=0, col=0), Cell(row=1, col=1))
    assert d is None


def test_solver_uses_astar_with_obstacles() -> None:
    # Warehouse (0,0), SKU (0,2), obstacle at (0,1).
    # Manhattan would say 2 each way = 4 total round trip.
    # A* says path is 0,0 -> 1,0 -> 1,1 -> 1,2 -> 0,2 = 4 one way => 8 closed.
    warehouse = Cell(row=0, col=0)
    skus = [Cell(row=0, col=2)]
    obstacles = [Cell(row=0, col=1)]
    dist_fn = obstacle_aware_distance(4, 4, obstacles)
    length = optimal_tour_length(warehouse, skus, distance_fn=dist_fn)
    assert length == 8
