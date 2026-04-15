<!-- agent-notes: { ctx: "Phase 1 discovery artifact for drone-tsp-openenv", deps: [CLAUDE.md, docs/process/tracking-protocol.md], state: active, last: "cam@2026-04-14" } -->

# Discovery — warehouse-robot-routing-openenv

**Domain reframe (2026-04-14):** The mechanics remain a grid-world TSP with
step-by-step N/S/E/W movement, adaptive curriculum, and distance-based grading.
The *skin* is reframed from "drone delivering packages to houses" to
**"last-mile warehouse pick-and-pack routing for an autonomous mobile robot
(AMR) on a warehouse floor."** Warehouse = packing station, houses = SKU pick
locations, drone = AMR, obstacles = shelving / pillars / one-way aisles.

**Known risk (accepted by user):** The hackathon rubric requires "real-world
tasks, not games or toys." A gridworld shortest-path simulation sits in the
grey zone even after reframing. User acknowledged and chose to proceed.
Mitigation: lean hard on warehouse-operations framing in task descriptions,
README, and prompt templates. Use industry terms (SKU, AMR, pick list,
dwell-time). Judge-LLMs scan for textual signals of real-world applicability.

**Date:** 2026-04-14
**Phase:** Discovery (Phase 1)
**Prior Phase:** None
**Lead:** Cam
**Status:** Confirmed by human

## Vision

An OpenEnv-compliant grid-world environment where an LLM agent plans and executes
multi-stop drone delivery routes, graded against optimal TSP solutions. The
environment exists to **produce high-quality (prompt, action, reward) trajectories
for downstream LLM fine-tuning** on spatial and combinatorial reasoning.

The fine-tuning loop itself is out of scope. This project is the *environment*,
not the trainer.

## User & Context

Solo experimenter (project owner). HF Space publication is for OpenEnv
compliance, not for external distribution. Docs optimize for future-self, not
strangers.

**Context:** The OpenEnv hard constraints (Pydantic schemas, `openenv validate`,
HF Space, Dockerfile, `inference.py`, `validate-submission.sh`, < 20 min on
2 vCPU / 8 GB) originate from the Meta PyTorch OpenEnv Hackathon x SST Round 1
spec (Mar 25 – Apr 12, 2026). Round 1 submission window has closed as of
project kickoff (2026-04-14); this project is a **learning / portfolio build**,
not a live submission. No deadline pressure. The hackathon spec is retained
as the quality bar because it is well-defined and matches the user's goal of
practicing the full OpenEnv stack.

Note: the hackathon grading rubric combines **programmatic checks** (graders
return valid scores) with **LLM scoring** (a judge model reads the env +
README). README quality and code readability therefore have some signal
value beyond "tests pass."

## Core Loop

- `reset()` starts the agent at tier Easy with a random variation.
- Observation: typed Pydantic model containing grid dimensions, warehouse
  coordinate, list of house coordinates, obstacle cells, drone position,
  visited-set, remaining step budget, current tier, attempt counter.
- Action: `Action(move: Literal["N","S","E","W","PICKUP","DROP"])` — one move per
  step.
- `step()` returns shaped reward based on progress toward remaining optimal
  tour length, with penalties for invalid moves, revisits, loops.
- Episode terminates when the full curriculum (Easy → Medium → Hard) is
  completed OR the outer step budget is exhausted.

## Curriculum (Adaptive)

The environment walks the agent through an adaptive curriculum:

1. **Easy** — 8×8 grid, 3 houses, no obstacles.
2. **Medium** — 16×16 grid, 6 houses, sparse obstacles.
3. **Hard** — 24×24 grid, 10 houses, dense obstacles.

Progression rules:

- **Mastery criterion:** 3 consecutive variations at current tier with task
  score ≥ 0.9.
- **Failure:** any score below 0.9 on a variation resets the consecutive counter
  and draws a new variation at the same tier.
- **Attempt budget:** max 20 variations per tier. If not mastered in 20,
  force-promote to the next tier and record `mastered=False` for that tier.
- **Variation:** new RNG seed at the same tier parameters — new house positions,
  new obstacle layout, same grid size and house count.
- **End of curriculum:** after Hard is mastered (or force-promoted), `done=True`.
  Outer runner calls `reset()` for a fresh curriculum run.

## Grading

