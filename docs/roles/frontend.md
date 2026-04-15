<!-- agent-notes: { ctx: "frontend role guide for warehouse-routing-openenv", deps: [src/warehouse_routing/server/ui.py], state: active, last: "grace@2026-04-15" } -->
# Frontend Engineer

## What you own
- The **`/ui` SVG grid viewer** — `src/warehouse_routing/server/ui.py`. One Python file, one HTML string, vanilla JS, no build step.
- The **HF Space landing page experience** — `base_path: /ui` in the Space `README.md` frontmatter.
- **The blog site** at `Rashmi-mahadevaiah/warehouse-routing-blog` (separate HF Space, static SDK).

## Where things live
| Artifact | Path |
|----------|------|
| Grid viewer (HTML + JS embedded in Python) | `src/warehouse_routing/server/ui.py` |
| Mount point | `src/warehouse_routing/server/app.py` (`mount_ui(app)`) |
| Smoke test | `tests/test_smoke.py::test_ui_route_serves_grid_viewer` |
| HF Space metadata | `README.md` (Space repo, not this repo) |
| Blog | `warehouse-routing-blog/` (gitignored here; lives in its own HF Space repo) |

## How "good" looks here
- **No new dependencies.** Vanilla JS + SVG. No React, no Vue, no Tailwind, no bundler. The HTML is `r"""..."""` in Python.
- **Every new HTTP route ships with a smoke test in the same commit.** Sprint 4 retro made this explicit (#27). The test must assert status code, content-type, and key markers in the body.
- **Regression guards.** Sprint 3 had a `latest = data` clobber bug; the smoke test now greps for that pattern. Add similar guards for any new bug you fix.
- **Keyboard works.** Arrow keys = N/S/E/W; `R` = reset. Don't break this.
- **Theme matches the blog.** Dark, GitHub-ish palette (`#0d1117` bg, `#58a6ff` accent). Don't introduce a new color system.

## Decisions you make
- Visual layout, color choices within the established palette.
- Which fields to surface in the right-side panel.
- Polling cadence for `/state` (currently 1s).

## Decisions you don't make
- New routes (Architect + Backend).
- Schema fields on `Observation` (Architect).
- Whether `/web` Gradio default stays mounted (Architect — it currently does).

## Project-specific gotchas
- **`/state` returns only `{episode_id, step_count}`.** It does NOT return an observation. Sprint 3's tier-flicker bug came from `refresh()` reassigning `latest = data`, blanking the panel one second after reset. Don't reintroduce.
- **The HTML lives inside a Python raw string (`r"""..."""`).** Triple-quote-aware editing only.
- **`base_path` in HF Space metadata controls the landing page.** If you ship a new top-level route, update that too.
- **Iframe context confuses DevTools.** When debugging on the deployed Space, the parent `console` won't see iframe variables. Open the iframe directly: `https://rashmi-mahadevaiah-drone.hf.space/ui`.
- **No build step means no minification.** Keep the inline JS readable — future you will be debugging it from view-source.
