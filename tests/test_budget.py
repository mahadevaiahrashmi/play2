"""budget: reserve-before-call / settle-after, ceilings, per-model report, concurrency."""

import threading

import pytest

from warehouse_routing.budget import (
    BudgetExceeded,
    BudgetLedger,
    Limits,
    MeteredLLM,
    Price,
)
from warehouse_routing.llm_types import LLMResponse

PRICES = {"m": Price(input_per_1k=1.0, output_per_1k=2.0)}  # $/1k tokens (test values)


def test_reservation_is_upper_bound_and_settles_to_actual() -> None:
    ledger = BudgetLedger(prices=PRICES)
    res = ledger.reserve("e1", "m", prompt_tokens=100, max_completion_tokens=10)
    # 100 * $1/1k + 10 * $2/1k = $0.12
    assert res.cost == pytest.approx(0.12)
    assert ledger.report()["run"]["reserved_cost"] == pytest.approx(0.12)
    cost = ledger.settle(res, LLMResponse("N", prompt_tokens=90, completion_tokens=1))
    assert cost == pytest.approx(0.092)
    rep = ledger.report()
    assert rep["run"]["reserved_cost"] == 0
    assert rep["run"]["cost"] == pytest.approx(0.092)
    assert rep["run"]["tokens"] == 91
    assert rep["open_reservations"] == 0


def test_settle_without_usage_charges_full_reservation() -> None:
    ledger = BudgetLedger(prices=PRICES)
    res = ledger.reserve("e1", "m", 100, 10)
    assert ledger.settle(res, None) == pytest.approx(0.12)


def test_release_refunds_and_double_settle_rejected() -> None:
    ledger = BudgetLedger(prices=PRICES)
    res = ledger.reserve("e1", "m", 100, 10)
    ledger.release(res)
    assert ledger.report()["run"]["cost"] == 0
    assert ledger.report()["run"]["reserved_cost"] == 0
    with pytest.raises(ValueError):
        ledger.settle(res, None)


def test_unknown_model_is_an_error_not_free() -> None:
    with pytest.raises(KeyError):
        BudgetLedger(prices=PRICES).reserve("e", "other", 1, 1)


def test_episode_token_ceiling_is_independent_per_episode() -> None:
    ledger = BudgetLedger(prices=PRICES, episode_limits=Limits(max_tokens=100))
    r = ledger.reserve("e1", "m", 60, 20)
    with pytest.raises(BudgetExceeded) as exc:
        ledger.reserve("e1", "m", 30, 20)  # 80 + 50 > 100 (reserved counts)
    assert (exc.value.scope, exc.value.resource) == ("episode", "tokens")
    ledger.reserve("e2", "m", 60, 20)  # other episode unaffected
    ledger.settle(r, LLMResponse("N", 10, 1))
    ledger.reserve("e1", "m", 30, 20)  # headroom returned after settle


def test_run_cost_ceiling() -> None:
    ledger = BudgetLedger(prices=PRICES, run_limits=Limits(max_cost=0.25))
    ledger.reserve("e1", "m", 100, 10)  # 0.12
    ledger.reserve("e2", "m", 100, 10)  # 0.24
    with pytest.raises(BudgetExceeded) as exc:
        ledger.reserve("e3", "m", 100, 10)
    assert (exc.value.scope, exc.value.resource) == ("run", "cost")


def test_exact_ceiling_is_allowed_no_float_drift() -> None:
    # 10 x $0.001 == $0.01 exactly (integer micro-dollar accounting)
    prices = {"m": Price(input_per_1k=1.0, output_per_1k=0.0)}
    ledger = BudgetLedger(prices=prices, run_limits=Limits(max_cost=0.01))
    for _ in range(10):
        ledger.reserve("e", "m", prompt_tokens=1, max_completion_tokens=0)
    with pytest.raises(BudgetExceeded):
        ledger.reserve("e", "m", 1, 0)


