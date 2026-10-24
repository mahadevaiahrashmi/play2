"""Strict parsing of an LLM reply into a typed ``Move``, with bounded retries.

Contract
--------
* ``parse_action(raw)`` accepts exactly: a single letter N/S/E/W (any case,
  surrounding whitespace/punctuation tolerated), a JSON object
  ``{"move": "N"}``, or either wrapped in a Markdown code fence. Anything else
  raises ``ActionParseError``. (The legacy regex in ``inference.py`` would
  accept "I think NOT north" as ``N``; this does not.)
* ``request_action(llm, messages, max_retries)`` calls the LLM, and on an
  invalid reply re-asks with the bad reply and the parse error appended to the
  conversation. After ``max_retries + 1`` failed attempts it raises
  ``LLMOutputError`` carrying every ``FailedAttempt``. Each failed attempt is
  logged at WARNING (attempt number, raw reply, error). The caller's message
  list is never mutated. Errors raised by ``llm`` itself propagate untouched
  (timeouts/outages are ``resilient_llm``'s job).
* Fallback is explicit and lives in ``fallback_move``: when the model never
  produces a valid move, the policy plays a move that bumps a wall/obstacle if
  one exists (the simulator records an invalid-move penalty step and the robot
  does not move), otherwise "N". Callers must count these fallbacks.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from warehouse_routing.llm_types import LLMFn, LLMResponse, Message
from warehouse_routing.models import Move, Observation
from warehouse_routing.sim import MOVE_OFFSETS

_log = logging.getLogger(__name__)

_FENCE = re.compile(r"^```[a-zA-Z]*\s*(.*?)\s*```$", re.DOTALL)
_STRIP_CHARS = " \t\r\n.!`\"'"
_MOVES = ("N", "S", "E", "W")

CORRECTION_TEMPLATE = (
    "Your previous reply was invalid: {error}. "
    "Reply with EXACTLY ONE of N, S, E, W (a single uppercase letter). No explanation."
)


class ActionParseError(ValueError):
    """The reply is not a valid action."""


class ActionReply(BaseModel):
    """Typed shape of the JSON reply form."""

    model_config = ConfigDict(extra="forbid")
    move: Move

    @field_validator("move", mode="before")
    @classmethod
    def _upper(cls, v: object) -> object:
        return v.strip().upper() if isinstance(v, str) else v


@dataclass(frozen=True)
class FailedAttempt:
    number: int  # 1-based
    raw: str
    error: str


class LLMOutputError(RuntimeError):
    """No valid action after ``max_retries + 1`` attempts."""

    def __init__(self, failures: list[FailedAttempt], responses: list[LLMResponse]) -> None:
        self.failures = failures
        self.responses = responses
        last = failures[-1]
        super().__init__(
            f"no valid action after {len(failures)} attempts; last reply {last.raw!r}: {last.error}"
        )


@dataclass
class ParsedAction:
    move: Move
    attempts: int
    failures: list[FailedAttempt] = field(default_factory=list)
    responses: list[LLMResponse] = field(default_factory=list)


def parse_action(raw: str) -> Move:
    text = raw.strip()
    fence = _FENCE.match(text)
    if fence:
        text = fence.group(1).strip()
    if not text:
        raise ActionParseError("empty reply")
    if text.startswith("{"):
        try:
            return ActionReply.model_validate(json.loads(text)).move
        except json.JSONDecodeError as exc:
            raise ActionParseError(f"malformed JSON: {exc.msg}") from exc
        except ValidationError as exc:
            raise ActionParseError(f"invalid JSON action: {exc.errors()[0]['msg']}") from exc
    letter = text.strip(_STRIP_CHARS).upper()
    if letter in _MOVES:
        return letter  # type: ignore[return-value]
    raise ActionParseError(f"expected one of N, S, E, W, got {text[:40]!r}")


def request_action(
    llm: LLMFn,
    messages: list[Message],
    *,
    max_retries: int = 2,
) -> ParsedAction:
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")
    convo = [dict(m) for m in messages]
    failures: list[FailedAttempt] = []
    responses: list[LLMResponse] = []
    total = max_retries + 1
    for number in range(1, total + 1):
        response = llm(convo)
        responses.append(response)
        try:
            move = parse_action(response.text)
        except ActionParseError as exc:
            failures.append(FailedAttempt(number=number, raw=response.text, error=str(exc)))
            _log.warning(
                "invalid LLM reply: attempt %d/%d raw=%r error=%s",
                number, total, response.text, exc,
            )
            convo.append({"role": "assistant", "content": response.text})
            convo.append({"role": "user", "content": CORRECTION_TEMPLATE.format(error=exc)})
            continue
        return ParsedAction(move=move, attempts=number, failures=failures, responses=responses)
    raise LLMOutputError(failures, responses)


def fallback_move(obs: Observation) -> Move:
    """Deterministic fallback: prefer a move into a wall/obstacle (penalty-only step)."""
    blocked = {(c.row, c.col) for c in obs.obstacles}
    for move in _MOVES:
        dr, dc = MOVE_OFFSETS[move]
        r, c = obs.robot_pos.row + dr, obs.robot_pos.col + dc
        if not (0 <= r < obs.grid_rows and 0 <= c < obs.grid_cols) or (r, c) in blocked:
            return move  # type: ignore[return-value]
    return "N"
