<!-- agent-notes: { ctx: "role guide index for warehouse-routing-openenv", deps: [docs/code-map.md, docs/methodology/personas.md], state: active, last: "grace@2026-04-15" } -->
# Role Guides

Project-specific onboarding for human contributors. Each role guide answers:
**what is mine to own, where does it live in this codebase, and what does "good" look like here?**

These are companions to the methodology agent personas in `docs/methodology/personas.md` — that file describes the AI agents; this directory describes the human role surface.

| Role | Guide | Owns |
|------|-------|------|
| Product Manager | [pm.md](pm.md) | Backlog, priorities, hackathon scope, baseline targets |
| Software Architect | [architect.md](architect.md) | ADRs, OpenEnv contract, module boundaries, eval harness |
| Backend Engineer | [backend.md](backend.md) | `src/warehouse_routing/` core (sim, solver, reward, server) |
| Frontend Engineer | [frontend.md](frontend.md) | `/ui` SVG grid viewer, HF Space landing page |
| Software Tester | [tester.md](tester.md) | `tests/`, oracle harness, baseline reproducibility |
| Product Designer | [product-designer.md](product-designer.md) | `/ui` viewer, blog narrative, README first impression |
| AI Engineer | [ai-engineer.md](ai-engineer.md) | Policy classes, prompt design, mocked-prompt tests |
| ML Engineer | [ml-engineer.md](ml-engineer.md) | Training pipelines, experiment design, statistical eval |
| DevOps / SRE | [devops.md](devops.md) | Container, submission gate, HF Space deploy, secret hygiene |
| Security / Compliance | [security.md](security.md) | SBOM, license audit, secret leaks, threat model, veto power |
| Tech Writer / DevRel | [tech-writer.md](tech-writer.md) | README, code map, blog, baselines doc, changelog |
| Data Engineer | [data-engineer.md](data-engineer.md) | Trace pipeline, dataset schema, baseline reproducibility (greenfield) |
| Research Scientist | [research-scientist.md](research-scientist.md) | Hypotheses, experiment design, lit review, claim framing (optional) |

Read [`docs/code-map.md`](../code-map.md) first for the package structure, then pick your role guide.
