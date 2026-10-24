"""runner + leaderboard: composition, dedupe, dead letters, deterministic ordering."""

import json
import random
import threading
from pathlib import Path

import pytest

from warehouse_routing.budget import BudgetLedger, Limits, Price
from warehouse_routing.episode_log import (
    DeadLetter,
    DeadLetterLog,
    EpisodeLog,
    EpisodeRecord,
    StepRecord,
    replay_episode,
)
from warehouse_routing.leaderboard import build_leaderboard, to_json, to_markdown
from warehouse_routing.policies import GreedyPolicy, OraclePolicy, RandomPolicy
from warehouse_routing.runner import EpisodeContext, EvalRunner, RunConfig
from warehouse_routing.tracing import Tracer

FACTORIES = {
    "oracle": lambda ctx: OraclePolicy(),
    "greedy": lambda ctx: GreedyPolicy(),
    "random": lambda ctx: RandomPolicy(rng=random.Random(ctx.seed)),
}
CFG = RunConfig(tiers=("easy",), seeds=(0, 1, 2), max_workers=3)


def test_runs_policy_x_tier_x_seed_in_deterministic_order() -> None:
    result = EvalRunner(FACTORIES, RunConfig(tiers=("easy", "medium"), seeds=(0, 1))).run()
    keys = [(r.policy, r.tier, r.seed) for r in result.records]
    assert keys == [
        (p, t, s) for p in ("oracle", "greedy", "random") for t in ("easy", "medium") for s in (0, 1)
    ]
    assert all(r.final_score == 1.0 for r in result.records if r.policy == "oracle")
    assert all(r.final_score == 0.0 for r in result.records if r.policy == "random")
    assert result.executed == 12 and result.skipped == 0 and result.failures == []


def test_result_order_independent_of_completion_order() -> None:
    finished: list[int] = []
    events = {s: threading.Event() for s in (0, 1, 2)}

    def factory(ctx: EpisodeContext) -> OraclePolicy:
        # seed 0 may only start once seed 1 is done, which waits for seed 2: reverse completion
        if ctx.seed in (0, 1):
            assert events[ctx.seed + 1].wait(5), "deadlock: workers < 3?"
        return OraclePolicy()

    def on_done(seed: int) -> None:
        finished.append(seed)
        events[seed].set()

    runner = EvalRunner({"o": factory}, CFG, on_episode_done=lambda rec: on_done(rec.seed))
    # seed 2 finishes first, then 1, then 0
    result = runner.run()
    assert finished == [2, 1, 0]
    assert [r.seed for r in result.records] == [0, 1, 2]


def test_rerun_is_deduplicated_via_run_id(tmp_path: Path) -> None:
    log = EpisodeLog(tmp_path / "e.jsonl")
    first = EvalRunner(FACTORIES, CFG, log=log).run()
    assert first.executed == 9
    second = EvalRunner(FACTORIES, CFG, log=EpisodeLog(tmp_path / "e.jsonl")).run()
    assert second.executed == 0 and second.skipped == 9
    assert [r.to_json() for r in second.records] == [r.to_json() for r in first.records]
    assert len((tmp_path / "e.jsonl").read_text().splitlines()) == 9


def test_logged_episodes_replay_to_the_same_score(tmp_path: Path) -> None:
    log = EpisodeLog(tmp_path / "e.jsonl")
    EvalRunner(FACTORIES, CFG, log=log).run()
    for rec in log.load():
        assert replay_episode(rec) == rec.final_score


def test_failing_episode_is_retried_then_dead_lettered(tmp_path: Path) -> None:
    calls: dict[int, int] = {}

    def flaky(ctx: EpisodeContext) -> OraclePolicy:
        calls[ctx.seed] = calls.get(ctx.seed, 0) + 1
        if ctx.seed == 1:
            raise RuntimeError("provider exploded")
        return OraclePolicy()

    dead = DeadLetterLog(tmp_path / "dead.jsonl")
    cfg = RunConfig(tiers=("easy",), seeds=(0, 1, 2), max_workers=2, max_episode_attempts=3)
    result = EvalRunner({"flaky": flaky}, cfg, dead=dead).run()
    assert calls[1] == 3 and calls[0] == 1
    assert [r.seed for r in result.records] == [0, 2]
    assert len(result.failures) == 1
    entry = dead.load()[0]
    assert entry.seed == 1 and entry.attempts == 3 and "provider exploded" in entry.error


