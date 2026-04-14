# agent-notes: { ctx: "baseline policies: Random + Oracle for eval harness", deps: [src/warehouse_routing/models.py, src/warehouse_routing/solver.py, src/warehouse_routing/pathing.py], state: active, last: "sato@2026-04-14" }
"""Deterministic baseline policies.

- `RandomPolicy` — uniform over N/S/E/W, useful as a lower bound.
- `OraclePolicy` — computes the optimal TSP tour on the first observation
  of each episode and replays the precomputed move sequence. Scores 1.0
  on every variation and doubles as a regression check: if the grader,
  solver, or sim drift apart, the oracle stops scoring 1.0.

Both implement the same `choose(obs) -> Move` interface used by
`inference.py` and the eval harness.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from warehouse_routing.models import Cell, Move, Observation
from warehouse_routing.pathing import astar_path
from warehouse_routing.solver import obstacle_aware_distance, optimal_tour_order

VALID_MOVES: tuple[Move, ...] = ("N", "S", "E", "W")


@dataclass
class RandomPolicy:
    rng: random.Random

    def choose(self, obs: Observation) -> Move:
        return self.rng.choice(VALID_MOVES)


@dataclass
class OraclePolicy:
    """Replays the exact optimal tour, A*-routed around obstacles."""

    _plan: list[Move] = field(default_factory=list)
    _plan_seed: int | None = None

    def choose(self, obs: Observation) -> Move:
        if obs.steps_taken == 0 or self._plan_seed != obs.variation_seed:
            self._plan = _plan_optimal_moves(obs)
            self._plan_seed = obs.variation_seed
        if not self._plan:
            # Sim keeps asking for a move after we think we're done —
            # fall back to a harmless no-op direction. The grader will
            # punish this, and it means either solver or sim drifted.
            return "N"
        return self._plan.pop(0)


def _plan_optimal_moves(obs: Observation) -> list[Move]:
    distance_fn = obstacle_aware_distance(obs.grid_rows, obs.grid_cols, obs.obstacles)
    tour = optimal_tour_order(obs.warehouse, obs.sku_locations, distance_fn)
    blocked = frozenset((c.row, c.col) for c in obs.obstacles)

    moves: list[Move] = []
    for a, b in zip(tour[:-1], tour[1:], strict=True):
        path = astar_path(obs.grid_rows, obs.grid_cols, blocked, a, b)
        if path is None or len(path) < 2:
            continue
        for prev, curr in zip(path[:-1], path[1:], strict=True):
            moves.append(_cells_to_move(prev, curr))
    return moves


def _cells_to_move(a: Cell, b: Cell) -> Move:
    dr = b.row - a.row
    dc = b.col - a.col
    if dr == -1 and dc == 0:
        return "N"
    if dr == 1 and dc == 0:
        return "S"
    if dr == 0 and dc == 1:
        return "E"
    if dr == 0 and dc == -1:
        return "W"
    raise ValueError(f"non-adjacent cells in plan: {a} -> {b}")
