# Baseline Scores

All numbers below were produced offline (no API key, no network) by the code in
this repo. `score = optimal_length / agent_length`, 0 if the episode fails.

## Offline policies across all tiers

Reproduce:

```
uv run python scripts/evaluate_baselines.py --n-per-tier 20 --base-seed 0
```

Seeds 0..19, 20 variations per tier (60 episodes per policy), fixed seeds so the
table is deterministic:

| Policy | Easy | Medium | Hard | Overall mean | Success rate |
|--------|------|--------|------|--------------|--------------|
| Random | 0.000 | 0.000 | 0.000 | 0.000 | 0.00 |
| Greedy (nearest-neighbour) | 0.979 | 0.948 | 0.895 | 0.941 | 1.00 |
| Oracle (exact TSP) | 1.000 | 1.000 | 1.000 | 1.000 | 1.00 |

- **Random** (uniform N/S/E/W) never completes a tour within the step budget.
- **Greedy** always walks (A*-routed) to the nearest unvisited SKU, then home.
  It solves every episode but loses efficiency as SKU count and obstacles grow
  (0.979 → 0.895), so there is headroom for a learned/LLM agent on Hard.
- **Oracle** replays the exact Held-Karp tour. It scores 1.0 by construction and
  doubles as a regression check: if `solver`, `pathing`, `sim`, or `grader`
  drift apart, it stops scoring 1.0.

## Curriculum run (first 9 episodes, master seed 0)

Drives each policy through `warehouse_routing.eval.evaluate` (adaptive
curriculum: promote after 3 consecutive scores ≥ 0.9).

```
python -c "
import random
from warehouse_routing.eval import evaluate
from warehouse_routing.policies import GreedyPolicy, OraclePolicy, RandomPolicy
for label, policy in [('Oracle', OraclePolicy()), ('Greedy', GreedyPolicy()), ('Random', RandomPolicy(rng=random.Random(0)))]:
    r = evaluate(policy, master_seed=0, max_variations=9, time_limit_seconds=None)
    print(label, r.n, round(r.mean_score, 3), r.success_rate, r.by_tier())
"
```

| Policy | n | mean_score | success_rate | easy | medium | hard |
|--------|---|------------|--------------|------|--------|------|
| Oracle | 9 | 1.000 | 1.00 | 1.00 | 1.00 | 1.00 |
| Greedy | 9 | 0.971 | 1.00 | 1.00 | 1.00 | 0.912 |
| Random | 9 | 0.000 | 0.00 | 0.00 | —    | —    |

Random never leaves Easy, so the curriculum never promotes it.

## LLM policy — pending credentials

Not run: needs `API_BASE_URL`, `MODEL_NAME`, and an API key (`GROQ_API_KEY`,
`HF_TOKEN` or `API_KEY`). Run `python inference.py`; results will be added here.
Greedy (0.941 overall) and Oracle (1.000) are the reference points to beat.
