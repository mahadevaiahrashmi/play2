<!-- agent-notes: { ctx: "security/compliance role guide for warehouse-routing-openenv", deps: [Dockerfile, pyproject.toml, docs/methodology/personas.md], state: active, last: "grace@2026-04-15" } -->
# Security / Compliance

> Human counterpart to the **Pierrot** persona in `docs/methodology/personas.md`. Pierrot has veto power on security and compliance grounds — this role exercises that veto on the human side.

## What you own
- **The SBOM.** Every dependency, every license, every transitive risk. Currently does not exist — that is your first deliverable.
- **Secret hygiene.** `HF_TOKEN`, `GROQ_API_KEY`, any future credentials. The chat-leak incident in sprint 1 proves this is real.
- **License audit.** `python-tsp`, `openai`, `fastapi`, `pydantic`, `openenv-base` — all permissive today, but you must verify and re-verify on dep bumps.
- **Container security.** Base image CVEs, root user check, image scan results.
- **Threat model** for any external-facing surface (`/reset`, `/step`, `/state`, `/ui`).
- **Veto power** on dependencies, auth changes, and pre-release gates.

## Where things live
| Artifact | Path |
|----------|------|
| Dependency manifest | `pyproject.toml` |
| Lock file | `uv.lock` |
| SBOM | `docs/sbom.md` (does not exist yet — create it) |
| Threat model | `docs/threat-model.md` (scaffolded under `docs/scaffolds/`, not yet activated) |
| Dependency decisions log | `docs/dependency-decisions.md` (scaffolded) |
| Container | `Dockerfile` |
| Pierrot persona spec | `docs/methodology/personas.md` |

## How "good" looks here
- **Every dep has a reason and a license, recorded.** "We added it because we needed X" is the minimum entry. No silent additions.
- **No secrets in repo, image, logs, or chat.** Period. Use HF Space secrets UI for runtime.
- **Container runs non-root.** Verify with `docker inspect`. (Currently inherits from `openenv-base` — verify what that defaults to.)
- **Dependency bumps go through a license re-check.** Same name, new version, new license is a real failure mode.
- **CVE scans on every base image bump.** `trivy image warehouse-routing:dev` or equivalent.
- **Veto used surgically.** Don't block work for theoretical risk. Block for documented exposure.

## Decisions you make
- Whether a new dependency is acceptable (veto power).
- License compatibility (veto power).
- Whether a release can ship (veto power, used as last resort).
- Secret rotation cadence and method.
- Threat severity classification.

## Decisions you don't make
- Application architecture (Architect).
- Test sufficiency (Tester).
- Feature priorities (PM) — but you can mark items as security-blocking.

## Routine cadence
- **Per dep change:** license check + SBOM update.
- **Sprint:** CVE scan against base image; secret-leak scan against the diff (`gitleaks` or `trufflehog`).
- **Sprint close:** contribute to the operational baseline audit; flag any below-Foundation security concerns as P0 for next sprint.
- **Pre-submission:** verify `validate-submission.sh` is the only network-touching gate.

## Project-specific gotchas
- **The Groq API key was pasted into chat in sprint 1.** Treat it as compromised — needs rotation. Add a pre-commit hook scanning for `gsk_`, `hf_`, `sk-` prefixes (devops owns the hook; you own the policy).
- **HF Spaces are public by default.** Anyone can hit `/reset` and `/step`. There's no rate limiting today — fine for a hackathon, would be a CVE in prod.
- **`/ui` is unauthenticated and shares process state with `/step`.** A user on the viewer can reset the env underneath an inference run. Document or fix.
- **`openai` package is permissive (Apache-2.0)** but its transitive `httpx` chain occasionally bumps versions you didn't ask for. Check `uv.lock` after every `uv sync`.
- **`python-tsp` is MIT** but maintained by a single contributor — **single-maintainer risk**. Pin it strictly.
- **No CI means no automated security gate.** Until devops adds CI, you are the human gate. Document this dependency.
