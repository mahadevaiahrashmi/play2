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

## Evaluation runner leaderboards (`scripts/run_eval.py`)

Produced by:

```
uv run python scripts/run_eval.py --seeds 10 --workers 4 --out-dir runs/latest
```

10 seeded variations (seeds 0-9) per tier, 30 episodes per policy. Every logged
episode was replayed (`replay_episode`) and reproduced its logged score
(`replay_verified=90` and `210`). Running with `--workers 1` and `--workers 4`
gave byte-identical leaderboard files. Columns: Mean steps is over episodes that
produced steps; Opt. gap = mean(steps/optimal - 1) over successful episodes;
Failed = dead-lettered episodes (counted as score 0); Loop alerts = tracer
repeated-state/prompt alerts (threshold 5).

Note the greedy numbers differ slightly from the 20-seed table above (0.938 vs
0.941) because this run uses seeds 0-9 only.

### Offline policies

| Rank | Policy | Easy | Medium | Hard | Mean score | Success | Mean steps | Opt. gap | Cost (USD) | Fallbacks | Loop alerts | Failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | oracle | 1.000 | 1.000 | 1.000 | 1.000 | 1.00 | 63.3 | 0.000 | 0.0000 | 0 | 0 | 0 |
| 2 | greedy | 0.975 | 0.929 | 0.911 | 0.938 | 1.00 | 68.8 | 0.071 | 0.0000 | 0 | 0 | 0 |
| 3 | random | 0.000 | 0.000 | 0.000 | 0.000 | 0.00 | 254.7 | — | 0.0000 | 0 | 875 | 0 |

Per-tier detail:

| Policy | Tier | n | Mean score | Success | Mean steps | Opt. gap |
|---|---|---|---|---|---|---|
| oracle | easy | 10 | 1.000 | 1.00 | 21.0 | 0.000 |
| oracle | medium | 10 | 1.000 | 1.00 | 54.0 | 0.000 |
| oracle | hard | 10 | 1.000 | 1.00 | 114.8 | 0.000 |
| greedy | easy | 10 | 0.975 | 1.00 | 21.6 | 0.029 |
| greedy | medium | 10 | 0.929 | 1.00 | 58.2 | 0.079 |
| greedy | hard | 10 | 0.911 | 1.00 | 126.6 | 0.104 |
| random | easy | 10 | 0.000 | 0.00 | 64.0 | — |
| random | medium | 10 | 0.000 | 0.00 | 200.0 | — |
| random | hard | 10 | 0.000 | 0.00 | 500.0 | — |

### Simulated LLM scenarios -- scripted mock, NOT a real model

These runs drive `ScriptedLLM` (see `mock_llm.py`) through the real
structured-action / resilient / budget / tracing stack. They test how the
platform's guards behave under failure; they say **nothing about any real
model's ability**. Prices are illustrative ($0.0005 / $0.0015 per 1k
input/output tokens), so the cost column is simulated and only meaningful for
comparing scenarios with each other. Cost is charged conservatively, including
failed attempts at their full reservation.

Scenarios: `valid` replies with the greedy move; `malformed-then-valid` returns
prose on every 4th call (the retry prompt includes the parse error);
`flaky-timeouts` raises a timeout on every 3rd call (backoff retry);
`noisy-30pct` replies with a random move 30% of the time; `oscillating` answers
E, W, E, W...; `garbage` never produces a valid move (all steps fall back to a
wall bump); `outage-then-recovery` raises connection errors while
`10 <= steps_taken < 40`, opening the circuit breaker, then recovers.