def test_dead_letters_can_be_replayed_once_fixed(tmp_path: Path) -> None:
    broken = {"on": True}

    def factory(ctx: EpisodeContext) -> OraclePolicy:
        if broken["on"] and ctx.seed == 1:
            raise RuntimeError("down")
        return OraclePolicy()

    dead = DeadLetterLog(tmp_path / "dead.jsonl")
    log = EpisodeLog(tmp_path / "e.jsonl")
    cfg = RunConfig(tiers=("easy",), seeds=(0, 1), max_workers=1, max_episode_attempts=1)
    runner = EvalRunner({"p": factory}, cfg, log=log, dead=dead)
    runner.run()
    assert len(dead.load()) == 1 and len(log.load()) == 1
    still_broken_ok, still_broken = runner.replay_dead_letters()  # outage persists
    assert still_broken_ok == [] and still_broken[0].attempts == 2
    broken["on"] = False  # provider recovers
    ok, still = runner.replay_dead_letters()
    assert still == [] and len(ok) == 1
    assert dead.load() == []
    assert sorted(r.seed for r in log.load()) == [0, 1]


def test_budget_exceeded_is_not_retried_and_is_dead_lettered(tmp_path: Path) -> None:
    n = {"c": 0}

    def factory(ctx: EpisodeContext) -> OraclePolicy:
        n["c"] += 1
        return OraclePolicy()

    ledger = BudgetLedger(prices={}, episode_limits=Limits(max_steps=3))
    cfg = RunConfig(tiers=("easy",), seeds=(0,), max_episode_attempts=3)
    result = EvalRunner({"p": factory}, cfg, ledger=ledger, dead=DeadLetterLog(tmp_path / "d")).run()
    assert n["c"] == 1  # no retry
    assert len(result.failures) == 1 and "steps budget" in result.failures[0].error
    assert result.failures[0].attempts == 1


def test_run_step_ceiling_stops_later_episodes() -> None:
    ledger = BudgetLedger(prices={}, run_limits=Limits(max_steps=40))
    cfg = RunConfig(tiers=("easy",), seeds=tuple(range(6)), max_workers=1)
    result = EvalRunner({"o": FACTORIES["oracle"]}, cfg, ledger=ledger).run()
    assert len(result.records) < 6 and len(result.failures) >= 1
    assert ledger.report()["run"]["steps"] <= 40


def test_tracer_sees_episodes_and_oscillation_alerts() -> None:
    class Oscillator:
        def __init__(self) -> None:
            self.i = 0

        def choose(self, obs):  # type: ignore[no-untyped-def]
            self.i += 1
            return "E" if self.i % 2 else "W"

    tracer = Tracer(loop_threshold=5)
    cfg = RunConfig(tiers=("easy",), seeds=(0,), max_workers=1)
    result = EvalRunner({"osc": lambda ctx: Oscillator()}, cfg, tracer=tracer).run()
    rec = result.records[0]
    assert rec.final_score == 0.0 and rec.alerts > 0
    rep = tracer.report()
    assert rep["episodes"][0]["episode_id"] == rec.run_id
    assert rep["span_summary"]["policy.choose"]["count"] == len(rec.steps)
    assert rep["alerts_total"] == rec.alerts


def test_cost_comes_from_ledger_per_episode() -> None:
    from warehouse_routing.llm_policy import LLMPolicy, build_llm_stack
    from warehouse_routing.mock_llm import MOCK_MODEL, SCENARIOS, ScriptedLLM

    ledger = BudgetLedger(prices={MOCK_MODEL: Price(1.0, 2.0)})

    def factory(ctx: EpisodeContext) -> LLMPolicy:
        raw = ScriptedLLM(SCENARIOS["valid"](ctx.seed))
        llm = build_llm_stack(raw, ledger=ledger, episode_id=ctx.episode_id, model=MOCK_MODEL,
                              timeout_s=None, sleep=lambda s: None)
        return LLMPolicy(llm, tracer=ctx.tracer)

    cfg = RunConfig(tiers=("easy",), seeds=(0, 1), max_workers=2)
    result = EvalRunner({"sim": factory}, cfg, ledger=ledger, tracer=Tracer()).run()
    assert all(r.cost > 0 and r.llm_calls == len(r.steps) for r in result.records)
    assert sum(r.cost for r in result.records) == pytest.approx(ledger.report()["run"]["cost"])


