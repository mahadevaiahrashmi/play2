<!-- agent-notes: { ctx: "code review of b750bde: prompt history + /ui smoke test", deps: [inference.py, tests/test_inference_policy.py, tests/test_smoke.py], state: active, last: "code-reviewer@2026-04-15" } -->
# Code Review — Prompt History + `/ui` Smoke Test

**Date:** 2026-04-15
**Commit reviewed:** `b750bde feat(inference,test): prompt history + /ui smoke test`
**Files:** `inference.py` (+33/-5), `tests/test_inference_policy.py` (+93/0, new), `tests/test_smoke.py` (+19/-1)
**Closes:** #26 (LLM baseline scores 0.000), #27 (`/ui` route has no automated test)
**Reviewer:** code-reviewer (Vik + Tara + Pierrot lenses)

## Context
Sprint 4 closed two regressions caught at sprint 3:
1. `OpenAIPolicy.choose()` was stateless — sent only the current observation to the LLM. Llama 3.3 70B baseline scored 0.000 with documented oscillation/wall-bumping. This commit adds a rolling 8-step `(action, reward)` history and an episode-boundary reset heuristic.
2. The `/ui` SVG grid viewer shipped without any automated test. A `latest = data` clobber bug regressed the panel and was only caught by manual UAT. This commit adds a backend smoke test with a regression guard string.

## Findings

### Vik — Simplicity & Maintainability

**Important — V1: `dict` for history rows is untyped magic strings.**
`self.history.append({"action": action, "reward": reward})` and the consumer `f"{h['action']}->r={h['reward']:.2f}"` carry no type information. A typo in `"action"` vs `"act"` would be a silent runtime bug. Replace with a `TypedDict` or a 2-tuple `(action, reward)` — both are cheaper than the current dict and self-documenting.

**Important — V2: `hasattr(policy, "record")` duck typing in `run_variation`.**
The fact that a policy supports per-step recording is part of its contract, not an accident. The current pattern works for `RandomPolicy` (no `record`) and `OpenAIPolicy` (has `record`), but it makes the contract invisible. Either: extend the `Policy` protocol with an optional `record(action, reward) -> None` method (default no-op), or make `record()` part of the `Policy` ABC and have `RandomPolicy` implement it as a pass. The duck-typed `hasattr` is a lurking source of "why doesn't my new policy get history?" bugs.

**Suggestion — V3: `history: list[dict] = None` + `__post_init__` is dataclass cargo-cult.**
The standard idiom is `history: list[dict] = field(default_factory=list)` from `dataclasses`. It removes the `None` placeholder, the `# type: ignore`, the `__post_init__` method, and the runtime branch. Three lines saved, intent clearer, no behavior change.

**Suggestion — V4: `last_steps_taken: int = -1` sentinel.**
Works because `steps_taken >= 0` is invariant in `sim.py:68`. But `Optional[int] = None` would document "no observations seen yet" more clearly than "-1 means nothing." Low priority — the comment on the next line carries the intent.

**Vik clean bill on:** module organization, naming (`HISTORY_WINDOW`, `recent`, `history_str` all clear), no hot-path concerns (LLM call dominates by 4+ orders of magnitude), no concurrency surface, no resource leaks.

### Tara — Test Quality & Coverage

**Important — T1: No test asserts the system prompt is in the messages payload.**
All three new tests assert on the user message content. None assert that `SYSTEM_PROMPT` is still being sent. Someone could delete the `{"role": "system", ...}` line and the suite would stay green. Add one assertion: `assert any(m["role"] == "system" and "warehouse autonomous mobile robot" in m["content"] for m in client.calls[0]["messages"])`.

**Suggestion — T2: No test covers `choose()` called multiple times without `record()` in between.**
The `record()` method is part of the contract but the test happy path always calls `record()` between `choose()` calls. If a future bug in `run_variation` skipped `record()`, the policy would silently grow no history, and there's no test pinning that. Cheap to add.

