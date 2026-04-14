# agent-notes: { ctx: "task specs + seeded variation generators", deps: [src/warehouse_routing/models.py, src/warehouse_routing/solver.py], state: active, last: "sato@2026-04-14" }
"""Task definitions and deterministic variation generators.

A TaskSpec is the tier-level template (grid size, SKU count, obstacle
density, step budget). A variation is a concrete (Observation,
optimal_length) pair produced from a seed. Same seed -> same variation.
"""

import random
from collections import deque
from dataclasses import dataclass

from warehouse_routing.models import Cell, Observation, Tier
from warehouse_routing.solver import obstacle_aware_distance, optimal_tour_length


@dataclass(frozen=True)
class TaskSpec:
    tier: Tier
    grid_rows: int
    grid_cols: int
    n_skus: int
    obstacle_density: float
    step_budget: int


EASY = TaskSpec(
    tier="easy",
    grid_rows=8,
    grid_cols=8,
    n_skus=3,
    obstacle_density=0.0,
    step_budget=64,
)

MEDIUM = TaskSpec(
    tier="medium",
    grid_rows=16,
    grid_cols=16,
    n_skus=6,
    obstacle_density=0.10,
    step_budget=200,
)


def _reachable_from(
    grid_rows: int,
    grid_cols: int,
    blocked: set[tuple[int, int]],
    start: tuple[int, int],
) -> set[tuple[int, int]]:
    """BFS from start; returns every reachable cell."""
    seen: set[tuple[int, int]] = {start}
    queue: deque[tuple[int, int]] = deque([start])
    while queue:
        r, c = queue.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = r + dr, c + dc
            if (
                0 <= nr < grid_rows
                and 0 <= nc < grid_cols
                and (nr, nc) not in blocked
                and (nr, nc) not in seen
            ):
                seen.add((nr, nc))
                queue.append((nr, nc))
    return seen


def _prune_until_reachable(
    grid_rows: int,
    grid_cols: int,
    obstacle_coords: list[tuple[int, int]],
    warehouse: tuple[int, int],
    sku_coords: list[tuple[int, int]],
    rng: random.Random,
) -> list[tuple[int, int]]:
    """Remove obstacles one at a time until all SKUs are reachable from warehouse."""
    blocked = set(obstacle_coords)
    targets = set(sku_coords)
    current = list(obstacle_coords)
    while True:
        reachable = _reachable_from(grid_rows, grid_cols, blocked, warehouse)
        if targets.issubset(reachable):
            return sorted(blocked)
        if not current:
            return []
        rng.shuffle(current)
        victim = current.pop()
        blocked.discard(victim)


@dataclass(frozen=True)
class Variation:
    observation: Observation
    optimal_length: int


def make_variation(spec: TaskSpec, seed: int, attempt: int = 1) -> Variation:
    rng = random.Random(seed)
    warehouse = Cell(row=0, col=0)

    all_cells = [
        (r, c)
        for r in range(spec.grid_rows)
        for c in range(spec.grid_cols)
        if (r, c) != (warehouse.row, warehouse.col)
    ]
    rng.shuffle(all_cells)

    sku_coords = all_cells[: spec.n_skus]
    remaining = all_cells[spec.n_skus :]

    n_obstacles = int(spec.obstacle_density * (spec.grid_rows * spec.grid_cols))
    obstacle_coords = remaining[:n_obstacles]

    if obstacle_coords:
        obstacle_coords = _prune_until_reachable(
            spec.grid_rows,
            spec.grid_cols,
            obstacle_coords,
            (warehouse.row, warehouse.col),
            sku_coords,
            rng,
        )

    sku_cells = [Cell(row=r, col=c) for r, c in sku_coords]
    obstacle_cells = [Cell(row=r, col=c) for r, c in obstacle_coords]

    obs = Observation(
        grid_rows=spec.grid_rows,
        grid_cols=spec.grid_cols,
        warehouse=warehouse,
        sku_locations=sku_cells,
        obstacles=obstacle_cells,
        robot_pos=warehouse,
        visited=[False] * len(sku_cells),
        steps_taken=0,
        step_budget=spec.step_budget,
        tier=spec.tier,
        attempt=attempt,
        variation_seed=seed,
        done=False,
    )
    if obstacle_cells:
        dist_fn = obstacle_aware_distance(spec.grid_rows, spec.grid_cols, obstacle_cells)
        optimal = optimal_tour_length(warehouse, sku_cells, distance_fn=dist_fn)
    else:
        optimal = optimal_tour_length(warehouse, sku_cells)
    return Variation(observation=obs, optimal_length=optimal)
