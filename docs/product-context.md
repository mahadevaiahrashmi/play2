<!-- agent-notes: { ctx: "human product philosophy, used by Pat for proxy decisions", deps: [docs/tracking/2026-04-14-drone-tsp-openenv-discovery.md], state: active, last: "pat@2026-04-14" } -->

# Product Context

**Captured:** 2026-04-14 by Pat (Phase 1b elicitation)
**Project:** drone-tsp-openenv — learning build against Meta PyTorch OpenEnv
Hackathon Round 1 spec.

This document is Pat's model of the human's product philosophy. It is consulted
whenever the human is unavailable and the team needs to proxy a decision.

## Decision Style

**"Just make the call and tell me after."** The human does not want options
laid out or recommendations for approval on routine decisions. Pick a direction,
move, report the outcome. Escalate only for decisions that are hard to reverse
or that would meaningfully change the project's shape.

**How to apply:**
- Naming, file layout, minor dependency choices → pick and move.
- Architecture decisions that lock in a schema, API, or data model → still
  make a call, but write an ADR so the decision is reviewable after the fact.
- Decisions that cost more than a few hours to undo → flag before committing.

## Quality vs. Speed

**Speed wins.** Working-but-ugly beats polished-but-late. MVP first, iterate.

**How to apply:**
- Prefer a running end-to-end slice (even if half the tiers are stubs) over
  a polished Easy tier alone.
- Refactoring passes are allowed but not required; don't block on them.
- Test coverage targets flex downward if they're slowing shipping; Tara's
  red-green-refactor still applies but "minimum viable tests" is acceptable.

## Scope Appetite

**Trim ruthlessly.** Cut scope to the bone, add later if actually needed.

**How to apply:**
- Every feature beyond the OpenEnv hard constraints is a candidate for
  deferral.
- The adaptive curriculum IS in scope — the human explicitly designed it —
  but any elaboration of it (per-tier hyperparameter tuning, telemetry
  dashboards, leaderboards) is not.
- When in doubt: cut it, flag in `docs/tech-debt.md` as a follow-up.

## Risk Tolerance

**New / unproven tools are fine, even preferred** when they fit the job
better than mature alternatives. The OpenEnv constraint itself is an example —
unproven framework, accepted willingly.

**How to apply:**
- Don't reach for "boring technology" as a default. If `python-tsp` is newer
  but cleaner than hand-rolling Held-Karp, use it.
- Corollary: when a new tool bites back, don't agonize — swap it out and move
  on. No emotional investment.
- This tolerance does NOT extend to abandoning the OpenEnv spec; that's the
  whole point of the project.

## Quality Bar (Done Definition)

**"Done = tests pass and it runs."** Not "reviewed by all three lenses."
Not "documented to a T." Minimum viable done.

**How to apply:**
- A work item can close when: tests pass, `openenv validate` passes, the
  component runs end-to-end, and the commit is pushed.
- Full Done Gate checklist (`docs/process/done-gate.md`) is aspirational, not
  mandatory. Skip items that don't add signal for this project.
- Exception: anything that would be surfaced by the hackathon's LLM-scoring
  rubric (README clarity, task descriptions, baseline scores) should meet a
  higher bar because the spec explicitly grades on it.

## Interruption Style

**Pick and move on small calls.** Do not interrupt the human to ask about
naming, file layout, minor dependencies, or reversible decisions.

**How to apply:**
- Default to making the call.
- Only interrupt for: scope changes, architectural forks, anything that
  costs > ~2 hours to undo, anything that affects the grading rubric.

## Non-Negotiables

- **OpenEnv spec compliance is non-negotiable.** Every hard constraint from
  the discovery artifact must be met.
- No other non-negotiables declared by the human. Pat treats the rest of the
  project as flexible.

## Implicit Quality Bar (inferred — the human skipped this question)

Signals: speed-wins, trim-ruthlessly, done=runs, pick-and-move. Inference:
this is a **"prove it works end-to-end"** build, not a "polish for months"
build. Pat proxies accordingly — depth of any individual component stops at
"works and won't obviously embarrass the judging rubric."

Correct this if the human says otherwise.

## Review & Update Policy

- Pat re-reads this file at the start of every Pat invocation.
- Updates happen on explicit feedback from the human, or at sprint boundaries
  when patterns drift from what's captured here.
- Stale entries get removed, not left around as historical noise.
