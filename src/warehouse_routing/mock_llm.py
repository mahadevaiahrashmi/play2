"""Scripted fake LLM for offline, deterministic exercise of the failure paths.

Everything here is SIMULATED: no model is called and no real model quality is
measured. Results produced with it must be labelled "simulated LLM".

Contract
--------
* ``ScriptedLLM(script)`` is an LLM function (``messages -> LLMResponse``).
  ``script`` is either a list of replies (a ``str`` is returned, an exception
  instance/class is raised), consumed one per call, with ``on_exhausted``
  = ``"cycle"`` (default) / ``"last"`` / ``"error"``; or a *behavior* callable
  ``(call_index, observation) -> str | BaseException``. The observation is
  parsed back out of the prompt, exactly what a model would see.
* Token usage is ``estimate_tokens`` of the prompt/reply (deterministic).
* ``MockLLMPolicy`` is an ``LLMPolicy`` over a ``ScriptedLLM``.
* ``SCENARIOS`` maps scenario names to behavior factories taking a seed:
  valid, malformed-then-valid, flaky-timeouts, noisy-30pct, oscillating,
  garbage, outage-then-recovery. All randomness is seeded.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence

from warehouse_routing.budget import Price
from warehouse_routing.llm_policy import LLMPolicy, build_llm_stack
from warehouse_routing.llm_types import (
    LLMFn,
    LLMResponse,
    Message,
    estimate_message_tokens,
    estimate_tokens,
)
from warehouse_routing.models import Observation
from warehouse_routing.policies import VALID_MOVES, GreedyPolicy
from warehouse_routing.resilient_llm import CircuitBreaker
from warehouse_routing.runner import EpisodeContext, PolicyFactory

Behavior = Callable[[int, Observation], "str | BaseException"]

MOCK_MODEL = "mock-llm"
# Illustrative, SIMULATED prices ($ per 1k tokens) so cost accounting has something to add up.
MOCK_PRICE = Price(input_per_1k=0.0005, output_per_1k=0.0015)


def observation_from_messages(messages: list[Message]) -> Observation:
    """Recover the Observation JSON embedded in the first user message."""
    for m in messages:
        if m["role"] == "user" and "state: " in m["content"]:
            obs: Observation = Observation.model_validate_json(m["content"].split("state: ", 1)[1])
            return obs
    raise ValueError("no state found in prompt")


class ScriptedLLM:
    def __init__(
        self,
        script: Sequence[str | BaseException | type[BaseException]] | Behavior,
        *,
        on_exhausted: str = "cycle",
    ) -> None:
        if on_exhausted not in ("cycle", "last", "error"):
            raise ValueError("on_exhausted must be cycle|last|error")
        self._script = script
        self._on_exhausted = on_exhausted
        self.calls = 0

    def _next(self, messages: list[Message]) -> str | BaseException | type[BaseException]:
        i = self.calls
        if callable(self._script):
            return self._script(i, observation_from_messages(messages))
        n = len(self._script)
        if i >= n:
            if self._on_exhausted == "error":
                raise IndexError("script exhausted")
            i = (i % n) if self._on_exhausted == "cycle" else n - 1
        return self._script[i]

    def __call__(self, messages: list[Message]) -> LLMResponse:
        item = self._next(messages)
        self.calls += 1
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, type) and issubclass(item, BaseException):
            raise item()
        return LLMResponse(
            text=item,
            prompt_tokens=estimate_message_tokens(messages),
            completion_tokens=estimate_tokens(item),
        )


class MockLLMPolicy(LLMPolicy):
    def __init__(
        self,
        script: Sequence[str | BaseException | type[BaseException]] | Behavior,
        *,
        on_exhausted: str = "cycle",
        **kwargs: object,
    ) -> None:
        self.scripted = ScriptedLLM(script, on_exhausted=on_exhausted)
        super().__init__(self.scripted, **kwargs)  # type: ignore[arg-type]


# -- scenario behaviors ---------------------------------------------------------


def _greedy_reply(obs: Observation) -> str:
    return GreedyPolicy().choose(obs)


def valid(seed: int) -> Behavior:
    return lambda i, obs: _greedy_reply(obs)


def malformed_then_valid(seed: int, every: int = 4) -> Behavior:
    def behave(i: int, obs: Observation) -> str:
        if i % every == every - 1:
            return "I would head north towards the nearest SKU"
        return _greedy_reply(obs)

    return behave


def flaky_timeouts(seed: int, every: int = 3) -> Behavior:
    def behave(i: int, obs: Observation) -> str | BaseException:
        if i % every == every - 1:
            return TimeoutError("simulated provider timeout")
        return _greedy_reply(obs)

    return behave


def noisy(seed: int, p_wrong: float = 0.3) -> Behavior:
    rng = random.Random(seed)

    def behave(i: int, obs: Observation) -> str:
        if rng.random() < p_wrong:
            return rng.choice(VALID_MOVES)
        return _greedy_reply(obs)

    return behave


def oscillating(seed: int) -> Behavior:
    return lambda i, obs: "E" if i % 2 == 0 else "W"


def garbage(seed: int) -> Behavior:
    return lambda i, obs: "I am unable to decide on a direction."


def outage_then_recovery(seed: int, start: int = 10, end: int = 40) -> Behavior:
    def behave(i: int, obs: Observation) -> str | BaseException:
        if start <= obs.steps_taken < end:
            return ConnectionError("simulated provider outage")
        return _greedy_reply(obs)

    return behave


SCENARIOS: dict[str, Callable[[int], Behavior]] = {
    "valid": valid,
    "malformed-then-valid": malformed_then_valid,
    "flaky-timeouts": flaky_timeouts,
    "noisy-30pct": noisy,
    "oscillating": oscillating,
    "garbage": garbage,
    "outage-then-recovery": outage_then_recovery,
}

def scenario_factory(
    name: str,
    *,
    max_retries: int = 3,
    breaker_threshold: int = 5,
    breaker_reset_ticks: float = 25.0,
) -> PolicyFactory:
    """Per-episode policy: ScriptedLLM -> metered -> resilient (timeout, retries, breaker).

    The breaker uses a logical clock that advances one tick per ``choose`` call,
    and backoff sleeps are no-ops, so a run is fast and fully deterministic.
    State (breaker, clock, RNG) is per episode, never shared across threads.
    """

    def factory(ctx: EpisodeContext) -> LLMPolicy:
        ticks = [0.0]
        breaker = CircuitBreaker(breaker_threshold, breaker_reset_ticks, clock=lambda: ticks[0])
        llm = build_llm_stack(
            ScriptedLLM(SCENARIOS[name](ctx.seed)),
            ledger=ctx.ledger,
            episode_id=ctx.episode_id,
            model=MOCK_MODEL,
            timeout_s=5.0,
            max_retries=max_retries,
            breaker=breaker,
            sleep=lambda s: None,
            rand=random.Random(ctx.seed).random,
        )
        return LLMPolicy(llm, tracer=ctx.tracer, tick=lambda: ticks.__setitem__(0, ticks[0] + 1))

    return factory


__all__ = [
    "MOCK_MODEL",
    "MOCK_PRICE",
    "SCENARIOS",
    "LLMFn",
    "MockLLMPolicy",
    "ScriptedLLM",
    "observation_from_messages",
]