# -- leaderboard ----------------------------------------------------------------


def rec(policy: str, tier: str, seed: int, score: float, steps: int, opt: int = 10,
        success: bool | None = None, cost: float = 0.0, fallbacks: int = 0) -> EpisodeRecord:
    st = [StepRecord("N", (0, 0), [True], 0.0, False, False) for _ in range(steps)]
    return EpisodeRecord(
        run_id=f"{policy}{tier}{seed}", policy=policy, tier=tier, seed=seed, attempt=1,
        optimal_length=opt, steps=st, final_score=score,
        success=score > 0 if success is None else success, cost=cost, fallbacks=fallbacks,
    )


def test_leaderboard_ranks_by_mean_score_and_breaks_ties_by_name() -> None:
    records = [
        rec("zeta", "easy", 0, 1.0, 10), rec("alpha", "easy", 0, 1.0, 10),
        rec("mid", "easy", 0, 0.5, 20), rec("low", "easy", 0, 0.0, 64),
    ]
    board = build_leaderboard(records, [], tiers=("easy",))
    assert [r.name for r in board.rows] == ["alpha", "zeta", "mid", "low"]


def test_leaderboard_metrics_gap_steps_success_cost_and_failures() -> None:
    records = [
        rec("p", "easy", 0, 0.5, 20, opt=10, cost=0.25, fallbacks=2),
        rec("p", "easy", 1, 1.0, 10, opt=10, cost=0.25),
        rec("p", "easy", 2, 0.0, 64, opt=10, success=False),
    ]
    failures = [DeadLetter("x", "p", "easy", 3, "boom", 2)]
    row = build_leaderboard(records, failures, tiers=("easy",)).rows[0]
    easy = row.per_tier["easy"]
    assert easy["n"] == 4  # the dead-lettered episode counts, as a zero
    assert easy["mean_score"] == pytest.approx((0.5 + 1.0 + 0 + 0) / 4)
    assert easy["success_rate"] == pytest.approx(2 / 4)
    assert easy["mean_steps"] == pytest.approx((20 + 10 + 64) / 3)  # failures have no steps
    # gap over successful episodes only: (20/10-1 + 10/10-1)/2
    assert easy["optimality_gap"] == pytest.approx(0.5)
    assert row.cost == pytest.approx(0.5) and row.failures == 1 and row.fallbacks == 2
    assert row.alerts == 0


def test_gap_is_none_when_nothing_succeeded() -> None:
    row = build_leaderboard([rec("p", "easy", 0, 0.0, 64, success=False)], [], ("easy",)).rows[0]
    assert row.per_tier["easy"]["optimality_gap"] is None


def test_outputs_are_deterministic_and_well_formed() -> None:
    records = [rec("b", "easy", 0, 1.0, 10), rec("a", "easy", 0, 0.5, 20)]
    board1 = build_leaderboard(records, [], ("easy", "medium"))
    board2 = build_leaderboard(list(reversed(records)), [], ("easy", "medium"))
    assert to_markdown(board1) == to_markdown(board2)
    assert to_json(board1) == to_json(board2)
    data = json.loads(to_json(board1))
    assert [r["name"] for r in data["rows"]] == ["b", "a"]
    md = to_markdown(board1)
    assert md.splitlines()[0].startswith("| Rank | Policy |")
    assert "| 1 | b |" in md
    assert "—" in md  # medium tier has no episodes


def test_cli_script_runs_offline_and_rerun_is_deduplicated(tmp_path: Path) -> None:
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[1] / "scripts" / "run_eval.py"
    cmd = [sys.executable, str(script), "--seeds", "1", "--workers", "2", "--out-dir", str(tmp_path)]
    env = {"PATH": "/usr/bin:/bin"}  # deliberately no API keys
    first = subprocess.run(cmd, capture_output=True, text=True, env=env, check=True).stdout
    assert "[offline] executed=9 skipped=0 failed=0 replay_verified=9" in first
    assert "[simulated-llm] executed=21 skipped=0 failed=0" in first
    assert "scripted mock, NOT a real model" in first
    assert (tmp_path / "offline-leaderboard.md").exists()
    assert json.loads((tmp_path / "simulated-llm-leaderboard.json").read_text())["rows"]
    second = subprocess.run(cmd, capture_output=True, text=True, env=env, check=True).stdout
    assert "[offline] executed=0 skipped=9" in second
