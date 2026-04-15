---
agent-notes: { ctx: "implementation tracking for Oracle + reusable eval harness feature", deps: [docs/adrs/0003-reusable-eval-harness.md, docs/baseline-scores.md, docs/code-map.md], state: complete, last: "sato@2026-04-14" }
---

# Implementation: Oracle Policy + Reusable Eval Harness

**Date:** 2026-04-14
**Lead:** Sato
**Status:** Complete
**Prior Phase:** [2026-04-14 Drone-TSP Discovery](./2026-04-14-drone-tsp-openenv-discovery.md)

## Context

Comparison against the SQLEnv reference blog (`/home/mahad/test1/blog/sqlenv-blog/index.html`) surfaced a
gap: they publish a baseline table (Oracle / Random / LLM) produced by a shared eval loop. We had
Random implicit in `inference.py`, no Oracle, no shared loop, and baseline numbers nowhere. User
reviewed three feature options, rejected a grader change, and said "you decide which features to
make." We picked Oracle + reusable harness + published baseline.

## Key Decisions

- **Chose Protocol-based `Policy` over an ABC** because any class with `choose(obs) -> Move` should
  work without inheritance; OpenAIPolicy stays inline in `inference.py` to keep openai import lazy.
- **Placed `evaluate()` as a free function in `warehouse_routing.eval`, not a method on `Curriculum`**,
  to keep the dependency direction `eval → curriculum`; the curriculum state machine should not
  know about Observation/Action/GridEnv.
- **Kept `[START]/[STEP]/[END]` logging out of `evaluate()`** — the format is hackathon-specific and
  belongs in `inference.py`. Accepted two similar loops as the cost of that separation.
- **OraclePolicy replays a Held-Karp tour via A* path reconstruction** (new `astar_path` in
  `pathing.py`, new `optimal_tour_order` in `solver.py`), chosen so it doubles as a regression
  check: if solver/pathing/sim/grader drift, the oracle stops scoring 1.0.
- **Published three-row baseline table** in `docs/baseline-scores.md` with an offline reproduction
  command that imports nothing from `inference.py`. LLM row left pending until credentials are
  available.
- **Skipped grader change** (user vetoed): grader formula stays `optimal_length / agent_length`
  clamped to [0,1].

## Artifacts Produced

- `src/warehouse_routing/policies.py` — `RandomPolicy`, `OraclePolicy`, `VALID_MOVES`, plan builder
- `src/warehouse_routing/eval.py` — `Policy`, `EpisodeResult`, `EvalReport`, `evaluate()`
- `src/warehouse_routing/pathing.py` — new `astar_path()` alongside existing `astar_distance()`
- `src/warehouse_routing/solver.py` — new `optimal_tour_order()` alongside `optimal_tour_length()`
- `tests/test_policies.py` — 3 tests (Oracle scores 1.0 on easy; Oracle clears curriculum across
  all tiers; Random bounded in [0,1])
- `tests/test_pathing.py` — 4 new tests for `astar_path` (same-point, straight line, obstacle
  detour, unreachable)
- `tests/test_solver.py` — 5 new tests for `optimal_tour_order` (no SKUs, single SKU, set
  equality, hop-sum equals `optimal_tour_length`, obstacle-aware path)
- `inference.py` — refactored to import `Policy` from `eval`, `RandomPolicy` + `VALID_MOVES` from
  `policies`; inline dataclasses removed
- `docs/baseline-scores.md` — three-row table, Oracle 1.000 vs Random 0.000
- `docs/adrs/0003-reusable-eval-harness.md` — ADR documenting the decision
- `docs/code-map.md` — populated from scaffold stub with full module inventory (85 tests)

## Baseline Numbers (offline, master_seed=0, max_variations=9)

| Policy | n | mean | success | easy | medium | hard |
|--------|---|------|---------|------|--------|------|
| Oracle | 9 | 1.000 | 1.00 | 1.00 | 1.00 | 1.00 |
| Random | 9 | 0.000 | 0.00 | 0.00 | — | — |

Random never promotes past easy; easy never closes in 64 steps under uniform N/S/E/W.

## Test Impact

- Before: 73 tests
- After: 85 tests (+3 policies, +4 astar_path, +5 optimal_tour_order)
- Full suite: 85 passed

## Commits

- `f07e97d` — feat(eval): Oracle policy + reusable evaluate harness
- `f58664e` — test: direct unit tests for astar_path and optimal_tour_order (closes #23)
- `468f72d` — docs(code-map): populate with full module inventory (closes #22)
- `3d165e9` — docs(adr): ADR-0003 reusable eval harness (closes #24)

## Open Questions

- None for this feature. Sprint 3's remaining credential-gated items (#18 HF deploy, #20 LLM
  baseline row) are unblocked by this work but waiting on `HF_TOKEN` / HF Space credentials.
