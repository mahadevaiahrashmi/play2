# agent-notes: { ctx: "optimal closed-TSP tour length for warehouse + SKU set", deps: [src/warehouse_routing/models.py], state: active, last: "sato@2026-04-14" }
"""Optimal tour-length solver.

Takes the warehouse node and a list of SKU nodes and returns the length of
the shortest closed tour visiting every SKU and returning to the warehouse.

Uses python-tsp Held-Karp for exactness. Accepts a pluggable distance
function so obstacle-aware A* distances (sprint 2, issue #9) can slot in
without touching the solver.
"""

from collections.abc import Callable

import numpy as np
from python_tsp.exact import solve_tsp_dynamic_programming

from warehouse_routing.models import Cell
from warehouse_routing.pathing import astar_distance

DistanceFn = Callable[[Cell, Cell], int]


def manhattan(a: Cell, b: Cell) -> int:
    return abs(a.row - b.row) + abs(a.col - b.col)


def obstacle_aware_distance(
    grid_rows: int, grid_cols: int, obstacles: list[Cell]
) -> DistanceFn:
    """DistanceFn factory that uses A* shortest-path on an obstacle grid.

    Unreachable pairs return a large sentinel so the TSP solver avoids them
    (but still returns a tour if any feasible closed path exists).
    """
    blocked = frozenset((c.row, c.col) for c in obstacles)

    def _dist(a: Cell, b: Cell) -> int:
        d = astar_distance(grid_rows, grid_cols, blocked, a, b)
        return d if d is not None else 10**6

    return _dist


def build_distance_matrix(
    nodes: list[Cell], distance_fn: DistanceFn = manhattan
) -> np.ndarray:
    n = len(nodes)
    m = np.zeros((n, n), dtype=np.float64)
    for i in range(n):
        for j in range(n):
            if i != j:
                m[i, j] = distance_fn(nodes[i], nodes[j])
    return m


def optimal_tour_length(
    warehouse: Cell,
    sku_locations: list[Cell],
    distance_fn: DistanceFn = manhattan,
) -> int:
    if not sku_locations:
        return 0
    nodes: list[Cell] = [warehouse, *sku_locations]
    matrix = build_distance_matrix(nodes, distance_fn)
    _permutation, distance = solve_tsp_dynamic_programming(matrix)
    return int(distance)