| Rank | Policy | Easy | Medium | Hard | Mean score | Success | Mean steps | Opt. gap | Cost (USD) | Fallbacks | Loop alerts | Failed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | sim-llm/flaky-timeouts | 0.975 | 0.929 | 0.911 | 0.938 | 1.00 | 68.8 | 0.071 | 1.0041 | 0 | 0 | 0 |
| 2 | sim-llm/malformed-then-valid | 0.975 | 0.929 | 0.911 | 0.938 | 1.00 | 68.8 | 0.071 | 0.9037 | 0 | 0 | 0 |
| 3 | sim-llm/valid | 0.975 | 0.929 | 0.911 | 0.938 | 1.00 | 68.8 | 0.071 | 0.6589 | 0 | 0 | 0 |
| 4 | sim-llm/noisy-30pct | 0.588 | 0.631 | 0.604 | 0.608 | 1.00 | 105.5 | 0.676 | 1.0054 | 0 | 5 | 0 |
| 5 | sim-llm/outage-then-recovery | 0.025 | 0.491 | 0.645 | 0.387 | 0.70 | 117.2 | 0.901 | 0.6980 | 1530 | 529 | 0 |
| 6 | sim-llm/garbage | 0.000 | 0.000 | 0.000 | 0.000 | 0.00 | 254.7 | — | 8.5717 | 7640 | 2990 | 0 |
| 7 | sim-llm/oscillating | 0.000 | 0.000 | 0.000 | 0.000 | 0.00 | 254.7 | — | 2.5364 | 0 | 2980 | 0 |

Per-tier detail:

| Policy | Tier | n | Mean score | Success | Mean steps | Opt. gap |
|---|---|---|---|---|---|---|
| sim-llm/flaky-timeouts | easy | 10 | 0.975 | 1.00 | 21.6 | 0.029 |
| sim-llm/flaky-timeouts | medium | 10 | 0.929 | 1.00 | 58.2 | 0.079 |
| sim-llm/flaky-timeouts | hard | 10 | 0.911 | 1.00 | 126.6 | 0.104 |
| sim-llm/malformed-then-valid | easy | 10 | 0.975 | 1.00 | 21.6 | 0.029 |
| sim-llm/malformed-then-valid | medium | 10 | 0.929 | 1.00 | 58.2 | 0.079 |
| sim-llm/malformed-then-valid | hard | 10 | 0.911 | 1.00 | 126.6 | 0.104 |
| sim-llm/valid | easy | 10 | 0.975 | 1.00 | 21.6 | 0.029 |
| sim-llm/valid | medium | 10 | 0.929 | 1.00 | 58.2 | 0.079 |
| sim-llm/valid | hard | 10 | 0.911 | 1.00 | 126.6 | 0.104 |
| sim-llm/noisy-30pct | easy | 10 | 0.588 | 1.00 | 36.5 | 0.742 |
| sim-llm/noisy-30pct | medium | 10 | 0.631 | 1.00 | 86.1 | 0.599 |
| sim-llm/noisy-30pct | hard | 10 | 0.604 | 1.00 | 194.0 | 0.688 |
| sim-llm/outage-then-recovery | easy | 10 | 0.025 | 0.10 | 63.9 | 2.938 |
| sim-llm/outage-then-recovery | medium | 10 | 0.491 | 1.00 | 109.8 | 1.040 |
| sim-llm/outage-then-recovery | hard | 10 | 0.645 | 1.00 | 177.8 | 0.559 |
| sim-llm/garbage | easy | 10 | 0.000 | 0.00 | 64.0 | — |
| sim-llm/garbage | medium | 10 | 0.000 | 0.00 | 200.0 | — |
| sim-llm/garbage | hard | 10 | 0.000 | 0.00 | 500.0 | — |
| sim-llm/oscillating | easy | 10 | 0.000 | 0.00 | 64.0 | — |
| sim-llm/oscillating | medium | 10 | 0.000 | 0.00 | 200.0 | — |
| sim-llm/oscillating | hard | 10 | 0.000 | 0.00 | 500.0 | — |

What these show (observed, not predicted): retries and backoff fully mask
malformed/timeout replies (scores identical to `valid`) at higher simulated
cost; the loop detector fires on the oscillating and garbage scenarios; the
circuit breaker plus explicit fallback keeps the outage scenario running
(1,530 fallback steps) instead of crashing; no episode was dead-lettered. The tracer cap
(50,000 spans) was exceeded in the simulated run (6,516 spans dropped, see
`simulated-llm-trace.json`).

## LLM policy — pending credentials

Not run: needs `API_BASE_URL`, `MODEL_NAME`, and an API key (`GROQ_API_KEY`,
`HF_TOKEN` or `API_KEY`). Run `python inference.py`; results will be added here.
Greedy (0.941 overall) and Oracle (1.000) are the reference points to beat.
