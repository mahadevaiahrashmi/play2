---
agent-notes:
  ctx: "codebase structural overview; read first before exploring"
  deps: [src/warehouse_routing/, tests/, inference.py, server/app.py]
  state: active
  last: "sato@2026-04-14"
  key: ["UPDATE when adding packages, modules, or changing public APIs"]
---
# Code Map

Read this before exploring the codebase. Keep it current whenever you add a module or change a public API.

## Architecture at a Glance

```
                ┌──────────────────────────┐
                │      inference.py        │  hackathon entrypoint
                │  OpenAIPolicy / dry-run  │  [START]/[STEP]/[END] logs
                └────────────┬─────────────┘
                             │ Policy.choose(obs) -> Move
                             ▼
                ┌──────────────────────────┐
                │  warehouse_routing.eval  │  reusable harness
                │    evaluate(policy)      │  EvalReport / EpisodeResult
                └────────────┬─────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
  curriculum.py          tasks.py              sim.py
  state machine      variation builder       GridEnv.step
  (3-tier promote)   (seeded layouts)        (Action → StepResult)
        │                    │                    │
        └───────┬────────────┴────────┬───────────┘
                ▼                     ▼
           solver.py              reward.py / grader.py
           Held-Karp TSP          dense shaped reward
           + A* distance          final score = opt/agent
                │
                ▼
           pathing.py
           astar_distance / astar_path

       ┌──────────────────────┐
       │  server/app.py       │  repo-root FastAPI shim (openenv.yaml)
       └──────────┬───────────┘
                  ▼
       warehouse_routing.server.app  →  create_app(Environment, ...)
                  │
                  ▼
       warehouse_routing.env.WarehouseRoutingEnvironment
         module-level _SESSION singleton (per-request factory)
```

## Dependency Graph

```
models.py ───────── (Pydantic types; no internal deps)
  ├── pathing.py ─── (A*; depends on models)
  ├── solver.py ──── (TSP; depends on models, pathing)
  ├── reward.py ──── (depends on models, sim)
  ├── grader.py ──── (depends on models)
  ├── tasks.py ───── (depends on models, solver, pathing)
  ├── sim.py ─────── (depends on models)
  ├── curriculum.py  (depends on tasks)
  ├── policies.py ── (depends on models, solver, pathing)
  ├── eval.py ────── (depends on curriculum, sim, grader, tasks, models)
  ├── env.py ─────── (OpenEnv adapter; depends on curriculum, sim, grader, reward, tasks, models)
  └── server/app.py  (depends on env, models)

inference.py ─── (depends on curriculum, eval, grader, models, policies, reward, sim, tasks)
server/app.py ── (re-exports warehouse_routing.server.app:app)
```

## Package / Module Summaries

### `warehouse_routing` — core library

**Purpose:** Gridworld environment, curriculum, solvers, and policies for the OpenEnv warehouse-routing task.

| Module | Key Exports | Notes |
|--------|------------|-------|
| `models.py` | `Cell`, `Move`, `Action`, `Observation`, `Tier` | Pydantic v2; `Action`/`Observation` subclass openenv base types (inherit `done`/`reward`/`metadata`) |
| `pathing.py` | `astar_distance()`, `astar_path()` | 4-connected A* on obstacle grid; returns hop count or Cell list |
| `solver.py` | `manhattan()`, `obstacle_aware_distance()`, `build_distance_matrix()`, `optimal_tour_length()`, `optimal_tour_order()` | Held-Karp via `python_tsp`; pluggable `DistanceFn` |
| `tasks.py` | `TaskSpec`, `Variation`, `make_variation()`, `ALL_TASKS` | Deterministic per-seed layouts for easy/medium/hard |
| `sim.py` | `GridEnv`, `StepResult` | Applies `Action`, tracks visited + step budget |
| `reward.py` | `compute_reward()`, `Reward` | Dense shaping: time penalty, invalid penalty, SKU bonus, budget exhaust |
| `grader.py` | `grade_variation()` | `optimal_length / agent_length`, clamped [0,1], 0 if unfinished |
| `curriculum.py` | `Curriculum`, `DEFAULT_TIME_LIMIT_SECONDS` | Adaptive state machine; 3-in-a-row mastery, max-attempt force-promote, 19 min wall-clock |
| `policies.py` | `RandomPolicy`, `OraclePolicy`, `VALID_MOVES` | Oracle replays Held-Karp tour via A*; doubles as solver/sim/grader drift regression |
| `eval.py` | `Policy` (Protocol), `EpisodeResult`, `EvalReport`, `evaluate()` | Reusable harness; aggregates mean/success/by-tier |
| `env.py` | `WarehouseRoutingEnvironment`, `reset_session()`, `_SESSION` | OpenEnv adapter; module-level singleton (framework builds factory per request) |
| `server/app.py` | `app`, `main()` | `create_app(WarehouseRoutingEnvironment, ...)` + uvicorn runner |