- **Per-task score:** `optimal_tour_length / agent_tour_length`, clamped to
  [0, 1]. Agent paths longer than optimal score < 1.0. Optimal = TSP ground
  truth over Manhattan distances, with per-leg shortest-path where obstacles
  exist.
- **Shaped reward (per step):** decrease in remaining-optimal-distance-to-
  completion, plus small penalties for: invalid move, out-of-bounds attempt,
  revisit of a house, detected tight loop.
- **Determinism:** every grader is deterministic given the RNG seed. Scores
  reproducible.

## Hard Constraints (Non-Negotiable)

- Full OpenEnv interface: typed Pydantic `Observation`, `Action`, `Reward`
  models; `step()`, `reset()`, `state()`; `openenv.yaml` with metadata; passes
  `openenv validate`.
- Containerized as an HF Space tagged `openenv`, clean start via
  `docker build` + `docker run`.
- Runs on **2 vCPU / 8 GB RAM**.
- `inference.py` full run completes in **< 20 minutes** on target hardware.
- `validate-submission.sh` enumerates every task, invokes every grader, asserts
  every reward ∈ [0.0, 1.0].
- README includes: description & motivation, action/observation space
  definitions, task descriptions per tier, setup & usage, baseline scores.
- Reward is **dense** (every step), not just terminal.
- Three difficulty tiers with deterministic graders.
- Penalizes clearly undesirable behavior (infinite loops, destructive actions).
- **LLM client is OpenAI-compatible** (not Anthropic). `inference.py` reads
  `API_BASE_URL`, `MODEL_NAME`, `HF_TOKEN` from environment.
- **`inference.py` lives in repo root** (not `src/`).
- **Structured stdout logs** — `[START]`, `[STEP]`, `[END]` lines with exact
  field names and ordering per the hackathon sample. Deviation = zero score.
- **HF Space must serve HTTP** — a pinger hits the Space URL, expects 200, and
  must be able to call `reset()` remotely. Implies a FastAPI (or similar)
  shim around `step()`/`reset()`/`state()` inside the container.
- **Pre-submission validation script** (`validate-submission.sh`) must be
  runnable locally before any submission-like action.

## Out of Scope (MVP)

- Multi-drone fleets, capacity limits, battery, wind, time windows.
- Dynamic obstacles.
- The fine-tuning / RL loop itself (this env is consumed by it, not running it).
- Polished onboarding for external contributors.

## Key Risks (flagged for Phase 3)

1. **20-minute wall-clock on Hard.** A 24×24 grid with 10 houses under
   step-by-step LLM control can easily blow the budget. Mitigation candidates:
   hard step cap per variation, batched/async inference, aggressive early-exit
   on loop detection. Wei to stress-test.
2. **Optimal TSP ground truth.** 10 houses = 10! ≈ 3.6M permutations. Brute
   force still works but is wasteful. Candidates: Held-Karp (2^n · n²),
   `python-tsp` library. Archie decides in Phase 3 ADR.
3. **Prompt/observation format drift.** Small JSON schema changes swing LLM
   performance by tens of points. The `Observation` schema must be nailed down
   early and version-pinned. Treated as an ADR in Phase 3.
4. **OpenEnv maturity.** OpenEnv is relatively new; the LLM-agent ergonomics
   story is thinner than its classical-RL story. User flagged it as a hard
   constraint — Wei to adversarially challenge in Phase 3.
5. **Curriculum attempt budget vs. wall-clock.** Worst case: 20 failed Easy
   attempts + 20 Medium + 20 Hard = 60 variations. Must fit in 20 min. Needs
   per-variation step budget tuning.

## Success Signal

- `openenv validate` passes.
- `validate-submission.sh` green — every task score in [0, 1].
- HF Space builds and runs.
- Baseline LLM (e.g., Haiku) scores recorded for all three tiers.
- End-to-end `inference.py` run completes in < 20 min on 2 vCPU / 8 GB.

## Open Questions (deferred to later phases)

- **Archie (Phase 3):** TSP ground-truth algorithm choice; Observation schema
  versioning.
- **Pierrot (Phase 3):** threat surface of a containerized env that calls out
  to an LLM API — key handling, prompt-injection in task text.
- **Tara (Phase 5):** test strategy for curriculum logic, grader determinism,
  reward-shape unit tests.
- **Pat (Phase 1b, next):** product philosophy elicitation.

## Confirmation

Human confirmed vision on 2026-04-14. Proceeding to Phase 1b (Pat — human
model elicitation).
