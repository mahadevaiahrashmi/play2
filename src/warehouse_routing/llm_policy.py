"""LLM-backed routing policy built from the reusable pieces in this package.

Contract
--------
* ``build_messages(obs, history)`` produces the exact system/user prompt used
  by ``inference.py`` (shared, not duplicated): ``recent_moves: ...`` plus the
  JSON observation.
* ``LLMPolicy.choose(obs)`` asks ``request_action`` (strict parse + bounded
  retries) and returns a ``Move``. If the model never produces a valid move,
  or the transport layer gives up (retries exhausted, timeout, circuit open),
  it plays ``fallback_move`` (a wall bump = one penalty step) and increments
  ``fallbacks``; it never invents a "plausible" move. ``BudgetExceeded`` is
  *not* caught: running out of budget must stop the episode.
* Counters (``llm_calls``, ``parse_failures``, ``call_errors``,
  ``fallbacks``) make every degraded step visible to the runner/leaderboard.
* ``build_llm_stack`` composes ``ResilientLLM(MeteredLLM(raw_fn))`` so that every
  physical attempt (including transport retries) is metered, and an open
  circuit short-circuits *before* any budget is reserved.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from warehouse_routing.budget import BudgetLedger, MeteredLLM
from warehouse_routing.llm_types import LLMFn, LLMResponse, Message
from warehouse_routing.models import Move, Observation
from warehouse_routing.resilient_llm import (
    CircuitBreaker,
    CircuitOpenError,
    LLMTimeoutError,
    ResilientLLM,
    RetriesExhaustedError,
)
from warehouse_routing.structured_action import LLMOutputError, fallback_move, request_action
from warehouse_routing.tracing import Tracer

HISTORY_WINDOW = 8

SYSTEM_PROMPT = (
    "You control a warehouse autonomous mobile robot (AMR) on a grid. Your goal: "
    "visit every SKU cell, then return to the packing station (warehouse), using "
    "the fewest moves. Obstacles block movement; leaving the grid is invalid.\n"
    "Each turn you receive the current state as JSON. Respond with EXACTLY ONE of "
    "N, S, E, W (single uppercase letter). No explanation."
)

# Errors that mean "the model/provider is unavailable" (as opposed to a bug).
RECOVERABLE = (LLMOutputError, RetriesExhaustedError, CircuitOpenError, LLMTimeoutError)


def format_history(history: list[dict[str, Any]]) -> str:
    recent = history[-HISTORY_WINDOW:]
    return (
        "; ".join(f"{h['action']}->r={h['reward']:.2f}" for h in recent) if recent else "none"
    )


def build_messages(obs: Observation, history: list[dict[str, Any]]) -> list[Message]:
    user_content = f"recent_moves: {format_history(history)}\nstate: {obs.model_dump_json()}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def transient_errors() -> tuple[type[BaseException], ...]:
    """Errors worth retrying: OS/network errors, timeouts and (if installed) openai's."""
    errs: tuple[type[BaseException], ...] = (OSError, LLMTimeoutError)
    try:  # pragma: no cover - depends on the optional client
        import openai

        errs += (
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.RateLimitError,
            openai.InternalServerError,
        )
    except Exception:  # pragma: no cover
        pass
    return errs


def openai_llm_fn(client: object, model: str, max_tokens: int = 16) -> LLMFn:
    """Adapt an OpenAI-compatible client to the package's LLM function shape."""

    def call(messages: list[Message]) -> LLMResponse:
        completion = client.chat.completions.create(  # type: ignore[attr-defined]
            model=model, messages=messages, max_tokens=max_tokens, temperature=0.0
        )
        usage = getattr(completion, "usage", None)
        return LLMResponse(
            text=completion.choices[0].message.content or "",
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )

    return call


def build_llm_stack(
    raw_fn: LLMFn,
    *,
    ledger: BudgetLedger | None = None,
    episode_id: str = "episode",
    model: str = "model",
    max_completion_tokens: int = 16,
    timeout_s: float | None = 30.0,
    max_retries: int = 3,
    breaker: CircuitBreaker | None = None,
    sleep: Callable[[float], None] | None = None,
    rand: Callable[[], float] | None = None,
) -> LLMFn:
    inner: LLMFn = raw_fn
    if ledger is not None:
        inner = MeteredLLM(
            raw_fn, ledger, episode_id=episode_id, model=model,
            max_completion_tokens=max_completion_tokens,
        )
    kwargs: dict[str, Any] = {}
    if sleep is not None:
        kwargs["sleep"] = sleep
    return ResilientLLM(
        inner, timeout_s=timeout_s, max_retries=max_retries, breaker=breaker,
        retry_on=transient_errors(), rand=rand, **kwargs,
    )


class LLMPolicy:
    def __init__(
        self,
        llm: LLMFn,
        *,
        max_retries: int = 2,
        tracer: Tracer | None = None,
        tick: Callable[[], None] | None = None,
    ) -> None:
        self._llm = llm
        self._max_retries = max_retries
        self._tracer = tracer
        self._tick = tick
        self.history: list[dict[str, Any]] = []
        self._last_steps = -1
        self.llm_calls = 0
        self.parse_failures = 0
        self.call_errors = 0
        self.fallbacks = 0

    def reset(self) -> None:
        self.history = []
        self._last_steps = -1

    def choose(self, obs: Observation) -> Move:
        if obs.steps_taken <= self._last_steps:
            self.history = []
        self._last_steps = obs.steps_taken
        if self._tick is not None:
            self._tick()
        messages = build_messages(obs, self.history)
        if self._tracer is not None:
            self._tracer.observe_prompt(
                (
                    (obs.robot_pos.row, obs.robot_pos.col),
                    tuple(obs.visited),
                    format_history(self.history),
                )
            )
        try:
            if self._tracer is not None:
                with self._tracer.span("llm.request", step=obs.steps_taken):
                    parsed = request_action(self._llm, messages, max_retries=self._max_retries)
            else:
                parsed = request_action(self._llm, messages, max_retries=self._max_retries)
        except LLMOutputError as exc:
            self.llm_calls += len(exc.responses)
            self.parse_failures += len(exc.failures)
            self._degrade(exc)
        except RECOVERABLE as exc:
            self.call_errors += 1
            self._degrade(exc)
        else:
            self.llm_calls += len(parsed.responses)
            self.parse_failures += len(parsed.failures)
            return parsed.move
        return fallback_move(obs)

    def _degrade(self, exc: BaseException) -> None:
        self.fallbacks += 1
        if self._tracer is not None:
            self._tracer.add_error(f"{type(exc).__name__}: {exc}")

    def record(self, action: Move, reward: float) -> None:
        self.history.append({"action": action, "reward": reward})
