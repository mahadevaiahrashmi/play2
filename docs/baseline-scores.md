# agent-notes: { ctx: "baseline inference run record", deps: [inference.py, src/warehouse_routing/eval.py, src/warehouse_routing/policies.py], state: active, last: "sato@2026-04-14" }

# Baseline Scores

Produced with the shared harness in `warehouse_routing.eval.evaluate`.

## Offline (no LLM)

```
python -c "
import random
from warehouse_routing.eval import evaluate
from warehouse_routing.policies import OraclePolicy, RandomPolicy

for label, policy in [('Oracle', OraclePolicy()), ('Random', RandomPolicy(rng=random.Random(0)))]:
    r = evaluate(policy, master_seed=0, max_variations=9, time_limit_seconds=None)
    print(f'{label:7s} n={r.n} mean={r.mean_score:.3f} success={r.success_rate:.2f} tiers={r.by_tier()}')
"
```

| Policy | n | mean_score | success_rate | easy | medium | hard |
|--------|---|------------|--------------|------|--------|------|
| Oracle | 9 | **1.000**  | 1.00         | 1.00 | 1.00   | 1.00 |
| Random | 9 | 0.000      | 0.00         | 0.00 | —      | —    |

**Oracle** replays the exact Held-Karp tour (A*-routed around obstacles) and
mastered all three tiers in the minimum 9 episodes. This doubles as a
regression check: if `solver`, `pathing`, `sim`, or `grader` drift apart, the
oracle stops scoring 1.0.

**Random** scores 0 on every Easy variation (uniform N/S/E/W cannot close a
multi-stop tour in 64 steps) so the curriculum never promotes past Easy.
This is the lower bound the LLM baseline has to beat.

## LLM policy (pending)

Requires `API_BASE_URL`, `MODEL_NAME`, `HF_TOKEN`. Run:

```
python inference.py
```

Logged here once credentials are available.
