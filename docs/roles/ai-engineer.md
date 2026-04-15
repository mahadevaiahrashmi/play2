<!-- agent-notes: { ctx: "AI engineer role guide for warehouse-routing-openenv", deps: [inference.py, src/warehouse_routing/policies.py, src/warehouse_routing/eval.py], state: active, last: "grace@2026-04-15" } -->
# AI Engineer

> "AI engineer" here means: you build the LLM-facing layer — prompts, policy classes, tool schemas, eval harnesses. You consume models; you do not train them. ML Engineer (`ml.md`) is the role that trains.

## What you own
- **Policy classes** in `inference.py` and `src/warehouse_routing/policies.py`. Today: `RandomPolicy`, `OraclePolicy`, `OpenAIPolicy`. New ones plug into the same `evaluate()` harness.
- **Prompt design** — system prompt, observation serialization, history injection.
- **Failure-mode diagnosis.** When a policy scores 0.000, it's your job to read the `[STEP]` logs and explain *why* (wall-bumping, oscillation, hallucinated move letters, etc.).
- **The mocked-prompt assertion suite** — `tests/test_inference_policy.py`. Any new policy gets one of these.
- **Cost discipline.** Paid API runs are gated; you propose budgets per experiment.

## Where things live
| Artifact | Path |
|----------|------|
| Inference entrypoint + policy classes | `inference.py` |
| Reference policies | `src/warehouse_routing/policies.py` |
| Reusable harness (your contract surface) | `src/warehouse_routing/eval.py` |
| Mocked prompt tests | `tests/test_inference_policy.py` |
| Baseline scores | `docs/baseline-scores.md` |
| Reward shape (what the model is being graded on) | `src/warehouse_routing/reward.py` |
| ADR for harness | `docs/adrs/0003-reusable-eval-harness.md` |

## How "good" looks here
- **Stateless prompts are an anti-pattern.** Sprint 3 baseline shipped one and scored 0.000. Every new policy needs an opinion on memory: history window, tool calls, scratchpad, or an explicit defended reason for stateless.
- **Mocked test before paid run.** Assert what's in the user message with a `FakeClient` *before* spending a dollar on Groq.
- **`[STEP]` logs are the diagnostic surface.** When a policy fails, you must point to the exact step where it went wrong. "It just doesn't work" is not a finding.
- **Determinism where possible.** `temperature=0.0` for reproducibility. If you raise it, document why and re-run with multiple seeds.
- **Fall back safely.** On any LLM exception, return a legal move (`"N"` is the current default). Never crash the curriculum runner.

## Decisions you make
- Prompt structure, system prompt content, observation serialization format.
- History window size, what goes into history (action only? action + reward? + error?).
- Token budget per call (currently `max_tokens=4` — single letter).
- Tool-use vs. text-only.
- Which model to bench against.

## Decisions you don't make
- The harness contract (Architect — ADR-0003).
- Reward shape (Backend + PM).
- Whether to spend money on a full curriculum run (PM approves cost).
- Adding new policy *types* to the public API (Architect).

## Routine cadence
- **Per experiment:** dry-run with mocked client → smoke run on `easy` tier (≤3 variations) → full run only after smoke is green.
- **Sprint:** publish a delta against the prior baseline in `docs/baseline-scores.md`. No deltas = no progress.
- **Sprint close:** read the failure modes back into the next sprint's prompt iteration.

## Project-specific gotchas
- **`HISTORY_WINDOW = 8`** is a magic constant in `inference.py`. The mocked test pins it. If you change it, update both.
- **`OpenAIPolicy.choose()` detects new episodes by `obs.steps_taken` going backward.** Don't break this — `evaluate()` doesn't call a `reset()` hook.
- **The Groq endpoint is OpenAI-compatible** but rate-limits aggressively on free tier. Burstiness across the curriculum will throttle you.
- **`max_tokens=4`** is intentional — the model only needs one letter. Raising it invites verbose explanations that break the `re.search(r"[NSEW]", text)` parser.
- **Past Groq API key was leaked into the conversation transcript** (sprint 1 retro). Always pass keys via env, never paste.
- **Random baseline = 0.000, not "just noise."** A random walker rarely returns to the warehouse within budget — `score = 0` is the floor, not a soft signal.
