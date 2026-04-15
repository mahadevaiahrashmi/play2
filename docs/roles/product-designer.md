<!-- agent-notes: { ctx: "product designer role guide for warehouse-routing-openenv", deps: [src/warehouse_routing/server/ui.py, warehouse-routing-blog/], state: active, last: "grace@2026-04-15" } -->
# Product Designer

## What you own
- The **end-to-end experience** for someone who lands on the HF Space cold — they should understand what this thing is and try it within 30 seconds.
- The **`/ui` viewer's information design** — what the operator needs to see (and what they don't) at each step.
- The **blog narrative** — `warehouse-routing-blog/index.html`. Cold-open, gap, mechanism, baselines, failure modes, next steps.
- The **README's first 5 lines** — title, motivation, "what does this do for me?"
- **Color, typography, spacing** within the established dark palette.

## Where things live
| Artifact | Path |
|----------|------|
| Grid viewer (visual layer) | `src/warehouse_routing/server/ui.py` (the `<style>` block + SVG layout) |
| Blog | `warehouse-routing-blog/index.html` (separate HF Space, gitignored here) |
| README | `README.md` |
| Color tokens | Inline CSS `:root` vars in `ui.py` and `index.html` (`--bg`, `--accent`, `--good`, `--bad`, `--warn`) |
| Persona reference (AI side) | `docs/methodology/personas.md` (Dani persona = your AI counterpart) |

## How "good" looks here
- **A first-time visitor scores the experience in seconds, not minutes.** If they have to read the README to understand what's on screen, the UI failed.
- **Failure is legible.** Red robot bumping a wall should look bad. Green visited cells should feel earned. Don't hide failure modes.
- **One palette across surfaces.** Viewer, blog, README screenshots all share the GitHub-dark token set. Don't fork.
- **No fabrication in the blog.** Sprint 4 retro hard-coded this: only real Oracle / Llama / Random numbers, only real `[STEP]` log excerpts.
- **Accessibility floor.** Color is never the only signal — every state has a label or icon. The dpad is keyboard-equivalent (arrow keys, `R` for reset).

## Decisions you make
- Layout, type scale, spacing, interaction affordances within `/ui` and the blog.
- Which observation fields to surface in the panel (last action, cum reward, etc.).
- Tone of the blog and README.
- Screenshot composition for any future blog updates.

## Decisions you don't make
- Schema fields (Architect — you can request, not add).
- Dependencies — no design system imports, no icon libraries. Vanilla SVG + inline CSS only.
- Whether `/web` Gradio default stays (Architect).

## Routine cadence
- Every sprint: review the `/ui` against the live HF Space in a real browser, on a real network. Catch what tests can't.
- Every blog update: re-run the Oracle to confirm the headline numbers still hold. Don't ship stale baselines.
- Sprint boundary: contribute to Dani's visual smoke section in the retro.

## Project-specific gotchas
- **The visual smoke test exists because of the "Invisible UI" anti-pattern** (see `docs/process/gotchas.md`). 3 sprints once shipped Dash UI without anyone opening a browser. You are the human in the loop.
- **The blog repo is a separate HF Space.** It does not deploy from this repo. After editing, push the blog repo independently.
- **Iframe context confuses preview tools.** When testing the Space landing page, also open `/ui` directly to confirm console is clean.
- **Color tokens are duplicated** between `ui.py` and `index.html`. If you change `--accent`, change both.
