# agent-notes: { ctx: "typed OpenEnv Observation/Action/Reward models", deps: [], state: active, last: "sato@2026-04-14" }
"""Typed Pydantic models for the OpenEnv interface."""

from typing import Literal

from openenv.core.env_server.types import Action as _OpenEnvAction
from openenv.core.env_server.types import Observation as _OpenEnvObservation
from pydantic import BaseModel, ConfigDict, Field

Tier = Literal["easy", "medium", "hard"]
Move = Literal["N", "S", "E", "W"]


class Cell(BaseModel):
    model_config = ConfigDict(frozen=True)
    row: int = Field(ge=0)
    col: int = Field(ge=0)


class Observation(_OpenEnvObservation):
    grid_rows: int = Field(ge=1)
    grid_cols: int = Field(ge=1)
    warehouse: Cell
    sku_locations: list[Cell]
    obstacles: list[Cell] = Field(default_factory=list)
    robot_pos: Cell
    visited: list[bool]
    steps_taken: int = Field(ge=0)
    step_budget: int = Field(ge=1)
    tier: Tier
    attempt: int = Field(ge=1)
    variation_seed: int


class Action(_OpenEnvAction):
    move: Move


class Reward(BaseModel):
    value: float
    progress: float = 0.0
    penalty: float = 0.0
    terminal: float = 0.0