**Suggestion — T3: `_obs(steps)` builds an Observation with a fixed grid every call.**
Fine for these tests, but if you expand coverage to test serialization edge cases (large grids, many SKUs) you'll want a parametrized fixture. Defer until needed.

**Tara clean bill on:** test naming (descriptive, reads as docs), behavior-not-implementation focus, no flakiness vectors (no timing, no ordering, no network), pyramid balance (3 unit tests for 1 unit, plus 1 smoke test for an HTTP route — correct shape).

### Pierrot — Security Surface

**Suggestion — P1: `obs.model_dump_json()` ships warehouse layout to a third-party LLM (Groq).**
For a hackathon synthetic benchmark this is fine. In a real warehouse deploy this would leak operational layout (SKU positions, obstacles) to a third party. The AI Engineer role guide should call this out — it currently doesn't. Not blocking; documentation gap.

**Suggestion — P2: `[DEBUG] LLM call failed: {exc}` may leak SDK internals.**
The `openai` SDK's exception messages occasionally include request IDs and partial URLs. Low risk on a hackathon submission — pin as a follow-up before any prod-shaped use.

**Pierrot clean bill on:** no new dependencies, no auth changes, no secret handling regression (env-var precedence is sane), no new attack surface, no PII, no logging of credentials. The `API_KEY` env-var lookup adds `GROQ_API_KEY` ahead of `HF_TOKEN`/`API_KEY` — that's correct precedence given the new default endpoint.

### Migration / API / Performance

- **Migration:** none.
- **API contract:** `OpenAIPolicy.__init__` signature is unchanged for callers (the new fields have defaults). `Policy` protocol *implicitly* gains an optional `record()` method via duck typing — see V2. No breaking change.
- **Performance:** the LLM round-trip dominates wall-clock by ~4 orders of magnitude. The history-window slice (`self.history[-HISTORY_WINDOW:]`) is O(8). `model_dump_json()` is unchanged. No hot-path concern.

## Severity Summary

| Lens | Critical | Important | Suggestion |
|------|----------|-----------|-----------|
| Vik | 0 | 2 (V1, V2) | 2 (V3, V4) |
| Tara | 0 | 1 (T1) | 2 (T2, T3) |
| Pierrot | 0 | 0 | 2 (P1, P2) |
| **Total** | **0** | **3** | **6** |

**Verdict:** Ship-clean. No Critical findings. The 3 Important items are maintainability and coverage gaps, not correctness bugs — fold them into the next time `inference.py` is touched (likely the "beat the 0.000 baseline" sprint). The Suggestions are all freebies.

## Lessons (generalizable)

1. **Optional protocol methods need a real protocol.** When a method is "some implementations have this, some don't," `hasattr` *appears* lighter than an ABC, but it makes the contract invisible to new contributors and to type checkers. The cost of a `Protocol` with a default no-op is tiny; the cost of a silently-missing method on a new class is debugging hours.
2. **Tests that assert on what's *in* a request, not what's *missing*.** T1 is a classic absence-bug pattern: "the test passes whether or not you delete this line." Whenever you have a positive assertion (history is in the user message), pair it with a negative-removal-pinned assertion (system prompt is still there).
3. **Dataclass `field(default_factory=...)` is the standard idiom.** The `field: T = None; def __post_init__()` pattern shows up often when `field(default_factory=...)` would be cleaner. Small but worth internalizing — every `__post_init__` you delete saves a future reader a context switch.
4. **Sentinel `int = -1` works when an invariant guarantees the field is non-negative.** It's correct here because `sim.py:68` increments `steps_taken` from 0. But correctness depends on knowing the invariant. `Optional[int] = None` makes the intent self-documenting; the sentinel makes you trust a comment.
5. **HTTP routes need a backend test in the same commit they ship.** The `/ui` regression bug existed for an entire sprint because the route had no automated coverage. The smoke test that landed here is the right shape — assert status code, content-type, key markers, and (critically) a *regression guard string* against the specific bug pattern. Make this a Done Gate item.
