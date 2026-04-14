# agent-notes: { ctx: "TSP solver correctness + performance", deps: [src/warehouse_routing/solver.py], state: active, last: "sato@2026-04-14" }
import time

from warehouse_routing.models import Cell
from warehouse_routing.solver import manhattan, optimal_tour_length


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
