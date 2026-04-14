# agent-notes: { ctx: "terminal scoring of a variation: optimal/agent ratio", deps: [src/warehouse_routing/models.py], state: active, last: "sato@2026-04-14" }
"""Programmatic grader for a single variation.

Score = optimal_length / agent_length, clamped to [0, 1]. Failure to
complete the task (any unvisited SKU or robot not back at warehouse)
returns 0.0. Step-count used for agent length includes invalid-move
attempts, so wall-bumping is naturally penalized.
"""

from warehouse_routing.models import Observation


def grade_variation(final_obs: Observation, optimal_length: int) -> float:
    if not final_obs.done:
        return 0.0
    if not all(final_obs.visited):
        return 0.0
    if final_obs.robot_pos != final_obs.warehouse:
        return 0.0
    agent_length = final_obs.steps_taken
    if optimal_length <= 0:
        return 1.0
    if agent_length <= 0:
        return 0.0
    return max(0.0, min(1.0, optimal_length / agent_length))
