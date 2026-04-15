<!-- agent-notes: { ctx: "data engineer role guide for warehouse-routing-openenv", deps: [inference.py, src/warehouse_routing/eval.py, src/warehouse_routing/curriculum.py], state: active, last: "grace@2026-04-15" } -->
# Data Engineer

> Data Engineer here means: you make `[STEP]` traces, baseline runs, and curriculum metadata into structured, queryable, reproducible data. Not a strict requirement for the hackathon — becomes critical the moment ML Engineer wants offline learning.

## What you own
- **The trace pipeline.** Today, `inference.py` writes `[START]/[STEP]/[END]` lines to stdout. You own turning that into structured rows (parquet, JSONL, DuckDB) suitable for offline learning.
- **The dataset schema.** `(episode_id, tier, seed, attempt, step, observation_blob, action, reward, done, error, score)` — define it, version it, document it.
- **Baseline run reproducibility.** `docs/baseline-scores.md` should be the human face of a queryable artifact, not a hand-edited table.
- **Storage layout.** Where traces live, how they're partitioned, how big they're allowed to get, when they're rotated.
- **Data contracts.** If a model wants to consume `Observation` blobs, you guarantee schema stability across runs.

## Where things live
| Artifact | Path |
|----------|------|
| Trace producer (today) | `inference.py` (`log_start`, `log_step`, `log_end`) |
| Trace format spec | (none yet — your first deliverable) |
| Baseline scores | `docs/baseline-scores.md` |
| Eval harness (your upstream) | `src/warehouse_routing/eval.py` |
| Curriculum metadata | `src/warehouse_routing/curriculum.py` (`summary()`) |
| Storage | (none yet — pick local parquet for v1) |

## The current state — important
**No trace storage exists.** Sprint 1–4 produced traces only as stdout text. To enable ML Engineer's offline learning, you need to:

1. Define the row schema (Pydantic or a parquet schema).
2. Add a `TraceWriter` that the curriculum runner can hand rows to.
3. Decide local-only (parquet on disk) vs HF Datasets.
4. Make `--dry-run` write traces too — they're free signal.

This is a foundational sprint of work, not a one-issue task.

## How "good" looks here
- **Schemas are versioned.** `trace.schema.v1.json` (or equivalent). Bumps are explicit.
- **Every trace row is self-describing.** Replay a row → reconstruct the env state → re-step the policy → get the same outcome.
- **Storage is boring.** Local parquet for v1. Don't reach for Iceberg until there's a reason.
- **Determinism.** `(master_seed, tier, seed, attempt)` is the primary key. Same key → same trace, byte-for-byte.
- **Costs are visible.** Bytes per episode × episodes per sprint = your storage budget. Track it.

## Decisions you make
- Trace schema and version policy.
- Storage backend (parquet, JSONL, DuckDB, HF Datasets).
- Partitioning (by tier? by sprint? by master_seed?).
- Retention policy.
- Whether to capture full `Observation` blobs or a delta encoding.

## Decisions you don't make
- What gets logged in `[STEP]` lines — that's hackathon spec, frozen by Architect.
- The reward shape (Backend + PM).
- ML algorithm choice (ML Engineer).

## Routine cadence
- **Per experiment:** verify trace integrity (row count = step count; no missing keys).
- **Sprint:** report storage growth; rotate or compress as needed.
- **Sprint close:** flag schema drift to Architect — additive only.

## Project-specific gotchas
- **`Observation` is not flat.** It contains `list[Cell]` fields (`sku_locations`, `obstacles`, `visited`). Parquet handles nested lists, but check column types.
- **`steps_taken` resets to 0 between episodes.** Use `episode_id` (not `step`) as the row primary key prefix.
- **The hackathon stdout format is load-bearing.** Don't replace `print()` calls — *tee* them. Trace writing is additive.
- **`--dry-run` uses RandomPolicy.** Random traces are cheap, plentiful, and useful for schema validation. Use them first.
- **HF Spaces don't have persistent disk on the free tier.** Traces collected during a Space run vanish on container restart. Either pull traces locally during runs or upload to HF Datasets.
- **`TIME_PENALTY = -0.01`** per step plus **`step_budget = 500`** for Hard tier means a single failed Hard episode = 500 rows. Plan storage accordingly.
- **No data exists yet.** This role is greenfield. Negotiate scope with PM before starting — easy to over-engineer.
