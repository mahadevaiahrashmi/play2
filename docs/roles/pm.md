<!-- agent-notes: { ctx: "PM role guide for warehouse-routing-openenv", deps: [docs/product-context.md, docs/baseline-scores.md], state: active, last: "grace@2026-04-15" } -->
# Product Manager

## What you own
- The **hackathon submission spec compliance** — every requirement in the OpenEnv Hackathon Round 1 spec maps to a closed issue.
- The **backlog** — what gets built, in what order, against what success criteria.
- **Baseline targets** — current Llama 3.3 70B baseline is 0.000 on `easy`. Defines what "good" looks like for next iteration.
- **Stakeholder communication** — blog, README, `docs/product-context.md`.

## Where things live
| Artifact | Path |
|----------|------|
| Product context (philosophy, target user) | `docs/product-context.md` |
| Sprint retros | `docs/retrospectives/sprint-N-retro.md` |
| Baseline scores (the ground truth on agent quality) | `docs/baseline-scores.md` |
| Project board | https://github.com/users/mahadevaiahrashmi/projects/4 |
| Issue templates | `.github/ISSUE_TEMPLATE/` (none yet — opportunity) |

## How "good" looks here
- **Every issue has acceptance criteria** that map to a test or a measurable score, not "looks right."
- **No issue ships without a `sprint:N` label.** Sprint 4 retro caught 4 unlabeled docs issues — don't repeat.
- **Baseline regressions are P0.** If `Oracle` drops below 1.000 or any policy class regresses on its mocked-prompt test, that's a release blocker.
- **The README quick-start passes the 5-Minute Test** every sprint (Diego audit). If a new contributor can't `pytest` clean in 5 minutes, that's a P1.

## Decisions you make
- What goes into the next sprint vs. tech debt vs. drop.
- When to escalate `tech-debt` items above 3 sprints to P0 (this is enforced by Grace, not optional).
- When `proxy mode` activates for absent stakeholders — and which decisions to log in the Correction Log.

## Decisions you don't make
- Architectural ones (Architect + Wei).
- Test coverage gates (Tester has veto).
- Security/license veto (Pierrot).

## Routine cadence
| When | What |
|------|------|
| Sprint start | Prioritize backlog, label `sprint:N`, identify Architecture Gate items |
| Mid-sprint | Triage incoming issues, refresh `product-context.md` if priorities shift |
| Sprint close | Read the retro, update product context, decide tech debt paydown for next sprint |

## Project-specific gotchas
- The Groq baseline run **costs real money** per variation. Don't approve full curriculum runs as part of routine validation — gate on `--dry-run` and the Oracle harness for free signal.
- The blog (`Rashmi-mahadevaiah/warehouse-routing-blog`) lives in a separate HF Space repo. Keep it factual — no fabricated training results.
- `validate-submission.sh` requires the venv's `openenv` CLI on PATH. If submission gates start failing, check that first.
