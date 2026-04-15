<!-- agent-notes: { ctx: "session handoff after sprint 1/3/4 close + role guides + tech debt activation", deps: [docs/retrospectives/, docs/roles/, docs/tech-debt.md], state: active, last: "grace@2026-04-15" } -->
# Session Handoff

**Created:** 2026-04-15
**Sprint:** Sprint 1, 3, 4 closed. Sprint 2 open (process-improvement bucket).
**Wave:** N/A — this session was sprint boundary + documentation, not feature work.
**Session summary:** Closed sprints 1/3/4 with retros, implemented #26 (prompt history) and #27 (/ui smoke test), shipped 13 role guides, activated the tech debt register, and tracked the blog in this repo.

## What Was Done
- **Issue verification + close**: Verified all 25 sprint 1–3 issues were done-in-code, closed 24 stale `open`-state ones with commit references.
- **Implemented #27**: `/ui` smoke test in `tests/test_smoke.py` with regression guard against the `latest = data` clobber.
- **Implemented #26**: `OpenAIPolicy` rolling history (`HISTORY_WINDOW = 8`) with episode auto-reset on `steps_taken` regression. Mocked-client tests in `tests/test_inference_policy.py`.
- **Sprint 1 boundary**: retro at `docs/retrospectives/sprint-1-retro.md`, archived tracking artifacts to `docs/tracking/archive/sprint-1/`, moved scaffold residue to `archive/`. Filed #28/#29/#30 as process improvements.
- **Sprint 3 boundary** (retroactive): retro at `docs/retrospectives/sprint-3-retro.md`.
- **Sprint 4 boundary**: retro at `docs/retrospectives/sprint-4-retro.md`. Labeled previously-unlabeled #22–#25 with `sprint:4`.
- **Role guides**: 13 files under `docs/roles/` — PM, Architect, Backend, Frontend, Tester, Product Designer, AI Engineer, ML Engineer, DevOps, Security, Tech Writer, Data Engineer, Research Scientist.
- **Blog tracked in repo**: un-gitignored `warehouse-routing-blog/`, committed (`56d4c84`). Now lives in both GitHub and HF Space.
- **Tech debt register activated** at `docs/tech-debt.md` with 11 items (D1–D11), 2 already resolved.
- **Board ops**: Added #28/#29/#30 to project #4, moved them to **Ready**.
- **Tests**: 89 passing (was 85 — added 1 `/ui` smoke + 3 history tests).
- **Pushed**: all commits up to `ba02068` are on `origin/main`.

## Current State
- **Branch:** `main`
- **Last commit:** `ba02068 docs(tech-debt): activate register with D1-D11 from sprint 1-4 retros`
- **Uncommitted changes:** none — working tree clean
- **Tests:** 89 passing across 14 test files
- **Board status:** Sprint 2 has 3 items in **Ready** (#28, #29, #30). Sprints 1/3/4 are closed. No items In Progress.

## Sprint Progress
- **No `docs/sprints/sprint-N-plan.md` exists** — this project did not use wave-based planning.
- **Sprint 2 (open) — 3 items in Ready:**
  - #28 — Per-item Done flow must close GH issue, not just move board
  - #29 — Enforce In Review status transition before Done
  - #30 — LLM policy classes need mocked-client prompt assertion test

## What To Do Next (in order)

> **First, the user must rotate the Groq API key** that was pasted into chat in a prior session. It's not in git, but the chat log persists.

1. **Read `docs/code-map.md`** to orient.
2. **Read `docs/product-context.md`** for product philosophy.
3. **Read `docs/retrospectives/sprint-4-retro.md`** for the latest sprint context.
4. **Read `docs/tech-debt.md`** — note the escalation watch: D2, D7, D8, D9, D10, D11 turn 3 sprints old at sprint 5 close and auto-escalate to P0.
5. **Run sprint 2** — implement the 3 process-improvement items in Ready:
   - **#28** (`Per-item Done flow must close GH issue`): Update CLAUDE.md § Development Workflow to require `gh issue close` as part of step 6. Doc change.
   - **#29** (`Enforce In Review status transition`): Update CLAUDE.md to require explicit `In Review` board transition before Done. Doc change + optional pre-commit/CI check.
   - **#30** (`LLM policy classes need mocked-client prompt assertion test`): Add a Done Gate item requiring any LLM-wrapping policy class to ship with a mocked-client test asserting message contents. Update `docs/process/done-gate.md` and the AI Engineer role guide.
   - All three are doc/process work, not code. Should fit one short session. Close each via `gh issue close`.
6. **Then add CI** (`.github/workflows/test.yml`) — addresses D7. One workflow: install uv, `uv sync`, `pytest`. Trigger on push + PR. Block merges on red. ~30 min.
7. **Then a real engineering sprint** — likely **beating the Llama 0.000 baseline**: re-run inference now that #26 added prompt history, see if it moves, write up findings. Use `--max-variations 5` to limit cost.

## Tracking Artifacts
- `docs/tracking/` is empty (active artifacts). Sprint 1 and 3 artifacts archived under `docs/tracking/archive/sprint-1/`. No active phase context to carry forward.
- `docs/product-context.md` exists (created in a prior session).

## Proxy Decisions (Review Required)
None this session — the user was present throughout.

## Key Context
- **The blog is now in two places**: GitHub (`warehouse-routing-blog/` in this repo) and the HF Space (`Rashmi-mahadevaiah/warehouse-routing-blog`). They will drift if you edit one. Pick a canonical source before next blog edit.
- **The test suite must be run with no `HF_TOKEN` / `GROQ_API_KEY` in the shell** — otherwise the inference path tries real network calls. Use a clean shell or `env -i`.
- **`Observation.attempt` must be `>= 1`** — Pydantic rejects 0. Bit me when writing the policy history tests.
- **`compute_reward()` returns a `Reward` dataclass**, not a float. Use `.value`.
- **Sprint 4's failure-mode loop** (sprint 3 retro → file as #26/#27 → fix in sprint 4 → close) worked. Keep this pattern.
- **D2 (`openenv` PATH issue) is an XS doc fix** deferred 3 sprints. Knock it out as a freebie during sprint 2.
- **There is no CI.** Manual `pytest` is the only gate. Run tests locally before pushing.
- **Sprint 2's items are all doc/process work.** Tech Writer + PM lens is enough — no Architect or Backend needed.
