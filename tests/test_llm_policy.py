"""LLMPolicy + ScriptedLLM/MockLLMPolicy + the composed resilient/metered stack."""

import logging
from types import SimpleNamespace

import pytest

from warehouse_routing.budget import BudgetExceeded, BudgetLedger, Limits, Price
from warehouse_routing.eval import evaluate_tiers
from warehouse_routing.llm_policy import (
    HISTORY_WINDOW,
    SYSTEM_PROMPT,
    LLMPolicy,
    build_llm_stack,
    build_messages,
    openai_llm_fn,
)
from warehouse_routing.mock_llm import (
    MOCK_MODEL,
    SCENARIOS,
    MockLLMPolicy,
    ScriptedLLM,
    observation_from_messages,
)
from warehouse_routing.models import Cell, Observation
from warehouse_routing.policies import GreedyPolicy
from warehouse_routing.resilient_llm import CircuitBreaker
from warehouse_routing.tasks import EASY, make_variation
from warehouse_routing.tracing import Tracer


def obs0() -> Observation:
    return make_variation(EASY, seed=1).observation


def test_prompt_matches_inference_py_format_and_roundtrips() -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import inference

    assert inference.SYSTEM_PROMPT == SYSTEM_PROMPT and inference.HISTORY_WINDOW == HISTORY_WINDOW
    o = obs0()
    msgs = build_messages(o, [{"action": "E", "reward": -0.01}])
    assert msgs[0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert msgs[1]["content"].startswith("recent_moves: E->r=-0.01\nstate: ")
    assert observation_from_messages(msgs) == o


def test_scripted_reply_list_is_consumed_in_order_and_raises_exceptions() -> None:
    llm = ScriptedLLM(["E", TimeoutError("t"), ConnectionError], on_exhausted="last")
    msgs = build_messages(obs0(), [])
    assert llm(msgs).text == "E"
    with pytest.raises(TimeoutError):
        llm(msgs)
    with pytest.raises(ConnectionError):
        llm(msgs)
    assert llm.calls == 3
    with pytest.raises(ConnectionError):
        llm(msgs)  # "last" repeats the final entry
    strict = ScriptedLLM(["N"], on_exhausted="error")
    strict(msgs)
    with pytest.raises(IndexError):
        strict(msgs)


def test_valid_reply_returns_move_and_counts_calls() -> None:
    policy = MockLLMPolicy(["S"])
    assert policy.choose(obs0()) == "S"
    assert (policy.llm_calls, policy.parse_failures, policy.fallbacks) == (1, 0, 0)


def test_malformed_reply_is_retried_with_error_in_next_prompt() -> None:
    policy = MockLLMPolicy(["maybe north", "N"])
    seen: list[list[dict[str, str]]] = []
    inner = policy.scripted

    def spy(messages: list[dict[str, str]]):  # type: ignore[no-untyped-def]
        seen.append(messages)
        return inner(messages)

    policy._llm = spy  # type: ignore[assignment]
    assert policy.choose(obs0()) == "N"
    assert policy.parse_failures == 1 and policy.fallbacks == 0
    assert "invalid" in seen[1][-1]["content"] and "maybe north" in seen[1][-2]["content"]


def test_exhausted_retries_use_explicit_fallback_and_log(caplog: pytest.LogCaptureFixture) -> None:
    policy = MockLLMPolicy(["nonsense"], max_retries=1)
    o = obs0()  # robot at (0,0): fallback bumps the north wall
    with caplog.at_level(logging.WARNING):
        move = policy.choose(o)
    assert move == "N"
    assert policy.fallbacks == 1 and policy.parse_failures == 2 and policy.llm_calls == 2
    assert len([r for r in caplog.records if "invalid LLM reply" in r.getMessage()]) == 2


def test_transport_failures_after_retries_fall_back_not_crash() -> None:
    raw = ScriptedLLM([ConnectionError("down")])
    llm = build_llm_stack(raw, timeout_s=None, max_retries=2, sleep=lambda s: None)
    policy = LLMPolicy(llm)
    assert policy.choose(obs0()) == "N"
    assert policy.call_errors == 1 and policy.fallbacks == 1
    assert raw.calls == 3


def test_transient_error_is_retried_inside_stack_then_succeeds() -> None:
    raw = ScriptedLLM([TimeoutError("t"), "E"])
    policy = LLMPolicy(build_llm_stack(raw, timeout_s=None, sleep=lambda s: None))
    assert policy.choose(obs0()) == "E"
    assert policy.fallbacks == 0 and raw.calls == 2


def test_budget_exceeded_propagates_and_is_not_swallowed() -> None:
    ledger = BudgetLedger(prices={MOCK_MODEL: Price(1.0, 1.0)}, run_limits=Limits(max_tokens=5))
    stack = build_llm_stack(ScriptedLLM(["E"]), ledger=ledger, model=MOCK_MODEL,
                            timeout_s=None, sleep=lambda s: None)
    with pytest.raises(BudgetExceeded):
        LLMPolicy(stack).choose(obs0())


def test_open_circuit_causes_fallbacks_without_calling_the_model() -> None:
    t = {"now": 0.0}
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=100.0, clock=lambda: t["now"])
    raw = ScriptedLLM([ConnectionError("down")])
    policy = LLMPolicy(build_llm_stack(raw, timeout_s=None, max_retries=5, breaker=breaker,
                                       sleep=lambda s: None))
    for _ in range(3):
        policy.choose(obs0())
    assert raw.calls == 2  # opened after 2 failures; later steps never reach the model
    assert policy.fallbacks == 3 and breaker.state == "open"


