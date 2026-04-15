<!-- agent-notes: { ctx: "ML engineer role guide for warehouse-routing-openenv", deps: [src/warehouse_routing/eval.py, src/warehouse_routing/curriculum.py, docs/baseline-scores.md], state: active, last: "grace@2026-04-15" } -->
# ML Engineer

> "ML engineer" here means: you train models, tune them, design experiments, run statistically meaningful evaluations. AI Engineer (`ai-engineer.md`) consumes models. You produce them.

## What you own
- **Training pipelines** for any model that learns from environment rollouts (RL, behavior cloning from Oracle, fine-tuning a small LM on `[STEP]` traces).
- **Experiment design** — variation budget, seed plan, statistical significance of "Policy A beats Policy B."
- **Evaluation rigor** — confidence intervals on baseline scores, not single numbers.
- **Curriculum tuning** — should the mastery threshold be 0.9 or 0.8? Should the streak length be 3 or 5? Empirical answer.
- **Data pipeline** — collecting `[STEP]` traces in a structured format suitable for offline learning.

## Where things live
| Artifact | Path |
|----------|------|
| Eval harness | `src/warehouse_routing/eval.py` |
| Curriculum | `src/warehouse_routing/curriculum.py` |
| Reference policies (Random / Oracle) | `src/warehouse_routing/policies.py` |
| Baseline scores | `docs/baseline-scores.md` |
| Sim contract (your training-time environment) | `src/warehouse_routing/sim.py` + `env.py` |
| Reward shape | `src/warehouse_routing/reward.py` |

## The current state — important
**No training code exists yet.** Sprint 1–4 built the *evaluation* substrate only. The scoreboard today is:

| Policy | mean_score | n |
|--------|-----------|---|
| OraclePolicy | 1.000 | 9 |
| RandomPolicy | 0.000 | 9 |
| Llama 3.3 70B (stateless) | 0.000 | small smoke |

Your first job is to introduce a learning policy that beats `Random` on `easy` and to do it with statistical evidence, not a single seed.

## How "good" looks here
- **Confidence intervals on every baseline.** Single-seed runs are anecdote, not result. Report `mean ± 95% CI` over ≥30 variations.
- **Reproducibility.** Every experiment specifies `master_seed`, model checkpoint hash (if applicable), code commit, and reward constants in effect. A future engineer should reproduce your numbers from this metadata alone.
- **Ablations matter.** Don't ship "we added X and score went up." Ship "we added X, ablated to X', X'', and X is the cause."
- **Train against `tasks.py`, evaluate against unseen seeds.** Don't grade yourself on the seeds you trained on.
- **The Oracle is your ceiling, not your baseline.** Anything ≥ 0.5 on Hard is impressive. Anything ≥ 0.9 on Hard is research-grade.

## Decisions you make
- Algorithm choice (PPO? Q-learning? BC from Oracle? offline RL on `[STEP]` traces?).
- Hyperparameters and schedules.
- When a result is statistically significant.
- Compute budget per experiment (with PM cost approval).
- Curriculum hyperparams (mastery threshold, streak length, force-promote attempts).

## Decisions you don't make
- Reward shape (Backend + PM — but you can propose changes via ADR).
- Schema fields on `Observation` (Architect).
- Adding a training framework dep (Architect + Pierrot — torch is heavy, justify it).

## Routine cadence
- **Per experiment:** baseline → train → eval on held-out seeds → confidence interval → write up in `docs/experiments/<date>-<name>.md` (this directory does not exist yet — create it).
- **Sprint:** publish at most one *headline* result. Don't burn paper credibility on noise.
- **Sprint close:** add to `docs/baseline-scores.md` only after CIs are computed.

## Project-specific gotchas
- **`reward.py` is dense AND terminal.** A trained policy can game the dense signal (visit SKUs in suboptimal order to bank `+0.10` bonuses) and still terminal-fail. Look at *both* `mean_reward` and `score`.
- **The variation generator is small.** Easy tier has limited diversity at low seeds. Train on a wide seed range or risk overfitting.
- **The Held-Karp solver makes Oracle exact.** You will never beat 1.000. Aim for *robustness* (variance across seeds), not headline mean.
- **`steps_taken` resets to 0 between episodes** — relevant for any sequence model that needs an episode boundary signal.
- **No GPU on HF Spaces docker tier.** Inference-time models that fit on the LLM endpoint are the only realistic deploy path. Heavy training happens off-Space.
- **`TIME_PENALTY = -0.01`** per step is small but non-zero. Long episodes accumulate negative reward fast — your value function needs to handle the sign.
