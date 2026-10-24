# agent-notes: { ctx: "Oracle policy scores 1.0, Random is bounded; cross-checks solver+sim+grader", deps: [src/warehouse_routing/policies.py, src/warehouse_routing/eval.py], state: active, last: "sato@2026-04-14" }
"""Baseline policy tests.

The OraclePolicy tests double as an integration check: if the solver,
A*, sim, or grader drift apart, the oracle stops scoring 1.0 on tiers
it should trivially solve.
"""

import random

from warehouse_routing.eval import evaluate
from warehouse_routing.policies import OraclePolicy, RandomPolicy


def test_oracle_scores_one_on_easy_variations() -> None:
    report = evaluate(OraclePolicy(), master_seed=0, max_variations=5, time_limit_seconds=None)
    assert report.n == 5
    assert report.success_rate == 1.0
    assert all(e.score == 1.0 for e in report.episodes)


def test_oracle_clears_curriculum() -> None:
    # 3-in-a-row mastery per tier, 3 tiers -> at least 9 variations, then done.
    report = evaluate(OraclePolicy(), master_seed=7, time_limit_seconds=None)
    assert report.n >= 9
    assert report.mean_score == 1.0
    tiers = {e.tier for e in report.episodes}
    assert tiers == {"easy", "medium", "hard"}


def test_random_policy_is_bounded() -> None:
    report = evaluate(
        RandomPolicy(rng=random.Random(0)),
        master_seed=0,
        max_variations=6,
        time_limit_seconds=None,
    )
    assert report.n == 6
    for e in report.episodes:
        assert 0.0 <= e.score <= 1.0


def test_greedy_solves_every_tier_and_is_near_optimal() -> None:
    from warehouse_routing.eval import evaluate_tiers
    from warehouse_routing.policies import GreedyPolicy

    report = evaluate_tiers(GreedyPolicy, n_per_tier=3, base_seed=0)
    assert report.n == 9
    assert report.success_rate == 1.0
    assert all(0.0 < e.score <= 1.0 for e in report.episodes)
    assert report.mean_score > 0.8


def test_evaluate_tiers_oracle_is_perfect_and_deterministic() -> None:
    from warehouse_routing.eval import evaluate_tiers

    a = evaluate_tiers(OraclePolicy, n_per_tier=2, base_seed=5)
    b = evaluate_tiers(OraclePolicy, n_per_tier=2, base_seed=5)
    assert a.n == 6 and a.mean_score == 1.0
    assert [e.steps for e in a.episodes] == [e.steps for e in b.episodes]
