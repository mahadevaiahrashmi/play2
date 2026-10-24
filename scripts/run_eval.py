#!/usr/bin/env python
"""Run the full offline evaluation and print leaderboards. No API key, no network.

    uv run python scripts/run_eval.py [--seeds 10] [--workers 4] [--out-dir runs/latest]

Two runs are made and written side by side:

* offline policies: random, greedy (nearest-neighbour), oracle (exact TSP);
* SIMULATED LLM scenarios: a scripted fake model (``mock_llm``) that replies
  validly, malformed, times out, oscillates, etc. These measure how the
  platform's guards behave; they say nothing about any real model.

Artifacts in --out-dir: ``*-episodes.jsonl`` (replayable), ``*-dead-letters.jsonl``,
``*-leaderboard.{md,json}``, ``*-trace.json``, ``*-budget.json``. Re-running with the
same out-dir skips episodes already logged (idempotent run IDs).
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from pathlib import Path

from warehouse_routing.budget import BudgetLedger
from warehouse_routing.episode_log import DeadLetterLog, EpisodeLog, replay_episode
from warehouse_routing.leaderboard import build_leaderboard, to_json, to_markdown
from warehouse_routing.mock_llm import MOCK_MODEL, MOCK_PRICE, SCENARIOS, scenario_factory
from warehouse_routing.policies import GreedyPolicy, OraclePolicy, RandomPolicy
from warehouse_routing.runner import EvalRunner, RunConfig
from warehouse_routing.tracing import Tracer


def run_suite(label: str, factories: dict, args: argparse.Namespace, out: Path) -> str:
    log = EpisodeLog(out / f"{label}-episodes.jsonl")
    dead = DeadLetterLog(out / f"{label}-dead-letters.jsonl")
    tracer = Tracer(loop_threshold=5)
    ledger = BudgetLedger(prices={MOCK_MODEL: MOCK_PRICE})
    config = RunConfig(seeds=tuple(range(args.seeds)), max_workers=args.workers)
    result = EvalRunner(factories, config, log=log, dead=dead, tracer=tracer, ledger=ledger).run()
    board = build_leaderboard(result.records, result.failures, config.tiers)
    md = to_markdown(board)
    (out / f"{label}-leaderboard.md").write_text(md)
    (out / f"{label}-leaderboard.json").write_text(to_json(board) + "\n")
    (out / f"{label}-trace.json").write_text(json.dumps(tracer.report(), indent=2) + "\n")
    (out / f"{label}-budget.json").write_text(json.dumps(ledger.report(), indent=2) + "\n")
    for rec in result.records:  # every logged episode must replay to its logged score
        assert replay_episode(rec) == rec.final_score
    print(f"[{label}] executed={result.executed} skipped={result.skipped} "
          f"failed={len(result.failures)} replay_verified={len(result.records)}")
    return md


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=10, help="seeds per tier (0..N-1)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--verbose", action="store_true", help="show every invalid-reply warning")
    parser.add_argument("--out-dir", type=Path, default=Path("runs/latest"))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if not args.verbose:  # failed attempts are still counted in the leaderboard
        logging.getLogger("warehouse_routing.structured_action").setLevel(logging.ERROR)

    offline = {
        "random": lambda ctx: RandomPolicy(rng=random.Random(ctx.seed)),
        "greedy": lambda ctx: GreedyPolicy(),
        "oracle": lambda ctx: OraclePolicy(),
    }
    simulated = {f"sim-llm/{name}": scenario_factory(name) for name in SCENARIOS}

    md1 = run_suite("offline", offline, args, args.out_dir)
    md2 = run_suite("simulated-llm", simulated, args, args.out_dir)
    print(f"\n## Offline policies ({args.seeds} seeds per tier)\n\n{md1}")
    print(
        f"## Simulated LLM scenarios ({args.seeds} seeds per tier) -- scripted mock, "
        f"NOT a real model; cost uses illustrative prices\n\n{md2}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
