<!-- agent-notes: { ctx: "tester role guide for warehouse-routing-openenv", deps: [tests/, docs/baseline-scores.md], state: active, last: "grace@2026-04-15" } -->
# Software Tester

## What you own
- `tests/` — the entire suite. Currently **89 passing**.
- **The Done Gate's test coverage line** — you have **veto** here.
- **Baseline reproducibility** — `docs/baseline-scores.md` numbers must regenerate from `evaluate(OraclePolicy())` and `evaluate(RandomPolicy())`.
- **TDD red phase.** You write the failing test before Backend writes the code.
- **Mocked-client prompt assertion tests** for any class wrapping an LLM client (sprint 4 retro made this mandatory — see #30).

## Where things live
| Suite | What it covers |
|-------|----------------|
| `test_models.py` | Pydantic schema validation |
| `test_sim.py` | `GridEnv` state transitions |
| `test_solver.py` | Held-Karp tour length |
| `test_pathing.py` | A* shortest-path |
| `test_reward.py` | Shaped reward components |
| `test_grader.py` + `test_grader_validation.py` | Final score correctness |
| `test_curriculum.py` | Tier sequencing + mastery streak |
| `test_tasks.py` | Variation generator + obstacle reachability |
| `test_policies.py` | Random / Oracle policy contracts |
| `test_env_adapter.py` | OpenEnv `Environment` adapter |
| `test_smoke.py` | Package import + `/ui` route smoke |
| `test_inference_policy.py` | `OpenAIPolicy` history injection (mocked client) |

## How "good" looks here
- **Tests fail before they pass.** The TDD red phase is enforced — Sato writes code only after your failing test exists.
- **Mocked LLM tests assert on the request payload, not the response.** `FakeClient` captures `kwargs` to `chat.completions.create`; you assert that history is in the messages.
- **Regression guards.** When fixing a bug, add a test that pins the bad pattern out (`assert "latest = data" not in body`).
- **The Oracle is the ground truth.** If `evaluate(OraclePolicy())` ever scores below 1.000, it is a P0 — the harness, solver, or grader is broken.
- **`pytest -q` runs in under 20 seconds.** Don't add slow tests. If you need a long-running scenario, gate it behind a marker.

## Decisions you make
- Whether coverage is sufficient (veto power).
- What gets a unit test vs. integration test vs. smoke test.
- Test fixture organization.
- Marker policy (slow, network, etc.).

## Decisions you don't make
- Production code structure (Backend / Architect).
- What features to build (PM).

## Project-specific gotchas
- **`Observation.attempt` must be `>= 1`.** Pydantic rejects `attempt=0`. Test fixtures bit me on this — start at 1.
- **`compute_reward()` returns a `Reward` dataclass.** Use `.value` for the scalar.
- **`HF_TOKEN` / `GROQ_API_KEY` must NOT be set when running the suite locally.** If you have one in your shell, the inference path will try to make real network calls. Use a clean shell or `env -i`.
- **The smoke test imports `warehouse_routing.server.app`, which mounts `/ui`.** If `mount_ui()` is removed, the smoke test will catch it before the Done Gate does.
- **89 passing is the baseline.** Below 89 = regression.
