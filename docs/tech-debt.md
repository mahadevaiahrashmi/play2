<!-- agent-notes: { ctx: "technical debt register, persists across sprints", deps: [docs/retrospectives/], state: active, last: "grace@2026-04-15" } -->
# Technical Debt Register

> Grace maintains this register. Pat prioritizes debt against feature work.
> Debt persists across sprints — board items get closed, but debt lives here until resolved.
> **Escalation rule:** any item open for **3+ sprints** is automatically P0 in the next sprint. Pat cannot deprioritize escalated items below P0. Only override is an explicit user decision to defer.

**Project:** warehouse-routing-openenv
**Last reviewed:** 2026-04-15 (sprint 4 close, retroactive register creation)

## Active Debt

| ID | Description | Incurred | Why (business reason) | Est. cost to fix | Risk if left | Sprint to fix | Status |
|----|-------------|----------|----------------------|-----------------|-------------|--------------|--------|
| D1 | `OpenAIPolicy` history is in-memory; not persisted across `--max-variations` runs | Sprint 4 | History only needed within an episode for the hackathon scope | S (half day) | Low — episode-scoped use case is the only one | TBD | Open |
| D2 | `validate-submission.sh` requires the venv's `openenv` CLI on `PATH`; not documented in README | Sprint 3 | First-run failure was confusing; documented in commit message but not surfaced to users | XS (15 min — README note) | Medium — every fresh contributor will trip on this | sprint:2 | Open |
| D3 | Working tree carried scaffold-deletion residue across all 4 sprints; resolved by moving to `archive/` at sprint 1 close | Sprint 1 (init) | Template scaffolds were never resolved at project init | — | — | — | **Resolved (sprint-1 boundary, commit 6fecc5b)** |
| D4 | Same as D2 (duplicate logged in sprint 3 retro) | Sprint 3 | Logged twice; consolidated under D2 | — | — | — | Closed as duplicate of D2 |
| D5 | `HISTORY_WINDOW = 8` is a magic constant in `inference.py`; defended only by the mocked test, not tunable per tier | Sprint 4 | Hackathon scope; one global value sufficed | S (half day, if it needs per-tier tuning) | Low — only matters if Hard tier needs more context | TBD | Open |
| D6 | Blog source has no off-disk backup beyond the HF Space repo; previous parent path `/home/mahad/test1/blog/warehouse-routing-blog` no longer exists; only the nested copy in `play2/` survives | Sprint 4 | Accidental during file moves; nested copy was gitignored at the time | XS (15 min — already resolved in commit 56d4c84 by tracking `warehouse-routing-blog/` in this repo) | — | — | **Resolved (commit 56d4c84)** |
| D7 | No CI on the GitHub repo; `pytest` is a manual gate; pushes to `main` run nothing | Sprint 1 (init) | Hackathon focus on shipping; CI was deferred | M (1 day — one workflow file, secrets, status checks) | High — every regression must be caught by hand; the only thing standing between green main and red main is human discipline | sprint:2 | Open |
| D8 | No `docs/sbom.md`; `docs/dependency-decisions.md` is still a scaffold; no automated dep scan | Sprint 1 (init) | Security role guide was added in sprint 4 but the artifacts it owns don't exist yet | M (1 day — initial SBOM, then maintenance) | Medium — license / single-maintainer / CVE risks are tracked nowhere; `python-tsp` is single-maintainer | TBD | Open |
| D9 | No pre-commit secret scanner; the Groq API key was pasted into chat in sprint 1 (not committed, but the structural gap remains) | Sprint 1 | Project did not have a secret-handling policy until sprint 4 retro flagged it | S (half day — `gitleaks` or `trufflehog` in pre-commit + CI) | High — recurrence is a one-keystroke incident | TBD | Open |
| D10 | `docs/code-map.md` is the source of architectural truth but was populated late (sprint 4, commit 468f72d); drift risk is high without an explicit refresh trigger | Sprint 4 | No update trigger defined; relies on the Tech Writer noticing | S (half day — add a CI check or doc-ownership trigger) | Medium — onboarding friction grows quietly | TBD | Open |
| D11 | All sprint 1–4 items skipped the `In Review` board status; status flow audit trail is missing for the entire project history | Sprint 1–4 (systemic) | Per-item review was bundled into the commit-and-close flow rather than a separate board transition | — (process fix, not a code fix) | Medium — future audits cannot distinguish "reviewed and shipped" from "shipped without review" | sprint:2 (#29) | Open |

## Resolved Debt

| ID | Description | Incurred | Resolved | How it was fixed |
|----|-------------|----------|----------|-----------------|
| D3 | Scaffold-deletion residue carried across sprints | Sprint 1 init | Sprint 1 close (2026-04-15) | Moved template/sample scaffolds to `archive/` instead of deleting; commit `6fecc5b` |
| D6 | Blog source had no off-disk backup beyond HF Space | Sprint 4 | 2026-04-15 | Un-gitignored `warehouse-routing-blog/` and committed it into this repo; commit `56d4c84` |

## Debt Categories
- **Process / hygiene:** D2, D7, D9, D11
- **Documentation drift:** D8, D10
- **Code shortcuts:** D1, D5
- **Resolved:** D3, D6

## Escalation watch list
None of the active items are 3+ sprints old yet. Re-evaluate at sprint 5 close — at that point, **D2, D7, D8, D9, D10, D11 will all be 3 sprints old** and auto-escalate to P0 if still open. PM should plan paydown into sprint 5 to avoid mass escalation.
