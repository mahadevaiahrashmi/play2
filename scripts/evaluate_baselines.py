#!/usr/bin/env python
"""Evaluate the offline baseline policies (random, greedy, oracle) on every tier.

    uv run python scripts/evaluate_baselines.py [--n-per-tier 20] [--base-seed 0]

No API key or network needed. Prints a markdown score table.
"""

from __future__ import annotations

import argparse
import random

from warehouse_routing.eval import evaluate_tiers
from warehouse_routing.policies import GreedyPolicy, OraclePolicy, RandomPolicy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-per-tier", type=int, default=20)
    parser.add_argument("--base-seed", type=int, default=0)
    args = parser.parse_args()

    factories = {
        "Random": lambda: RandomPolicy(rng=random.Random(args.base_seed)),
        "Greedy (nearest-neighbour)": GreedyPolicy,
        "Oracle (exact TSP)": OraclePolicy,
    }

    print(
        f"Seeds {args.base_seed}..{args.base_seed + args.n_per_tier - 1}, "
        f"{args.n_per_tier} variations per tier\n"
    )
    print("| Policy | Easy | Medium | Hard | Overall mean | Success rate |")
    print("|--------|------|--------|------|--------------|--------------|")
    for label, factory in factories.items():
        report = evaluate_tiers(factory, n_per_tier=args.n_per_tier, base_seed=args.base_seed)
        t = report.by_tier()
        print(
            f"| {label} | {t['easy']:.3f} | {t['medium']:.3f} | {t['hard']:.3f} "
            f"| {report.mean_score:.3f} | {report.success_rate:.2f} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
