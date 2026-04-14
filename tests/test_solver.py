# agent-notes: { ctx: "TSP solver correctness + performance", deps: [src/warehouse_routing/solver.py], state: active, last: "sato@2026-04-14" }
import time

from warehouse_routing.models import Cell
from warehouse_routing.solver import (
    manhattan,
    obstacle_aware_distance,
    optimal_tour_length,
    optimal_tour_order,
)


def test_no_skus_zero_distance() -> None:
    assert optimal_tour_length(Cell(row=0, col=0), []) == 0


def test_single_sku_roundtrip() -> None:
    # (0,0) -> (0,3) -> (0,0) = 6 manhattan
    assert optimal_tour_length(Cell(row=0, col=0), [Cell(row=0, col=3)]) == 6


def test_collinear_skus_optimal_order() -> None:
    # warehouse at 0,0; SKUs at (0,1),(0,2),(0,3) -> best tour is 6
    length = optimal_tour_length(
        Cell(row=0, col=0),
        [Cell(row=0, col=1), Cell(row=0, col=2), Cell(row=0, col=3)],
    )
    assert length == 6


def test_two_skus_triangle() -> None:
    # warehouse (0,0), SKUs (0,2) and (2,0)
    # optimal = 0->(0,2)->(2,0)->0 = 2 + 4 + 2 = 8
    length = optimal_tour_length(
        Cell(row=0, col=0),
        [Cell(row=0, col=2), Cell(row=2, col=0)],
    )
    assert length == 8


def test_handles_12_nodes_fast() -> None:
    skus = [Cell(row=i, col=(i * 3) % 23) for i in range(11)]
    t0 = time.perf_counter()
    length = optimal_tour_length(Cell(row=0, col=0), skus)
    elapsed = time.perf_counter() - t0
    assert length > 0
    assert elapsed < 1.0


def test_manhattan_symmetric() -> None:
    a, b = Cell(row=1, col=2), Cell(row=5, col=4)
    assert manhattan(a, b) == manhattan(b, a) == 6


def test_optimal_tour_order_no_skus() -> None:
    w = Cell(row=0, col=0)
    assert optimal_tour_order(w, []) == [w, w]


def test_optimal_tour_order_single_sku_closes_at_warehouse() -> None:
    w = Cell(row=0, col=0)
    sku = Cell(row=0, col=3)
    order = optimal_tour_order(w, [sku])
    assert order[0] == w
    assert order[-1] == w
    assert sku in order


def test_optimal_tour_order_visits_every_sku_exactly_once() -> None:
    w = Cell(row=0, col=0)
    skus = [Cell(row=0, col=2), Cell(row=2, col=0), Cell(row=2, col=2)]
    order = optimal_tour_order(w, skus)
    assert order[0] == w and order[-1] == w
    interior = order[1:-1]
    assert set(interior) == set(skus)
    assert len(interior) == len(skus)


def test_optimal_tour_order_length_matches_optimal_tour_length() -> None:
    w = Cell(row=0, col=0)
    skus = [Cell(row=0, col=2), Cell(row=2, col=0)]
    order = optimal_tour_order(w, skus)
    hops = sum(manhattan(a, b) for a, b in zip(order[:-1], order[1:], strict=True))
    assert hops == optimal_tour_length(w, skus)


def test_optimal_tour_order_respects_obstacle_distance() -> None:
    w = Cell(row=0, col=0)
    skus = [Cell(row=0, col=2)]
    obstacles = [Cell(row=0, col=1)]
    dist_fn = obstacle_aware_distance(4, 4, obstacles)
    order = optimal_tour_order(w, skus, distance_fn=dist_fn)
    assert order == [w, skus[0], w]
    hops = sum(dist_fn(a, b) for a, b in zip(order[:-1], order[1:], strict=True))
    assert hops == optimal_tour_length(w, skus, distance_fn=dist_fn)
