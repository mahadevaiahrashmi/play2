<!-- agent-notes: { ctx: "session handoff — no-op refresh, ~17 days idle since b739370", deps: [docs/retrospectives/, docs/roles/, docs/tech-debt.md], state: active, last: "grace@2026-05-02" } -->
# Session Handoff

**Created:** 2026-05-02 (refresh of 2026-04-15 handoff — no project work this session)
**Sprint:** Sprint 1, 3, 4 closed. Sprint 2 open (process-improvement bucket).
**Wave:** N/A — this project does not use wave-based planning.
**Session summary:** No-op session. User asked for `gitpush and handoff`; nothing to push (branch already at `origin/main`), only local `.claude/` statusline customizations uncommitted. Refreshing the handoff date and forward plan; substantive content unchanged from 2026-04-15.

## What Was Done (this session)
- Verified branch is up to date with `origin/main` — no commits since `b739370` (2026-04-15).
- Verified board state matches prior handoff (#28/#29/#30 Ready; #26/#27 still labeled Backlog despite being implemented in `b750bde` — see Key Context).
- Refreshed this handoff file.

> Prior session (2026-04-15) summary preserved in git: see `b739370`, `af7dc23`, `280cb7e`. Highlights: closed sprints 1/3/4, implemented #26/#27, shipped 13 role guides, activated tech-debt register, code review of `b750bde` (3 Important / 6 Suggestion / 0 Critical, all deferred to next `inference.py` touch).

## Current State
- **Branch:** `main` — up to date with `origin/main`.
- **Last commit:** `b739370 chore(handoff): refresh after code review of b750bde`
- **Uncommitted changes:** local-only `.claude/settings.json` (statusLine block) and untracked `.claude/statusline.sh` — personal terminal customization, NOT project work. Do not commit unless the user explicitly asks.
- **Tests:** 89 passing across 14 test files (per prior session — not re-run today).
- **Board status:** Sprint 2 has 3 items in **Ready** (#28, #29, #30). Sprints 1/3/4 are closed. No items In Progress.

## Sprint Progress
- **No `docs/sprints/sprint-N-plan.md` exists** — this project did not use wave-based planning.
- **Sprint 2 (open) — 3 items in Ready:**
  - #28 — Per-item Done flow must close GH issue, not just move board
  - #29 — Enforce In Review status transition before Done
  - #30 — LLM policy classes need mocked-client prompt assertion test

## What To Do Next (in order)

> **First, the user must rotate the Groq API key** that was pasted into chat in a prior session. It's not in git, but the chat log persists. (Carried forward from 2026-04-15 handoff — confirm whether this has been done before assuming it's still pending.)

1. **Read `docs/code-map.md`** to orient.
2. **Read `docs/product-context.md`** for product philosophy.
3. **Read `docs/retrospectives/sprint-4-retro.md`** for the latest sprint context.
4. **Read `docs/tech-debt.md`** — note the escalation watch: D2, D7, D8, D9, D10, D11 turn 3 sprints old at sprint 5 close and auto-escalate to P0.
5. **Run sprint 2** — implement the 3 process-improvement items in Ready:
   - **#28** (`Per-item Done flow must close GH issue`): Update CLAUDE.md § Development Workflow to require `gh issue close` as part of step 6. Doc change.
   - **#29** (`Enforce In Review status transition`): Update CLAUDE.md to require explicit `In Review` board transition before Done. Doc change + optional pre-commit/CI check.
   - **#30** (`LLM policy classes need mocked-client prompt assertion test`): Add a Done Gate item requiring any LLM-wrapping policy class to ship with a mocked-client test asserting message contents. Update `docs/process/done-gate.md` and the AI Engineer role guide.
   - All three are doc/process work, not code. Should fit one short session. Close each via `gh issue close`.
   - **While you're at it, fix the #26/#27 board status** — they were implemented in `b750bde` but their board status is still Backlog (and they carry both `sprint:1` and `sprint:4` labels). Move to Done and close the GH issues. This is itself an instance of #28's symptom.
6. **Then add CI** (`.github/workflows/test.yml`) — addresses D7. One workflow: install uv, `uv sync`, `pytest`. Trigger on push + PR. Block merges on red. ~30 min.
7. **Then a real engineering sprint** — likely **beating the Llama 0.000 baseline**: re-run inference now that #26 added prompt history, see if it moves, write up findings. Use `--max-variations 5` to limit cost. **When you touch `inference.py`, fold in the deferred review findings** from `docs/code-reviews/2026-04-15-prompt-history-and-ui-smoke.md` (V1: typed history rows; V2: `Policy` protocol with optional `record()`; T1: assert SYSTEM_PROMPT in test).

## Tracking Artifacts
- `docs/tracking/2026-04-15-prompt-history-ui-smoke-review.md` — code review tracking for `b750bde`. Status: Complete. All findings deferred to next `inference.py` touch.
- Sprint 1 and 3 implementation artifacts archived under `docs/tracking/archive/sprint-1/`.
- `docs/product-context.md` exists (last updated `pat@2026-04-14`).

## Proxy Decisions (Review Required)
None this session — user was present, and no decisions were made beyond "skip committing local statusline files."

## Key Context
- **#26 and #27 board-status mismatch.** Both were implemented in `b750bde` and are functionally Done (89 tests passing, code reviewed), but the project board still lists them as **Backlog** with mixed `sprint:1`/`sprint:4` labels. Resolve as part of sprint 2 (it's a live demonstration of the gap #28 closes).
- **The blog is now in two places**: GitHub (`warehouse-routing-blog/` in this repo) and the HF Space (`Rashmi-mahadevaiah/warehouse-routing-blog`). They will drift if you edit one. Pick a canonical source before next blog edit.
- **The test suite must be run with no `HF_TOKEN` / `GROQ_API_KEY` in the shell** — otherwise the inference path tries real network calls. Use a clean shell or `env -i`.
- **`Observation.attempt` must be `>= 1`** — Pydantic rejects 0. Bit me when writing the policy history tests.
- **`compute_reward()` returns a `Reward` dataclass**, not a float. Use `.value`.
- **Sprint 4's failure-mode loop** (sprint 3 retro → file as #26/#27 → fix in sprint 4 → close) worked. Keep this pattern.
- **D2 (`openenv` PATH issue) is an XS doc fix** deferred 3 sprints. Knock it out as a freebie during sprint 2.
- **There is no CI.** Manual `pytest` is the only gate. Run tests locally before pushing.
- **Sprint 2's items are all doc/process work.** Tech Writer + PM lens is enough — no Architect or Backend needed.
- **Local `.claude/statusline.sh` + settings.json statusLine block** are personal customizations on this machine. They are not in git and should not be — leave them alone.
