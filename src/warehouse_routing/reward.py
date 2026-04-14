# agent-notes: { ctx: "dense shaped reward + penalties per step", deps: [src/warehouse_routing/sim.py, src/warehouse_routing/models.py], state: active, last: "sato@2026-04-14" }
"""Dense shaped reward function.

Provides signal on every step (not just terminal) and rewards partial
progress toward task completion. Penalizes invalid moves. Terminal
bonus on success is scaled by the same optimal/agent ratio used by the
grader, so the RL signal is aligned with the final score.
"""

from warehouse_routing.models import Reward
from warehouse_routing.sim import StepResult

TIME_PENALTY = -0.01
INVALID_PENALTY = -0.05
SKU_VISIT_BONUS = 0.1


def compute_reward(result: StepResult, optimal_length: int) -> Reward:
    progress = 0.0
    penalty = TIME_PENALTY
    terminal = 0.0

    if result.invalid:
        penalty += INVALID_PENALTY

    if result.newly_visited_index >= 0:
        progress += SKU_VISIT_BONUS

    if result.done:
        obs = result.observation
        success = all(obs.visited) and obs.robot_pos == obs.warehouse
        if success and obs.steps_taken > 0:
            terminal = optimal_length / obs.steps_taken
        else:
            terminal = 0.0

    return Reward(
        value=progress + penalty + terminal,
        progress=progress,
        penalty=penalty,
        terminal=terminal,
    )
