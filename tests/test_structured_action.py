"""structured_action: strict parsing, retry-with-error prompts, explicit fallback."""

import logging

import pytest

from warehouse_routing.llm_types import LLMResponse
from warehouse_routing.models import Cell, Observation
from warehouse_routing.structured_action import (
    ActionParseError,
    LLMOutputError,
    fallback_move,
    parse_action,
    request_action,
)


class Scripted:
    """LLM stub returning scripted replies; records the messages it saw."""

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.seen: list[list[dict[str, str]]] = []

    def __call__(self, messages: list[dict[str, str]]) -> LLMResponse:
        self.seen.append([dict(m) for m in messages])
        return LLMResponse(text=self.replies.pop(0), prompt_tokens=10, completion_tokens=1)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("N", "N"),
        (" e\n", "E"),
        ("S.", "S"),
        ('{"move": "W"}', "W"),
        ('```json\n{"move":"n"}\n```', "N"),
    ],
)
def test_parse_accepts_strict_formats(raw: str, expected: str) -> None:
    assert parse_action(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "I think North", "NE", "go E then N", '{"move": "up"}', '{"dir": "N"}', "[1]", "{bad"],
)
def test_parse_rejects_anything_else(raw: str) -> None:
    with pytest.raises(ActionParseError):
        parse_action(raw)


def test_first_valid_reply_needs_one_attempt() -> None:
    llm = Scripted(["E"])
    result = request_action(llm, [{"role": "user", "content": "go"}])
    assert result.move == "E"
    assert result.attempts == 1
    assert result.failures == []
    assert len(result.responses) == 1


def test_retry_prompt_includes_previous_reply_and_error() -> None:
    llm = Scripted(["maybe north?", "N"])
    result = request_action(llm, [{"role": "user", "content": "go"}], max_retries=2)
    assert result.move == "N"
    assert result.attempts == 2
    assert [f.number for f in result.failures] == [1]
    assert result.failures[0].raw == "maybe north?"
    second_prompt = llm.seen[1]
    # original prompt + the bad assistant reply + a corrective user message
    assert second_prompt[0] == {"role": "user", "content": "go"}
    assert second_prompt[1] == {"role": "assistant", "content": "maybe north?"}
    assert second_prompt[2]["role"] == "user"
    assert result.failures[0].error in second_prompt[2]["content"]
    # the caller's message list is never mutated
    assert llm.seen[0] == [{"role": "user", "content": "go"}]


def test_raises_after_max_retries_plus_one_attempts_and_logs_each(
    caplog: pytest.LogCaptureFixture,
) -> None:
    llm = Scripted(["a", "b", "c", "N"])
    with (
        caplog.at_level(logging.WARNING, logger="warehouse_routing.structured_action"),
        pytest.raises(LLMOutputError) as exc,
    ):
        request_action(llm, [{"role": "user", "content": "go"}], max_retries=2)
    assert len(llm.seen) == 3  # max_retries + 1, the 4th scripted reply is never consumed
    assert [f.raw for f in exc.value.failures] == ["a", "b", "c"]
    assert [f.number for f in exc.value.failures] == [1, 2, 3]
    assert len(exc.value.responses) == 3
    msgs = [r.getMessage() for r in caplog.records]
    assert len(msgs) == 3
    assert "attempt 2" in msgs[1] and "'b'" in msgs[1]


def test_zero_retries_means_single_attempt() -> None:
    llm = Scripted(["nope", "N"])
    with pytest.raises(LLMOutputError):
        request_action(llm, [{"role": "user", "content": "go"}], max_retries=0)
    assert len(llm.seen) == 1


def test_negative_retries_rejected() -> None:
    with pytest.raises(ValueError):
        request_action(Scripted([]), [], max_retries=-1)


def _obs(row: int, col: int, obstacles: list[Cell] | None = None) -> Observation:
    return Observation(
        grid_rows=3, grid_cols=3, warehouse=Cell(row=0, col=0),
        sku_locations=[Cell(row=2, col=2)], obstacles=obstacles or [],
        robot_pos=Cell(row=row, col=col), visited=[False], steps_taken=0, step_budget=10,
        tier="easy", attempt=1, variation_seed=0,
    )


def test_fallback_prefers_a_move_that_bumps_a_wall() -> None:
    # at the top-left corner N is out of the grid -> pure penalty step, no movement
    assert fallback_move(_obs(0, 0)) == "N"
    # bottom-left: N is open, S is a wall
    assert fallback_move(_obs(2, 0)) == "S"
    # centre cell with an obstacle to the east
    assert fallback_move(_obs(1, 1, [Cell(row=1, col=2)])) == "E"


def test_fallback_in_open_cell_is_deterministic_north() -> None:
    assert fallback_move(_obs(1, 1)) == "N"
