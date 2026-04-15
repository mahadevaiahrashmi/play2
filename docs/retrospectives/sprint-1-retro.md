<!-- agent-notes: { ctx: "sprint 1 retro: full hackathon build close", deps: [docs/baseline-scores.md, docs/tracking/], state: active, last: "grace@2026-04-15" } -->
# Sprint 1 Retrospective — warehouse-routing-openenv

**Date:** 2026-04-15
**Sprint scope:** Entire hackathon build — models, sim, solver, reward, grader, curriculum, OpenEnv server, Docker, inference entrypoint, validate-submission, /ui viewer, Oracle baseline, blog publish.
**Outcome:** 27/27 issues closed. 89/89 tests passing. HF Space live with grid viewer at `/ui`. Blog published. Llama 3.3 70B baseline established (0.000) with documented failure modes.

## What went well
- **TDD discipline held** through models → sim → solver → reward → grader → curriculum. Every module had failing tests before code.
- **Oracle harness** (ADR-0003) gave us a reusable, objective baseline before any LLM tuning.
- **Single-commit-per-issue** kept the audit trail clean. Every closed issue maps to a real commit.
- **Tier flicker bug** was diagnosed end-to-end (curl → schema → iframe → live HTML diff → root cause in `refresh()` clobber). The fix shipped with a regression-guarding test.
- **Inference baseline run produced actionable diagnostics** (wall-bumping, oscillation, no memory) instead of a single uninterpretable score.

## What hurt
- **Stateless prompt shipped first.** The original `OpenAIPolicy` sent only the current observation. Predictable result: 0.000. Should have been caught at design time, not after a paid API run. Fixed mid-sprint via #26.
- **`/ui` shipped without an automated test** (Done Gate violation). Regression bug only caught manually. Filed and fixed as #27.
- **Board / GitHub state drift.** All 25 sprint items were `Done` on the board but `open` on GitHub. 24 had to be batch-closed during this boundary audit. Process gap: closing the GH issue is not part of the per-item Done flow.
- **Working tree carried prior-session deletions** (samples/, README-template, research docs) for the entire sprint. Should have been resolved at scaffold time, not at sprint close.
- **Groq API key was pasted into the conversation transcript.** Needs rotation by user.

## Architecture Gate compliance
- **ADRs this sprint:** 3 (`0001-conventional-commits`, `0002-tdd-workflow`, `0003-reusable-eval-harness`).
- **Wei debate artifacts:** 0.
- **Compliance:** 0/3 ADRs had recorded Wei debates. ADR-0001 and ADR-0002 are process ADRs (low-risk, debate not strictly required). ADR-0003 is architectural (introduced a new harness pattern) and should have had one.
- **Unrecorded architectural decisions:**
  - Choice of Groq over HF Router for inference endpoint (cost/latency tradeoff, no ADR).
  - Custom SVG grid viewer instead of extending Gradio default (`/ui` route, no ADR).
  - Pydantic v2 + FastAPI as the OpenEnv shim (locked in by openenv-base, but not documented).
- **Action:** Retroactive lightweight ADR for the eval harness debate is acceptable; the others are noted here and not worth separate ADRs.

## Board compliance
- **Status flow violations:** All 25 original items skipped the `In Review` status. They moved Backlog → In Progress → Done without an explicit review transition. The board reflects done state correctly, but the audit trail is missing.
- **Root cause:** Per-item review was bundled into the single commit-and-close flow rather than a separate board transition.
- **Action:** Filed as process improvement (see issues below).

## Process improvement issues filed
1. Add "close GH issue" to the per-item Done flow so board and GitHub state stay in sync.
2. Enforce `In Review` status transition before `Done` (board-side requirement).
3. Block scaffold-time deletions from carrying past sprint 1.
4. Make a stateless-prompt smell test part of the inference Done Gate (any `OpenAIPolicy`-style class must demonstrate either a documented zero-history reason OR a history-injection test).

## Operational Baseline Audit — Sprint 1

### Ines: Operational Concerns (project type: backend service + CLI inference)
| Concern | Status | Finding |
|---------|--------|---------|
| Logging | Foundation | `[START]/[STEP]/[END]` spec format used in `inference.py`; FastAPI default access logs. No structured logger. Adequate for hackathon scope. |
| Error UX | Foundation | `inference.py` exits with explicit messages on missing API_KEY / openai import. `OpenAIPolicy.choose()` falls back to `"N"` on exception with a `[DEBUG]` line. |
| Debug support | Foundation | `--dry-run` flag enables full offline reproduction. Logs are sufficient to diagnose failures without a debugger. |
| Config health | Foundation | API_BASE_URL / MODEL_NAME / API_KEY env vars are read at startup; missing key fails fast. No `.env.example` (low priority for a hackathon submission). |
| Graceful degradation | Foundation | LLM call wrapped in try/except, defaults to safe `"N"` move. Container has no external deps beyond the LLM endpoint. |

**Result:** 5/5 at Foundation. No blocking gate.

### Diego: README 5-Minute Test
- **Result:** Pass (read-verified for Docker steps; execution-verified for `pytest`, `python inference.py --dry-run`, `validate-submission.sh`).
- **Issues found:** None. README quick-start is accurate.

### Dani: Visual Smoke Test
- **Pages checked:** `/ui` (live on HF Space), `/docs` (FastAPI auto-docs).
- **Console errors:** None after the `latest = data` clobber fix.
- **Visual issues:** None. Grid renders correctly across Easy/Medium/Hard tiers.

## Tech debt logged this sprint
- **D1:** `OpenAIPolicy` history is local to a Python list; not persisted across `--max-variations` runs. Acceptable.
- **D2:** `validate-submission.sh` requires the venv's `openenv` CLI on PATH. Documented in commit message but not in README.
- **D3:** Working-tree carries unresolved scaffold-deletions from project init.

## Lessons for next sprint
- Any policy class that talks to an LLM must have a mocked-client test asserting **what's in the prompt**. This catches stateless-prompt anti-patterns at design time.
- Any new HTTP route requires a smoke test asserting status + key markers in the same commit. Manual-only validation is not acceptable.
- Sprint boundary must close GH issues, not just move the board.
