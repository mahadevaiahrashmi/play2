"""Deterministic leaderboard / report over episode records.

Contract
--------
* Input: finished ``EpisodeRecord``s plus the dead-lettered ``failures``.
  Output is a pure function of that input (record order does not matter; no
  timestamps), rendered as Markdown and canonical JSON.
* Dead-lettered episodes count as score 0 / not successful in ``n``,
  ``mean_score`` and ``success_rate`` (a policy that crashes must not look
  good), but have no steps and so are excluded from ``mean_steps``.
* ``optimality_gap`` = mean over *successful* episodes of
  ``steps / optimal_length - 1`` (``None`` if none succeeded).
* ``Fallbacks`` = steps where an LLM policy gave up and played the explicit
  fallback move; ``Loop alerts`` = tracer repeated-state/prompt alerts.
* Ranking: overall mean score (descending, compared at 9 decimals), ties
  broken by policy name ascending.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from warehouse_routing.episode_log import DeadLetter, EpisodeRecord

TIERS_DEFAULT = ("easy", "medium", "hard")


@dataclass
class PolicyRow:
    name: str
    per_tier: dict[str, dict[str, Any]]
    overall: dict[str, Any]
    cost: float
    failures: int
    fallbacks: int
    alerts: int = 0


@dataclass
class Leaderboard:
    tiers: tuple[str, ...]
    rows: list[PolicyRow]


def _stats(records: list[EpisodeRecord], n_failed: int) -> dict[str, Any]:
    n = len(records) + n_failed
    if n == 0:
        return {"n": 0, "mean_score": None, "success_rate": None, "mean_steps": None,
                "optimality_gap": None}
    ok = [r for r in records if r.success]
    gaps = [len(r.steps) / r.optimal_length - 1 for r in ok if r.optimal_length > 0]
    return {
        "n": n,
        "mean_score": sum(r.final_score for r in records) / n,
        "success_rate": len(ok) / n,
        "mean_steps": sum(len(r.steps) for r in records) / len(records) if records else None,
        "optimality_gap": sum(gaps) / len(gaps) if gaps else None,
    }


def build_leaderboard(
    records: list[EpisodeRecord],
    failures: list[DeadLetter],
    tiers: tuple[str, ...] = TIERS_DEFAULT,
) -> Leaderboard:
    by_policy: dict[str, list[EpisodeRecord]] = defaultdict(list)
    for r in records:
        by_policy[r.policy].append(r)
    failed: dict[str, list[DeadLetter]] = defaultdict(list)
    for f in failures:
        failed[f.policy].append(f)

    rows = []
    for name in sorted(set(by_policy) | set(failed)):
        recs = sorted(by_policy[name], key=lambda r: (r.tier, r.seed))
        per_tier = {
            t: _stats(
                [r for r in recs if r.tier == t],
                sum(1 for f in failed[name] if f.tier == t),
            )
            for t in tiers
        }
        rows.append(
            PolicyRow(
                name=name,
                per_tier=per_tier,
                overall=_stats(recs, len(failed[name])),
                cost=sum(r.cost for r in recs),
                failures=len(failed[name]),
                fallbacks=sum(r.fallbacks for r in recs),
                alerts=sum(r.alerts for r in recs),
            )
        )
    rows.sort(key=lambda r: (-round(r.overall["mean_score"] or 0.0, 9), r.name))
    return Leaderboard(tiers=tuple(tiers), rows=rows)


def _fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def to_markdown(board: Leaderboard) -> str:
    head = ["Rank", "Policy", *(t.capitalize() for t in board.tiers), "Mean score", "Success",
            "Mean steps", "Opt. gap", "Cost (USD)", "Fallbacks", "Loop alerts", "Failed"]
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    for i, row in enumerate(board.rows, 1):
        o = row.overall
        cells = [str(i), row.name, *(_fmt(row.per_tier[t]["mean_score"]) for t in board.tiers),
                 _fmt(o["mean_score"]), _fmt(o["success_rate"], 2), _fmt(o["mean_steps"], 1),
                 _fmt(o["optimality_gap"]), f"{row.cost:.4f}", str(row.fallbacks), str(row.alerts),
                 str(row.failures)]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "Per-tier detail:", "",
              "| Policy | Tier | n | Mean score | Success | Mean steps | Opt. gap |",
              "|---|---|---|---|---|---|---|"]
    for row in board.rows:
        for t in board.tiers:
            s = row.per_tier[t]
            lines.append(
                f"| {row.name} | {t} | {s['n']} | {_fmt(s['mean_score'])} | "
                f"{_fmt(s['success_rate'], 2)} | {_fmt(s['mean_steps'], 1)} | "
                f"{_fmt(s['optimality_gap'])} |"
            )
    return "\n".join(lines) + "\n"


def to_json(board: Leaderboard) -> str:
    payload = {
        "tiers": list(board.tiers),
        "rows": [
            {"name": r.name, "per_tier": r.per_tier, "overall": r.overall, "cost": r.cost,
             "failures": r.failures, "fallbacks": r.fallbacks, "alerts": r.alerts}
            for r in board.rows
        ],
    }
    return json.dumps(payload, sort_keys=True, indent=2)
