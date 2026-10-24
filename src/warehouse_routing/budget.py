"""Cost governance: a thread-safe reserve/settle ledger with hard ceilings.

Contract
--------
* Ceilings (tokens, cost, steps) can be set per episode and per run
  (``Limits``; ``None`` = unlimited).
* ``reserve()`` is called *before* an LLM call with the prompt token count and
  the maximum completion tokens. It computes a worst-case cost and, under one
  lock, checks ``committed + already_reserved + this`` against every ceiling.
  Either the reservation is granted atomically or ``BudgetExceeded`` is
  raised, so concurrent callers can never collectively overspend.
* ``settle()`` replaces the reservation with actual usage. ``settle(res,
  None)`` charges the full reservation (used when a call failed or timed out:
  the provider may still bill, so we stay conservative). ``release()`` refunds
  with no charge (call provably never sent).
* If a provider returns more tokens than reserved, the true usage is recorded
  and counted in ``overshoots`` (the ceiling can then be exceeded by that
  delta; we never hide it).
* Money is tracked in integer micro-dollars, so a ceiling of exactly N calls
  is exact (no float drift). Prices are $ per 1k tokens, supplied by the
  caller; an unknown model raises ``KeyError`` rather than being free.
* ``MeteredLLM`` wraps an LLM function with reserve -> call -> settle.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from warehouse_routing.llm_types import LLMFn, LLMResponse, Message, estimate_message_tokens

_MICRO = 1_000_000


@dataclass(frozen=True)
class Price:
    """USD per 1,000 tokens."""

    input_per_1k: float
    output_per_1k: float

    def micro_cost(self, prompt_tokens: int, completion_tokens: int) -> int:
        return round(
            prompt_tokens * self.input_per_1k * 1000 + completion_tokens * self.output_per_1k * 1000
        )


@dataclass(frozen=True)
class Limits:
    max_tokens: int | None = None
    max_cost: float | None = None  # USD
    max_steps: int | None = None


class BudgetExceeded(RuntimeError):
    def __init__(self, scope: str, resource: str, detail: str = "") -> None:
        self.scope = scope
        self.resource = resource
        super().__init__(f"{scope} {resource} budget exceeded{': ' + detail if detail else ''}")


@dataclass(frozen=True)
class Reservation:
    id: int
    episode_id: str
    model: str
    prompt_tokens: int
    max_completion_tokens: int
    micro_cost: int

    @property
    def tokens(self) -> int:
        return self.prompt_tokens + self.max_completion_tokens

    @property
    def cost(self) -> float:
        return self.micro_cost / _MICRO


@dataclass
class _Scope:
    tokens: int = 0
    micro: int = 0
    steps: int = 0
    reserved_tokens: int = 0
    reserved_micro: int = 0

    def view(self) -> dict[str, Any]:
        return {
            "tokens": self.tokens,
            "cost": self.micro / _MICRO,
            "steps": self.steps,
            "reserved_tokens": self.reserved_tokens,
            "reserved_cost": self.reserved_micro / _MICRO,
        }


@dataclass
class _ModelUsage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    micro: int = 0


@dataclass
class BudgetLedger:
    prices: dict[str, Price]
    run_limits: Limits = field(default_factory=Limits)
    episode_limits: Limits = field(default_factory=Limits)

    def __post_init__(self) -> None:
        self._lock = threading.Lock()
        self._run = _Scope()
        self._episodes: dict[str, _Scope] = defaultdict(_Scope)
        self._models: dict[str, _ModelUsage] = defaultdict(_ModelUsage)
        self._open: dict[int, Reservation] = {}
        self._next_id = 1
        self._overshoots = 0

    # -- checks -----------------------------------------------------------
    @staticmethod
    def _check(scope_name: str, scope: _Scope, limits: Limits, tokens: int, micro: int) -> None:
        if limits.max_tokens is not None and (
            scope.tokens + scope.reserved_tokens + tokens > limits.max_tokens
        ):
            raise BudgetExceeded(scope_name, "tokens", f"limit {limits.max_tokens}")
        if limits.max_cost is not None and (
            scope.micro + scope.reserved_micro + micro > round(limits.max_cost * _MICRO)
        ):
            raise BudgetExceeded(scope_name, "cost", f"limit ${limits.max_cost}")

    # -- API ---------------------------------------------------------------
    def reserve(
        self, episode_id: str, model: str, prompt_tokens: int, max_completion_tokens: int
    ) -> Reservation:
        price = self.prices[model]  # KeyError on unknown model: never silently free
        micro = price.micro_cost(prompt_tokens, max_completion_tokens)
        tokens = prompt_tokens + max_completion_tokens
        with self._lock:
            ep = self._episodes[episode_id]
            self._check("episode", ep, self.episode_limits, tokens, micro)
            self._check("run", self._run, self.run_limits, tokens, micro)
            res = Reservation(
                self._next_id, episode_id, model, prompt_tokens, max_completion_tokens, micro
            )
            self._next_id += 1
            for scope in (ep, self._run):
                scope.reserved_tokens += tokens
                scope.reserved_micro += micro
            self._open[res.id] = res
            return res

    def _drop(self, res: Reservation) -> _Scope:
        if res.id not in self._open:
            raise ValueError(f"reservation {res.id} already settled or released")
        del self._open[res.id]
        ep = self._episodes[res.episode_id]
        for scope in (ep, self._run):
            scope.reserved_tokens -= res.tokens
            scope.reserved_micro -= res.micro_cost
        return ep

    def settle(self, res: Reservation, usage: LLMResponse | None) -> float:
        with self._lock:
            ep = self._drop(res)
            if usage is None:
                prompt, completion, micro = (
                    res.prompt_tokens,
                    res.max_completion_tokens,
                    res.micro_cost,
                )
            else:
                prompt, completion = usage.prompt_tokens, usage.completion_tokens
                micro = self.prices[res.model].micro_cost(prompt, completion)
                if prompt + completion > res.tokens or micro > res.micro_cost:
                    self._overshoots += 1
            for scope in (ep, self._run):
                scope.tokens += prompt + completion
                scope.micro += micro
            mu = self._models[res.model]
            mu.calls += 1
            mu.prompt_tokens += prompt
            mu.completion_tokens += completion
            mu.micro += micro
            return micro / _MICRO

    def release(self, res: Reservation) -> None:
        with self._lock:
            self._drop(res)

    def charge_step(self, episode_id: str) -> None:
        with self._lock:
            ep = self._episodes[episode_id]
            if self.episode_limits.max_steps is not None and ep.steps + 1 > self.episode_limits.max_steps:
                raise BudgetExceeded("episode", "steps", f"limit {self.episode_limits.max_steps}")
            if self.run_limits.max_steps is not None and self._run.steps + 1 > self.run_limits.max_steps:
                raise BudgetExceeded("run", "steps", f"limit {self.run_limits.max_steps}")
            ep.steps += 1
            self._run.steps += 1

    def episode_cost(self, episode_id: str) -> float:
        with self._lock:
            return self._episodes[episode_id].micro / _MICRO if episode_id in self._episodes else 0.0

    def report(self) -> dict[str, Any]:
        with self._lock:
            return {
                "run": self._run.view(),
                "episodes": {k: self._episodes[k].view() for k in sorted(self._episodes)},
                "models": {
                    k: {
                        "calls": v.calls,
                        "prompt_tokens": v.prompt_tokens,
                        "completion_tokens": v.completion_tokens,
                        "cost": v.micro / _MICRO,
                    }
                    for k, v in sorted(self._models.items())
                },
                "open_reservations": len(self._open),
                "overshoots": self._overshoots,
            }


class MeteredLLM:
    """reserve -> call -> settle around an LLM function (one episode, one model)."""

    def __init__(
        self,
        fn: LLMFn,
        ledger: BudgetLedger,
        *,
        episode_id: str,
        model: str,
        max_completion_tokens: int = 16,
    ) -> None:
        self._fn = fn
        self._ledger = ledger
        self._episode_id = episode_id
        self._model = model
        self._max_completion = max_completion_tokens

    def __call__(self, messages: list[Message]) -> LLMResponse:
        res = self._ledger.reserve(
            self._episode_id, self._model, estimate_message_tokens(messages), self._max_completion
        )
        try:
            response = self._fn(messages)
        except BaseException:
            self._ledger.settle(res, None)  # conservative: an abandoned call may still be billed
            raise
        self._ledger.settle(res, response)
        return response