**External deps:** `pydantic`, `python-tsp`, `numpy`, `fastapi`, `uvicorn`, `openenv-core`, `openai` (inference only)

### Top-level

| File | Purpose |
|------|---------|
| `inference.py` | Hackathon entrypoint; OpenAIPolicy + curriculum loop; emits `[START]/[STEP]/[END]` logs |
| `server/app.py` | Repo-root shim re-exporting `warehouse_routing.server.app:app`; validator scans for `main` literal |
| `openenv.yaml` | OpenEnv manifest: `app: server.app:app`, port 8000 |
| `Dockerfile` | Multi-stage build on `ghcr.io/meta-pytorch/openenv-base`; copies uv-managed Python |

## Test Inventory

| File | Tests | Focus |
|------|-------|-------|
| `test_curriculum.py` | 12 | Mastery promotion, force-promote, wall-clock, reproducibility |
| `test_env_adapter.py` | 3 | OpenEnv session lifecycle (reset/step/done) |
| `test_grader.py` | 6 | Optimal/agent ratio, success gating |
| `test_grader_validation.py` | 5 | Invariant and boundary checks |
| `test_models.py` | 7 | Pydantic validation, Action/Observation shape |
| `test_pathing.py` | 11 | `astar_distance` + `astar_path`: contiguity, detours, unreachable |
| `test_policies.py` | 3 | Oracle scores 1.0 (regression check), Random bounded |
| `test_reward.py` | 6 | Shaped reward components |
| `test_sim.py` | 8 | GridEnv step semantics, budget, visit tracking |
| `test_smoke.py` | 1 | Import-level sanity |
| `test_solver.py` | 11 | Held-Karp correctness, `optimal_tour_order` shape + obstacle path |
| `test_tasks.py` | 12 | Deterministic variation builder per tier |
| **Total** | **85** | |

## Key Type Flow

```
TaskSpec ─► make_variation(seed, attempt) ─► Variation
                                               │
                                               ├─► Observation (initial state)
                                               │      │
                                               │      ▼
                                               │   GridEnv.step(Action) ─► StepResult
                                               │                            │
                                               │                            ├─► compute_reward() ─► Reward
                                               │                            └─► StepResult.observation (next)
                                               │
                                               └─► optimal_length  ─► grade_variation(final_obs) ─► score ∈ [0,1]

Policy.choose(obs) ─► Move ─► Action(move=...)
```

## Config / Environment

| Variable | Purpose | Default |
|----------|---------|---------|
| `API_BASE_URL` | LLM endpoint (inference.py) | `https://router.huggingface.co/v1` |
| `MODEL_NAME` | Model id for inference | `Qwen/Qwen2.5-72B-Instruct` |
| `HF_TOKEN` / `API_KEY` | API auth | required unless `--dry-run` |

Curriculum constants (`curriculum.py`): `MASTERY_STREAK=3`, `MASTERY_SCORE=0.9`, `MAX_ATTEMPTS=20`, `DEFAULT_TIME_LIMIT_SECONDS=1140`.

Reward constants (`reward.py`): `TIME_PENALTY=-0.01`, `INVALID_PENALTY=-0.05`, `SKU_VISIT_BONUS=0.1`, `BUDGET_EXHAUST_PENALTY=-0.2`.
