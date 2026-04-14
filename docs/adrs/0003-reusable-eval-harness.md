---
agent-notes: { ctx: "ADR: shared Policy protocol + evaluate harness decouples policies from curriculum driver", deps: [src/warehouse_routing/eval.py, src/warehouse_routing/policies.py, inference.py, docs/baseline-scores.md], state: accepted, last: "archie@2026-04-14" }
---

# ADR-0003: Reusable Eval Harness

## Status

Accepted — 2026-04-14

## Context

Before this ADR, `inference.py` was the only place that drove a policy across
the curriculum. Every baseline we wanted to compare — Oracle, Random, LLM —
had to either live inside `inference.py` or duplicate its loop (curriculum
next/record, variation building, GridEnv stepping, grading). Three concrete
pressures pushed us to extract a harness:

1. **SQLEnv blog comparison.** Their "baseline table" pattern (oracle +
   random + LLM) only works if all three policies can be driven through an
   identical loop; otherwise the numbers aren't comparable.
2. **Regression safety net.** An OraclePolicy that replays the Held-Karp
   tour is only useful as a drift check if it can run outside the hackathon
   entrypoint — specifically from a pytest file, with no network, no
   `[START]/[STEP]/[END]` logging, and no env-var requirements.
3. **Baseline doc reproducibility.** `docs/baseline-scores.md` needs a
   single-command invocation that produces the published numbers without
   importing `inference.py` (which pulls in `openai` lazily and hard-fails
   without `HF_TOKEN`).

A thin `Policy` protocol + `evaluate()` function satisfies all three without
duplicating the curriculum state machine.

## Decision

Introduce `warehouse_routing.eval` with:

- `Policy` — a `typing.Protocol` with one method, `choose(obs) -> Move`.
- `EpisodeResult` — per-episode dataclass (tier, seed, attempt, steps, score, success).
- `EvalReport` — aggregate dataclass with `n`, `mean_score`, `success_rate`,
  `by_tier()` helpers.
- `evaluate(policy, *, master_seed, max_variations, time_limit_seconds)` —
  drives `Curriculum` + `make_variation` + `GridEnv` + `grade_variation`
  until the curriculum terminates or the cap is hit.

Move the baseline policies into `warehouse_routing.policies`:

- `RandomPolicy(rng)` — uniform over N/S/E/W.
- `OraclePolicy()` — computes the optimal tour on first obs of each episode
  via `optimal_tour_order` + `astar_path`, then replays the Move sequence.

`inference.py` imports `Policy` from `eval` and `RandomPolicy` from
`policies`, and keeps `OpenAIPolicy` inline (lazy `openai` import).

The harness deliberately **does not** emit `[START]/[STEP]/[END]` logs —
that format is hackathon-specific and stays in `inference.py`.

## Alternatives Considered

- **Leave the loop in `inference.py` and add Oracle there.** Rejected:
  `inference.py` hard-imports openai + requires `HF_TOKEN`, so pytest
  couldn't exercise Oracle as a regression check without monkey-patching.
- **Make `evaluate()` a method on `Curriculum`.** Rejected: the curriculum
  state machine shouldn't know about Observation/Action or GridEnv. Keeping
  it as a free function preserves the one-way dependency
  `eval → curriculum`, not the other way.
- **Inline Oracle inside tests.** Rejected: then `docs/baseline-scores.md`
  can't produce the number without a test runner, and the regression-check
  value (oracle stops scoring 1.0 if solver/pathing/sim/grader drift) is
  lost from the published numbers.

## Consequences

### Positive

- Oracle, Random, and LLM baselines run through identical code paths —
  scores are directly comparable.
- `test_policies.py` exercises Oracle end-to-end without network, providing
  an integration check for solver + pathing + sim + grader drift.
- `docs/baseline-scores.md` has a copy-pasteable offline reproduction
  command that imports nothing from `inference.py`.
- Future policies (RL, heuristic, another LLM) plug in by satisfying the
  one-method `Policy` protocol.

### Negative

- Two loops now exist that look similar: `eval.evaluate()` and the
  `[START]/[STEP]/[END]`-emitting loop in `inference.py`. They share the
  curriculum state machine but duplicate the episode loop. Acceptable
  because the log-format constraint is fundamentally imperative and hard
  to parameterize without making `evaluate` ugly.
- Slight indirection cost: `inference.py` now imports from two new
  modules instead of being self-contained.

### Neutral

- `Policy` is a Protocol, not an ABC — no inheritance required. Any class
  with a `choose(obs) -> Move` method works.
- The harness caps runs via `max_variations` (episode count) or
  `time_limit_seconds` (wall-clock), matching the curriculum's own
  termination conditions.
