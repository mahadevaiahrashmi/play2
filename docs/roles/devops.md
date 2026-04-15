<!-- agent-notes: { ctx: "DevOps/SRE role guide for warehouse-routing-openenv", deps: [Dockerfile, validate-submission.sh, openenv.yaml], state: active, last: "grace@2026-04-15" } -->
# DevOps / SRE

## What you own
- **The container.** `Dockerfile` — multi-stage build on `openenv-base`.
- **The submission gate.** `validate-submission.sh` — 3 checks (HF ping, docker build, openenv validate).
- **HF Space deployment** — `Rashmi-mahadevaiah/drone` (env) and `Rashmi-mahadevaiah/warehouse-routing-blog` (blog). Deploy = `git push` to the Space repo.
- **OpenEnv spec compliance** — `openenv.yaml` and the contract surface FastAPI exposes.
- **Secret hygiene** — `HF_TOKEN`, `GROQ_API_KEY`. Never in repo, never in logs, never in chat.
- **Local dev environment health** — `uv sync`, `.venv/bin/openenv` on PATH for the gate.

## Where things live
| Artifact | Path |
|----------|------|
| Dockerfile | `Dockerfile` |
| Submission gate | `validate-submission.sh` |
| OpenEnv spec | `openenv.yaml` |
| HF Space metadata | `README.md` (frontmatter — `sdk`, `app_port`, `base_path`) |
| Server entrypoint (re-export) | `server/app.py` |
| Real FastAPI app | `src/warehouse_routing/server/app.py` |
| CI config | (none yet — opportunity) |

## How "good" looks here
- **Submission gate is green before push.** `./validate-submission.sh https://<space>.hf.space` runs in under 30 seconds (with Docker layer cache) and exits 0.
- **No secrets in the image.** Build args, not `ENV`. Runtime injects via HF Space secrets UI.
- **Reproducible builds.** Pin base image by digest, not tag. Pin Python deps via `uv.lock`.
- **Boring deploys.** Push to HF Space main → Space rebuilds → `/reset` returns 200. No manual steps.
- **The container starts in under 10 seconds.** OpenEnv health checks have a budget — don't blow it with cold imports.

## Decisions you make
- Base image, image layering, build cache strategy.
- Health check shape and timeout.
- Resource limits on the Space (within HF tier).
- When to bump base image versions.
- Secret rotation cadence.

## Decisions you don't make
- Application code (Backend).
- API contract (Architect).
- What gets logged (Backend, but you can require structured logs).

## Routine cadence
- **Per push:** local `validate-submission.sh` → push → poll HF Space `/reset` until 200.
- **Sprint:** dependency drift check, base image age check.
- **Quarterly:** rotate `HF_TOKEN` and `GROQ_API_KEY`. Document in a runbook.
- **Sprint close:** contribute to Ines's operational baseline section in the retro.

## Project-specific gotchas
- **`validate-submission.sh` requires the venv's `openenv` CLI on PATH.** First run failed because system PATH didn't include `.venv/bin`. Fix: `PATH="/path/to/.venv/bin:$PATH" ./validate-submission.sh ...`. Documented in sprint 3 retro as D2 / D4.
- **`base_path: /ui` in HF Space `README.md`** controls the landing page. If you change route names, sync this.
- **Two server entrypoints exist:** `server/app.py` at repo root (re-export, openenv-base discovers this) and `src/warehouse_routing/server/app.py` (the real one). Don't merge them — openenv-base needs the root path.
- **Groq API key was leaked in chat once** (sprint 1 retro). Add a pre-commit hook for `gsk_` / `hf_` / `sk-` prefixes. Currently missing.
- **HF Space free tier sleeps after inactivity.** First request after sleep takes ~30s. Submission gate must allow for that.
- **No CI yet.** Pushes to GitHub `main` do not run the test suite. Manual `pytest` is the only gate. Filing a CI workflow is in the unowned bucket — pick this up.
- **Docker layer cache is the difference between 8s and 8 minutes.** Don't reorder Dockerfile lines without thinking about cache invalidation.