def test_step_ceilings_per_episode_and_per_run() -> None:
    ledger = BudgetLedger(
        prices=PRICES, episode_limits=Limits(max_steps=2), run_limits=Limits(max_steps=3)
    )
    ledger.charge_step("a")
    ledger.charge_step("a")
    with pytest.raises(BudgetExceeded) as exc:
        ledger.charge_step("a")
    assert (exc.value.scope, exc.value.resource) == ("episode", "steps")
    ledger.charge_step("b")
    with pytest.raises(BudgetExceeded) as exc2:
        ledger.charge_step("b")
    assert (exc2.value.scope, exc2.value.resource) == ("run", "steps")
    assert ledger.report()["run"]["steps"] == 3  # rejected steps are not counted


def test_per_model_report_is_sorted_and_aggregated() -> None:
    prices = {"b": Price(1.0, 1.0), "a": Price(1.0, 1.0)}
    ledger = BudgetLedger(prices=prices)
    for model in ("b", "a", "b"):
        r = ledger.reserve("e", model, 10, 2)
        ledger.settle(r, LLMResponse("N", 10, 1))
    models = ledger.report()["models"]
    assert list(models) == ["a", "b"]
    assert models["b"]["calls"] == 2 and models["b"]["prompt_tokens"] == 20
    assert models["a"]["calls"] == 1


def test_overshoot_beyond_reservation_is_recorded_not_hidden() -> None:
    ledger = BudgetLedger(prices=PRICES)
    r = ledger.reserve("e", "m", 10, 1)
    ledger.settle(r, LLMResponse("N", 10, 50))  # provider ignored max_tokens
    rep = ledger.report()
    assert rep["run"]["tokens"] == 60
    assert rep["overshoots"] == 1


def test_concurrent_reservations_never_overspend() -> None:
    # each reservation costs $1.00 (1000 tokens at $1/1k); run ceiling allows exactly 50
    prices = {"m": Price(input_per_1k=1.0, output_per_1k=0.0)}
    ledger = BudgetLedger(prices=prices, run_limits=Limits(max_cost=50.0))
    n_threads = 200
    barrier = threading.Barrier(n_threads)
    granted: list[object] = []
    denied: list[int] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        barrier.wait()
        try:
            r = ledger.reserve(f"e{i % 7}", "m", prompt_tokens=1000, max_completion_tokens=0)
        except BudgetExceeded:
            with lock:
                denied.append(i)
            return
        with lock:
            granted.append(r)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(granted) == 50
    assert len(denied) == 150
    assert ledger.report()["run"]["reserved_cost"] == pytest.approx(50.0)
    for r in granted:
        ledger.settle(r, LLMResponse("N", 400, 0))  # type: ignore[arg-type]
    rep = ledger.report()
    assert rep["run"]["cost"] == pytest.approx(20.0)
    assert rep["run"]["reserved_cost"] == 0
    assert rep["open_reservations"] == 0


def test_metered_llm_settles_actual_usage_and_charges_on_failure() -> None:
    ledger = BudgetLedger(prices=PRICES)

    def ok(messages: list[dict[str, str]]) -> LLMResponse:
        return LLMResponse("N", prompt_tokens=7, completion_tokens=1)

    metered = MeteredLLM(ok, ledger, episode_id="e", model="m", max_completion_tokens=4)
    assert metered([{"role": "user", "content": "hello world"}]).text == "N"
    assert ledger.report()["run"]["tokens"] == 8

    def boom(messages: list[dict[str, str]]) -> LLMResponse:
        raise ConnectionError("down")

    bad = MeteredLLM(boom, ledger, episode_id="e", model="m", max_completion_tokens=4)
    with pytest.raises(ConnectionError):
        bad([{"role": "user", "content": "x" * 40}])
    rep = ledger.report()
    assert rep["open_reservations"] == 0
    # failed call is charged its full reservation (10 prompt est + 4 completion)
    assert rep["run"]["tokens"] == 8 + 10 + 4


def test_metered_llm_refuses_before_calling_when_over_budget() -> None:
    ledger = BudgetLedger(prices=PRICES, run_limits=Limits(max_tokens=5))
    called = {"n": 0}

    def fn(messages: list[dict[str, str]]) -> LLMResponse:
        called["n"] += 1
        return LLMResponse("N", 1, 1)

    metered = MeteredLLM(fn, ledger, episode_id="e", model="m", max_completion_tokens=4)
    with pytest.raises(BudgetExceeded):
        metered([{"role": "user", "content": "x" * 100}])
    assert called["n"] == 0
