<!-- agent-notes: { ctx: "backend role guide for warehouse-routing-openenv", deps: [src/warehouse_routing/, docs/code-map.md], state: active, last: "grace@2026-04-15" } -->
# Backend Engineer

## What you own
- The **simulation engine** (`sim.py`) — deterministic grid state machine.
- **TSP solving** (`solver.py`) — Held-Karp via `python-tsp`, A* obstacle-aware (`pathing.py`).
- **Reward + grader** (`reward.py`, `grader.py`) — dense shaped + 0..1 score.
- **Curriculum runner** (`curriculum.py`) — adaptive Easy → Medium → Hard.
- **OpenEnv FastAPI shim** (`server/app.py`, `env.py`) — `/reset`, `/step`, `/state`.
- **Inference entrypoint** (`inference.py`) — episode loop, logging spec, policy plumbing.

## Where things live
| Module | Purpose |
|--------|---------|
| `models.py` | Pydantic Cell / Action / Observation / Reward |
| `sim.py` | `GridEnv` state machine |
| `solver.py` | Optimal closed-TSP tour length |
| `pathing.py` | A* shortest-path |
| `reward.py` | Per-step shaped reward + terminal score |
| `grader.py` | `grade_variation()` final score |
| `curriculum.py` | Tier sequencing + mastery streak |
| `tasks.py` | `TaskSpec` + variation generator |
| `eval.py` | Reusable `evaluate(policy, ...)` (ADR-0003) |
| `policies.py` | `RandomPolicy`, `OraclePolicy` |
| `server/app.py` | FastAPI `/reset` `/step` `/state` |
| `env.py` | OpenEnv `Environment` adapter |

## How "good" looks here
- **TDD red → green.** Tara writes the failing test, you make it pass. Sprint 1–4 averaged this — keep doing it.
- **No bare floats.** Reward constants live in `reward.py` as named module constants (`TIME_PENALTY`, etc.). Don't sprinkle.
- **Schemas at the edge.** Pydantic validates at `/reset` and `/step`. Internal code trusts its inputs.
- **Determinism.** Anything random is seeded from `(master_seed, tier_index, attempt)`. No `time.time()` for control flow.
- **One commit per issue.** Conventional commit format. `Closes #N` in the body.

## Decisions you make
- Implementation inside an established module.
- Helper extraction (when the same shape appears 3+ times — not earlier).
- Test fixture organization within `tests/`.

## Decisions you don't make
- New modules (Architect).
- API/schema additions (Architect).
- New dependencies (Architect + Pierrot).

## Project-specific gotchas
- **`compute_reward()` returns a `Reward` dataclass, not a float.** The `.value` attribute is the scalar.
- **`steps_taken` is monotonic within an episode.** `OpenAIPolicy` uses backwards motion as the episode-reset signal.
- **Don't mutate `Observation` in place.** It's a Pydantic model passed across HTTP boundaries.
- **The Held-Karp solver is O(n²·2^n).** Hard tier (10 SKUs) is fine; do not raise tier sizes without re-checking.
- **`make_variation()` retries until obstacles don't disconnect SKUs.** Don't lower the retry budget — Hard tier needs it.
