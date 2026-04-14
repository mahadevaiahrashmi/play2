# agent-notes: { ctx: "baseline inference run record", deps: [inference.py], state: active, last: "sato@2026-04-14" }

# Baseline Scores

## Random policy (offline smoke, no LLM)

```
python inference.py --dry-run --max-variations 5
```

| Run | Policy        | n | mean_score | mastered |
|-----|---------------|---|------------|----------|
| 1   | random-dryrun | 5 | 0.000      | {}       |

Random is, as expected, incapable of solving an 8×8 Easy variation within a
64-step budget. The run verifies the full pipeline end-to-end: curriculum →
variation generation → GridEnv → Reward → grader → `[START]/[STEP]/[END]`
stdout formatting → `[SUMMARY]` mean aggregation.

## LLM policy (pending)

Requires `API_BASE_URL`, `MODEL_NAME`, `HF_TOKEN`. Run:

```
python inference.py
```

Logged here once credentials are available.
