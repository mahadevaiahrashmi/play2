<!-- agent-notes: { ctx: "sprint 3 retro: OpenEnv shim + Docker + submission gate", deps: [docs/baseline-scores.md, validate-submission.sh, Dockerfile], state: active, last: "grace@2026-04-15" } -->
# Sprint 3 Retrospective — warehouse-routing-openenv

**Date:** 2026-04-15 (retroactive close)
**Sprint scope:** Wrap the env in OpenEnv contract, ship to HF Space, gate submissions, run the LLM baseline, finalize README.
**Outcome:** 7/7 issues closed. HF Space live, `validate-submission.sh` 3/3 green, baseline inference run completed.

## Sprint 3 issues (all closed)
- #15 `openenv.yaml` + `openenv validate` green
- #16 FastAPI HTTP shim for `/step` / `/reset` / `/state`
- #17 Dockerfile + clean `docker build` / `docker run`
- #18 HF Space deploy + ping returns 200
- #19 `validate-submission.sh` pre-submission script
- #20 Baseline inference run + scores recorded
- #21 README: full spec per hackathon requirements

## What went well
- **Submission gate held.** `validate-submission.sh` caught the missing PATH-to-`openenv` issue on first run, fixed on retry. 3/3 passed in ~8s on the second attempt thanks to Docker layer cache.
- **HF Space deploy was a one-shot** once the OpenEnv shim was correct. No retries needed for the container.
- **Baseline run produced diagnostic gold.** Llama 3.3 70B failure modes (wall-bumping, oscillation, no memory) were directly visible in the `[STEP]` log lines. This drove the sprint 4 prompt-history fix.

## What hurt
- **Baseline scored 0.000.** The stateless prompt was identified only after the paid run. Caught by sprint 4 (#26).
- **`/ui` shipped with no automated test.** Caught by sprint 4 (#27).
- **`base_path` in HF Space metadata initially pointed to `/web` (Gradio default)** instead of `/ui`. The grid viewer was invisible from the Space landing page until that was changed.
- **Tier flicker bug** ate significant diagnosis time — root cause was `refresh()` reassigning `latest = data` from `/state` (which has no observation). Now regression-guarded by the smoke test.
- **Sprint was never formally closed.** Issues moved to Done on the board but `/sprint-boundary` was not run — no retro, no tracking archive, no process-improvement gate. This retro is being written retroactively as part of sprint 1's boundary cleanup.

## Architecture Gate compliance
- **ADRs this sprint:** 0.
- **Wei debate artifacts:** 0.
- **Unrecorded architectural decisions:**
  - FastAPI shim mounted alongside the openenv-base Gradio default rather than replacing it.
  - Custom `/ui` SVG viewer (decision flowed into sprint 4).
  - `base_path` swap from `/web` to `/ui`.
- **Action:** Acceptable for a hackathon close-out sprint; no retroactive ADRs warranted.

## Board compliance
- All 7 items skipped `In Review` (same systemic issue as sprint 1). Already filed as #29 in sprint 2.

## Operational Baseline Audit — Sprint 3
| Concern | Status | Finding |
|---------|--------|---------|
| Logging | Foundation | `[START]/[STEP]/[END]` spec lines + FastAPI access logs. |
| Error UX | Foundation | Submission gate fails fast with explicit messages. |
| Debug support | Foundation | `--dry-run` reproduces offline; logs sufficient for postmortem. |
| Config health | Foundation | API_BASE_URL / MODEL_NAME / API_KEY validated at startup. |
| Graceful degradation | Foundation | LLM exception path falls back to safe `"N"`. |

5/5 Foundation. No gate trip.

## Tech debt logged
- **D4:** `validate-submission.sh` requires `openenv` on PATH; not documented in README. Already noted in sprint 1 retro as D2.

## Lessons (already absorbed into sprint 4)
- Always smoke-test new HTTP routes in the same commit (→ #27).
- Any LLM client wrapper needs a "what's in the prompt" test (→ #26, #30).
- Verify HF Space `base_path` matches the route you actually want users to land on.
