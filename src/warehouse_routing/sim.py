# agent-notes: { ctx: "deterministic grid state machine for AMR routing", deps: [src/warehouse_routing/models.py], state: active, last: "sato@2026-04-14" }
"""Grid simulator for warehouse AMR routing.

Pure state transitions. No reward shaping, no LLM. The reward function
(issue #6) consumes StepResult and produces a Reward.
"""

from dataclasses import dataclass

from warehouse_routing.models import Action, Cell, Observation

MOVE_OFFSETS: dict[str, tuple[int, int]] = {
    "N": (-1, 0),
    "S": (1, 0),
    "E": (0, 1),
    "W": (0, -1),
}


@dataclass(frozen=True)
class StepResult:
    observation: Observation
    invalid: bool
    newly_visited_index: int  # -1 if none
    at_warehouse: bool
    done: bool


class GridEnv:
    """Deterministic grid state machine."""

    def __init__(self, initial: Observation) -> None:
        self._obs = initial
        self._obstacle_set: frozenset[tuple[int, int]] = frozenset(
            (c.row, c.col) for c in initial.obstacles
        )
        self._sku_index: dict[tuple[int, int], int] = {
            (c.row, c.col): i for i, c in enumerate(initial.sku_locations)
        }

    @property
    def observation(self) -> Observation:
        return self._obs

    def _is_blocked(self, row: int, col: int) -> bool:
        if row < 0 or row >= self._obs.grid_rows:
            return True
        if col < 0 or col >= self._obs.grid_cols:
            return True
        if (row, col) in self._obstacle_set:
            return True
        return False

    def _all_visited(self) -> bool:
        return all(self._obs.visited)

    def _at_warehouse(self, cell: Cell) -> bool:
        return cell == self._obs.warehouse

    def step(self, action: Action) -> StepResult:
        if self._obs.done:
            return StepResult(self._obs, invalid=True, newly_visited_index=-1, at_warehouse=False, done=True)

        dr, dc = MOVE_OFFSETS[action.move]
        new_row = self._obs.robot_pos.row + dr
        new_col = self._obs.robot_pos.col + dc

        steps_taken = self._obs.steps_taken + 1
        budget_exhausted = steps_taken >= self._obs.step_budget

        if self._is_blocked(new_row, new_col):
            self._obs = self._obs.model_copy(
                update={"steps_taken": steps_taken, "done": budget_exhausted}
            )
            return StepResult(
                self._obs,
                invalid=True,
                newly_visited_index=-1,
                at_warehouse=self._at_warehouse(self._obs.robot_pos),
                done=budget_exhausted,
            )

        new_pos = Cell(row=new_row, col=new_col)
        new_visited = list(self._obs.visited)
        newly_visited = -1
        if (new_row, new_col) in self._sku_index:
            idx = self._sku_index[(new_row, new_col)]
            if not new_visited[idx]:
                new_visited[idx] = True
                newly_visited = idx

        at_wh = new_pos == self._obs.warehouse
        all_visited_now = all(new_visited)
        success = all_visited_now and at_wh
        done = success or budget_exhausted

        self._obs = self._obs.model_copy(
            update={
                "robot_pos": new_pos,
                "visited": new_visited,
                "steps_taken": steps_taken,
                "done": done,
            }
        )
        return StepResult(
            self._obs,
            invalid=False,
            newly_visited_index=newly_visited,
            at_warehouse=at_wh,
            done=done,
        )
