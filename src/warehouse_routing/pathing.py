# agent-notes: { ctx: "A* shortest-path on 4-connected grid with obstacles", deps: [src/warehouse_routing/models.py], state: active, last: "sato@2026-04-14" }
"""A* pathfinding on an obstacle-aware 4-connected grid.

Feeds the TSP solver with obstacle-aware pairwise distances so the
optimal-tour computation matches what a physical AMR could actually
achieve.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable

from warehouse_routing.models import Cell

Coord = tuple[int, int]
_OFFSETS: tuple[Coord, ...] = ((-1, 0), (1, 0), (0, -1), (0, 1))


def _manhattan(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def astar_distance(
    grid_rows: int,
    grid_cols: int,
    obstacles: Iterable[Cell] | frozenset[Coord],
    start: Cell,
    end: Cell,
) -> int | None:
    """Return shortest-path step count from start to end, or None if unreachable.

    Obstacles may be passed as a Cell iterable or a frozenset of (row, col)
    tuples (for callers that precompute the blocking set).
    """
    if isinstance(obstacles, frozenset):
        blocked: frozenset[Coord] = obstacles
    else:
        blocked = frozenset((c.row, c.col) for c in obstacles)

    s: Coord = (start.row, start.col)
    t: Coord = (end.row, end.col)
    if s == t:
        return 0
    if s in blocked or t in blocked:
        return None

    open_heap: list[tuple[int, int, Coord]] = [(_manhattan(s, t), 0, s)]
    g_score: dict[Coord, int] = {s: 0}

    while open_heap:
        _f, g, cur = heapq.heappop(open_heap)
        if cur == t:
            return g
        if g > g_score.get(cur, 10**9):
            continue
        for dr, dc in _OFFSETS:
            nr, nc = cur[0] + dr, cur[1] + dc
            if nr < 0 or nr >= grid_rows or nc < 0 or nc >= grid_cols:
                continue
            nb: Coord = (nr, nc)
            if nb in blocked:
                continue
            ng = g + 1
            if ng < g_score.get(nb, 10**9):
                g_score[nb] = ng
                heapq.heappush(open_heap, (ng + _manhattan(nb, t), ng, nb))

    return None


def astar_path(
    grid_rows: int,
    grid_cols: int,
    obstacles: Iterable[Cell] | frozenset[Coord],
    start: Cell,
    end: Cell,
) -> list[Cell] | None:
    """Return the shortest path as a list of Cells (inclusive), or None."""
    if isinstance(obstacles, frozenset):
        blocked: frozenset[Coord] = obstacles
    else:
        blocked = frozenset((c.row, c.col) for c in obstacles)

    s: Coord = (start.row, start.col)
    t: Coord = (end.row, end.col)
    if s == t:
        return [start]
    if s in blocked or t in blocked:
        return None

    open_heap: list[tuple[int, int, Coord]] = [(_manhattan(s, t), 0, s)]
    g_score: dict[Coord, int] = {s: 0}
    parent: dict[Coord, Coord] = {}

    while open_heap:
        _f, g, cur = heapq.heappop(open_heap)
        if cur == t:
            path: list[Cell] = []
            node: Coord = cur
            while True:
                path.append(Cell(row=node[0], col=node[1]))
                if node == s:
                    break
                node = parent[node]
            path.reverse()
            return path
        if g > g_score.get(cur, 10**9):
            continue
        for dr, dc in _OFFSETS:
            nr, nc = cur[0] + dr, cur[1] + dc
            if nr < 0 or nr >= grid_rows or nc < 0 or nc >= grid_cols:
                continue
            nb: Coord = (nr, nc)
            if nb in blocked:
                continue
            ng = g + 1
            if ng < g_score.get(nb, 10**9):
                g_score[nb] = ng
                parent[nb] = cur
                heapq.heappush(open_heap, (ng + _manhattan(nb, t), ng, nb))

    return None
