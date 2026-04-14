# agent-notes: { ctx: "public README: motivation, spec, setup, baseline", deps: [inference.py, openenv.yaml, docs/baseline-scores.md], state: active, last: "sato@2026-04-14" }

# warehouse-routing-openenv

An [OpenEnv](https://github.com/meta-pytorch/OpenEnv)-compliant gridworld
environment that trains and evaluates LLM agents on **multi-stop warehouse
routing**. An autonomous mobile robot (AMR) must visit every SKU location in a
warehouse and return to the packing station using the fewest moves possible.
Agents are graded against the optimal TSP solution for each variation.

Built to the [Meta PyTorch OpenEnv Hackathon](https://www.scaler.com/school-of-technology/meta-pytorch-hackathon/)
Round 1 spec as a learning / portfolio project.

## Motivation

Last-mile pick-and-pack is a well-studied operations research problem — TSP
with obstacles, a step budget, and a return-to-origin constraint. It is
small enough to admit optimal solutions (so grading is objective), large
enough to be non-trivial for an LLM prompted cold, and directly connected to
real AMR fleet planning. Three tiers (Easy / Medium / Hard) stress increasing
grid size, SKU count, obstacle density, and step budget.

## Task & grading

Each variation is a 2D grid containing:

- A **warehouse** cell (the packing station, always `(0, 0)`).
- A set of **SKU locations** (pick targets).
- A set of **obstacles** (blocked cells).
- A hard **step budget**.

The agent wins when every SKU has been visited **and** the robot is back at
the warehouse within the step budget. Score:

```
score = optimal_length / agent_length   (clamped to [0, 1])
score = 0                                (if not all SKUs visited or not returned)
```

Optimal length is computed with exact TSP (Held-Karp via `python-tsp`) over an
obstacle-aware Manhattan distance matrix built with A*.

### Tiers

| Tier   | Grid  | SKUs | Obstacle density | Step budget |
|--------|-------|------|------------------|-------------|
| Easy   | 8×8   | 3    | 0.00             | 64          |
| Medium | 16×16 | 6    | 0.10             | 200         |
| Hard   | 24×24 | 10   | 0.25             | 500         |

### Adaptive curriculum

`Curriculum` walks the agent Easy → Medium → Hard. A tier is **mastered** after
**3 consecutive variations scoring ≥ 0.9**, or **force-promoted** after 20
attempts. A default 19-minute wall-clock cap terminates the run under the
hackathon's 20-minute budget. Seeds are deterministic in
`(master_seed, tier_index, attempt)`.

## Action & observation space

### Action

```python
class Action(openenv.Action):
    move: Literal["N", "S", "E", "W"]
```

One grid cell per step, 4-connected. Pick-up and drop-off are automatic on
entering an SKU cell.

### Observation

```python
class Observation(openenv.Observation):
    grid_rows: int
    grid_cols: int
    warehouse: Cell
    sku_locations: list[Cell]
    obstacles: list[Cell]
    robot_pos: Cell
    visited: list[bool]          # parallel to sku_locations
    steps_taken: int
    step_budget: int
    tier: Literal["easy", "medium", "hard"]
    attempt: int
    variation_seed: int
    done: bool                   # inherited
    reward: float                # inherited, populated per step
    metadata: dict               # curriculum state, grader score, reward parts
```

### Reward

Dense shaped reward on every step:

| Event                 | Reward           |
|-----------------------|------------------|
| Any step (time cost)  | `-0.01`          |
| Invalid move          | `-0.05`          |
| Newly-visited SKU     | `+0.10`          |
| Terminal success      | `+optimal/agent` |
| Terminal failure      | `-0.20`          |

## Setup

Requires Python ≥ 3.12 and Docker.

```bash
git clone <this-repo>
cd warehouse-routing-openenv
uv sync                       # or: pip install -e ".[dev]"

# run the tests
pytest                        # 73 tests

# smoke-test the environment offline (random policy, no LLM)
python inference.py --dry-run --max-variations 5

# validate the OpenEnv spec
openenv validate .

# build & run the container
docker build -t warehouse-routing:dev .
docker run --rm -p 8000:8000 warehouse-routing:dev

# hit it
curl -X POST http://localhost:8000/reset -H 'content-type: application/json' -d '{}'
curl -X POST http://localhost:8000/step  -H 'content-type: application/json' -d '{"action":{"move":"E"}}'
```

## Running the LLM agent

```bash
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="Qwen/Qwen2.5-72B-Instruct"
export HF_TOKEN="hf_..."
python inference.py
```

`inference.py` logs each variation in the hackathon-mandated format:

```
[START] task=<tier-seedN-attemptM> env=warehouse_routing model=<model>
[STEP]  step=<n> action=<N|S|E|W> reward=<0.00> done=<bool> error=<msg|null>
[END]   success=<bool> steps=<n> score=<0.000> rewards=<r1,r2,...>
[SUMMARY] mean_score=<0.000> n=<N> mastered=<dict>
```

## Submission validator

Before submitting to HF Spaces, run:

```bash
./validate-submission.sh https://<your-space>.hf.space
```

Checks:

1. HF Space responds `200` to `POST /reset`
2. `docker build .` succeeds (10-min cap)
3. `openenv validate .` passes

## Baseline scores

See [`docs/baseline-scores.md`](docs/baseline-scores.md).

| Run | Policy        | n | mean_score |
|-----|---------------|---|------------|
| 1   | random-dryrun | 5 | 0.000      |

LLM baseline pending API credentials.

## Repository layout

```
.
├── inference.py                 # hackathon entrypoint (OpenAI client)
├── openenv.yaml                 # OpenEnv spec
├── Dockerfile                   # multi-stage build on openenv-base
├── validate-submission.sh       # pre-submission gate
├── server/app.py                # repo-root FastAPI entrypoint (re-exports)
├── src/warehouse_routing/
│   ├── models.py                # typed Observation / Action / Cell
│   ├── sim.py                   # GridEnv state machine
│   ├── tasks.py                 # TaskSpec, variation generator
│   ├── solver.py                # exact TSP + obstacle-aware distances
│   ├── pathing.py               # A* distance
│   ├── reward.py                # dense shaped reward
│   ├── grader.py                # 0..1 score
│   ├── curriculum.py            # adaptive Easy→Medium→Hard state machine
│   ├── env.py                   # OpenEnv Environment adapter
│   └── server/app.py            # real FastAPI app
├── tests/                       # 73 tests
└── docs/                        # plans, ADRs, baseline scores
```

## License

MIT