def test_oscillating_script_triggers_prompt_and_state_alerts() -> None:
    tracer = Tracer(loop_threshold=3)
    policy = MockLLMPolicy(SCENARIOS["oscillating"](0), tracer=tracer)
    from warehouse_routing.runner import EvalRunner, RunConfig

    result = EvalRunner(
        {"osc": lambda ctx: MockLLMPolicy(SCENARIOS["oscillating"](0), tracer=ctx.tracer)},
        RunConfig(tiers=("easy",), seeds=(0,), max_workers=1),
        tracer=tracer,
    ).run()
    rec = result.records[0]
    assert rec.final_score == 0.0 and not rec.success
    kinds = {a["kind"] for a in tracer.report()["alerts"]}
    assert kinds == {"state", "prompt"}
    assert policy.fallbacks == 0


def test_scenarios_are_deterministic_and_valid_scenario_equals_greedy() -> None:
    def run(name: str) -> list[tuple[str, int, float]]:
        report = evaluate_tiers(
            lambda: MockLLMPolicy(SCENARIOS[name](0)), n_per_tier=2, base_seed=0
        )
        return [(e.tier, e.seed, e.score) for e in report.episodes]

    assert run("valid") == run("valid")
    greedy = evaluate_tiers(GreedyPolicy, n_per_tier=2, base_seed=0)
    # a model that always answers with the greedy move must score exactly like GreedyPolicy
    assert run("valid") == [(e.tier, e.seed, e.score) for e in greedy.episodes]
    assert run("noisy-30pct") == run("noisy-30pct")  # seeded
    assert all(score == 0.0 for _, _, score in run("garbage"))


def test_every_scenario_name_builds_a_working_behavior() -> None:
    for name, factory in SCENARIOS.items():
        policy = MockLLMPolicy(factory(0), max_retries=1)
        assert policy.choose(obs0()) in ("N", "S", "E", "W"), name


def test_openai_adapter_maps_content_and_usage() -> None:
    calls: list[dict] = []

    class Completions:
        def create(self, **kw):  # type: ignore[no-untyped-def]
            calls.append(kw)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="W"))],
                usage=SimpleNamespace(prompt_tokens=11, completion_tokens=1),
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    resp = openai_llm_fn(client, "m")([{"role": "user", "content": "x"}])
    assert (resp.text, resp.prompt_tokens, resp.completion_tokens) == ("W", 11, 1)
    assert calls[0]["model"] == "m" and calls[0]["temperature"] == 0.0


def test_history_resets_between_episodes() -> None:
    policy = LLMPolicy(ScriptedLLM(["E"]))
    o = obs0()
    policy.choose(o)
    policy.record("E", -0.01)
    later = o.model_copy(update={"steps_taken": 1, "robot_pos": Cell(row=0, col=1)})
    policy.choose(later)
    assert len(policy.history) == 1
    policy.choose(o)  # steps_taken went backwards -> new episode
    assert policy.history == []


def test_scenario_factory_outage_opens_breaker_then_recovers() -> None:
    from warehouse_routing.mock_llm import MOCK_PRICE, scenario_factory
    from warehouse_routing.runner import EvalRunner, RunConfig

    ledger = BudgetLedger(prices={MOCK_MODEL: MOCK_PRICE})
    runner = EvalRunner(
        {"sim": scenario_factory("outage-then-recovery")},
        RunConfig(tiers=("medium",), seeds=(0,), max_workers=1),
        ledger=ledger, tracer=Tracer(),
    )
    rec = runner.run().records[0]
    assert 0 < rec.fallbacks < len(rec.steps)  # degraded during the outage, healthy after
    assert rec.cost > 0
    # the breaker short-circuited: far fewer model calls than steps x (retries+1) during outage
    attempts_during_outage = 30 * 4
    assert ledger.report()["models"][MOCK_MODEL]["calls"] < len(rec.steps) + attempts_during_outage


def test_scenario_runs_are_reproducible() -> None:
    from warehouse_routing.mock_llm import MOCK_PRICE, scenario_factory
    from warehouse_routing.runner import EvalRunner, RunConfig

    def go() -> list[str]:
        runner = EvalRunner(
            {n: scenario_factory(n) for n in ("noisy-30pct", "flaky-timeouts")},
            RunConfig(tiers=("easy", "medium"), seeds=(0, 1), max_workers=3),
            ledger=BudgetLedger(prices={MOCK_MODEL: MOCK_PRICE}), tracer=Tracer(),
        )
        return [r.to_json() for r in runner.run().records]

    assert go() == go()
