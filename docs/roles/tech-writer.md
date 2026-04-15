<!-- agent-notes: { ctx: "tech writer / DevRel role guide for warehouse-routing-openenv", deps: [README.md, docs/code-map.md, warehouse-routing-blog/], state: active, last: "grace@2026-04-15" } -->
# Technical Writer / DevRel

> Human counterpart to the **Diego** persona in `docs/methodology/personas.md`. Diego runs the README "5-Minute Test" every sprint — you own the words being tested.

## What you own
- **README.md** — the front door. Quick start, motivation, how to grade, how to submit.
- **`docs/code-map.md`** — the architectural source of truth for new contributors. Read first, write last.
- **`docs/baseline-scores.md`** — the scoreboard that the blog cites. Numbers must match reality.
- **The blog** — `warehouse-routing-blog/index.html` (in its own HF Space repo, gitignored here).
- **Changelog and migration notes** — currently nonexistent. Opportunity.
- **ADR readability** — Architect drafts ADRs; you make them legible to humans who didn't sit through the debate.

## Where things live
| Artifact | Path |
|----------|------|
| README | `README.md` |
| Code map | `docs/code-map.md` |
| Baselines | `docs/baseline-scores.md` |
| Product context | `docs/product-context.md` |
| Retros | `docs/retrospectives/sprint-N-retro.md` |
| ADRs (you edit for clarity, Architect owns content) | `docs/adrs/` |
| Role guides | `docs/roles/` |
| Blog | `warehouse-routing-blog/index.html` (separate HF Space) |
| Diego persona spec | `docs/methodology/personas.md` |

## How "good" looks here
- **The README quick-start passes Diego's 5-Minute Test every sprint.** A new contributor runs the commands as written and reaches a passing `pytest` in under 5 minutes. If they hit any undocumented step, that's a P1 defect.
- **No fabricated numbers.** Sprint 4 retro made this hard policy: blog and README cite only real `evaluate()` outputs from `docs/baseline-scores.md`. If you can't reproduce it, don't print it.
- **One canonical source per fact.** The reward constants live in `reward.py` — when you cite them in the blog, link, don't duplicate. When `reward.py` changes, citations break loudly.
- **Conventional commits + retros generate the changelog for free.** You're not writing it from scratch — you're curating it.
- **Voice is honest.** This project shipped a 0.000 baseline. The blog says so. Don't dress it up.
- **Every command is execution-tested.** Read-verified is acceptable only when execution requires real credentials; mark it as such.

## Decisions you make
- Tone, structure, headline framing.
- Which artifacts get a cross-link.
- When a doc is stale enough to delete vs. update.
- Diataxis split (tutorials / how-to / reference / explanation) when docs grow past one file.

## Decisions you don't make
- Technical accuracy on disputed claims (defer to Architect / Backend / ML).
- What to publicly disclose about security incidents (Security).
- Product positioning (PM).

## Routine cadence
- **Every commit that touches `inference.py`, `reward.py`, `eval.py`, or `models.py`:** check whether README or code-map needs a sync.
- **Per sprint:** run the 5-Minute Test against the README from a clean checkout.
- **Sprint close:** contribute to Diego's section in the retro. File any documentation gap as P1.
- **Per release:** publish a changelog entry. Reference closed issues, not commits.

## Project-specific gotchas
- **The blog repo lives at `warehouse-routing-blog/` (gitignored in this repo) and pushes to a separate HF Space.** Do not commit it here. Edits there require pushing the blog repo independently.
- **The blog's previous parent path (`/home/mahad/test1/blog/warehouse-routing-blog`) no longer exists** — only the nested copy in `play2/` survives. Single point of failure (logged as D6 in sprint 4 retro). Don't lose it.
- **`docs/code-map.md` was populated late** (sprint 4, commit `468f72d`). Keep it current — every sprint it drifts is technical debt.
- **Color tokens are duplicated** between the `/ui` viewer and the blog. If the designer changes `--accent`, you sync both files.
- **Three sprint retros now exist** (`sprint-1`, `sprint-3`, `sprint-4`). Sprint 2 has no retro because it has no closed sprint — it's the open process-improvement bucket. Don't mistake the absence for a gap.
- **Several scaffolds at `docs/scaffolds/`** (`config-manifest.md`, `runbook-template.md`, etc.) are unactivated stubs. They are not authoritative until moved out of `scaffolds/`. Don't link to them as if they are.
