<!-- agent-notes: { ctx: "sprint 4 retro: oracle harness, blog, prompt-history fix", deps: [docs/baseline-scores.md, inference.py, tests/test_inference_policy.py], state: active, last: "grace@2026-04-15" }-->
# Sprint 4 Retrospective — warehouse-routing-openenv

**Date:** 2026-04-15
**Sprint scope:** Reusable eval harness, Oracle baseline, code-map docs, blog publish, fix the two regressions caught at sprint 3 close (`/ui` smoke test, `OpenAIPolicy` history).
**Outcome:** 6/6 issues closed. Oracle 1.000 / Llama 0.000 / Random 0.000 baselines published. Blog live on HF Space. 89/89 tests passing (+4 this sprint).

## Sprint 4 issues (all closed)
- #22 docs: update code-map.md with policies.py + eval.py
- #23 test: direct unit tests for astar_path and optimal_tour_order
- #24 docs(adr): reusable eval harness abstraction (ADR-0003)
- #25 docs(tracking): Oracle + eval harness feature artifact
- #26 Llama baseline scores 0.000 — add prompt history to OpenAIPolicy
- #27 `/ui` route has no automated test (Done Gate violation)

## What went well
- **Oracle harness is reusable.** ADR-0003 paid off immediately — Random and Llama runs use the same `evaluate()` entry point. Future policies plug in for free.
- **Failure mode → fix → test loop closed.** Stateless prompt anti-pattern was caught in sprint 3 retro, filed as #26, fixed with a mocked-client test that asserts what's in the user message. Same loop for `/ui` (#27).
- **Blog publish was clean.** Shipped to a separate HF Space (`Rashmi-mahadevaiah/warehouse-routing-blog`) with no fabricated training results — only the real Oracle/Llama/Random numbers and actual `[STEP]` log excerpts.

## What hurt
- **Board / GH state drift discovered late.** All 25 sprint 1–3 items were Done on the board but `open` on GitHub. Required a 24-issue batch close during sprint 1's boundary. Already filed as #28 (process improvement).
- **Working tree carried scaffold residue across all 4 sprints.** Cleaned up at sprint 1 boundary by moving to `archive/`.
- **Groq API key landed in the conversation transcript.** Needs user rotation. Process gap: no in-flight check for secrets in chat.

## Architecture Gate compliance
- **ADRs this sprint:** 1 (`0003-reusable-eval-harness`).
- **Wei debate artifacts:** 0.
- **Compliance:** 0/1. The eval harness was a real architectural decision (introduced a new abstraction that all future policies depend on). Should have had a Wei debate. **Action:** Note the gap; don't retroactively fabricate a debate.
- **Unrecorded decisions:**
  - Groq endpoint over HF Router (cost/latency, no ADR — acceptable, swap-only).
  - `HISTORY_WINDOW = 8` constant in `OpenAIPolicy` (magic number; defended by the mocked test).

## Board compliance
- All 6 items skipped `In Review`. Already filed in sprint 2 backlog as #29.

## Operational Baseline Audit — Sprint 4
| Concern | Status | Finding |
|---------|--------|---------|
| Logging | Foundation | Unchanged from sprint 3. |
| Error UX | Foundation | `OpenAIPolicy.choose()` falls back to `"N"` on exception with `[DEBUG]` line. |
| Debug support | Foundation | History injection is observable in the prompt; mocked test proves it. |
| Config health | Foundation | `HISTORY_WINDOW` is a module constant, not an env var. Acceptable. |
| Graceful degradation | Foundation | Episode-reset on `steps_taken` regression handles curriculum boundaries. |

5/5 Foundation. No gate trip.

### Diego: README 5-Minute Test
- **Result:** Pass (read-verified for Docker, execution-verified for `pytest` and `validate-submission.sh`).

### Dani: Visual Smoke Test
- **Pages checked:** `/ui` on HF Space.
- **Console errors:** None (post-clobber-fix).
- **Visual issues:** None. Last action / cum reward fields render correctly.

## Tech debt logged
- **D5:** `HISTORY_WINDOW = 8` is a magic constant. Acceptable for hackathon scope; revisit if it tunes per-tier.
- **D6:** Prior-session blog repo at `/home/mahad/test1/blog/warehouse-routing-blog` no longer exists; only nested copy in play2 (gitignored). Single point of failure for the blog source.

## Lessons
- The post-sprint regression-find loop (sprint 3 retro → sprint 4 fix) worked. Keep doing this even after the hackathon closes.
- Always tag issues with `sprint:N` at creation. The 4 unlabeled docs issues this sprint were only categorized at sprint close.
