<!-- agent-notes: { ctx: "tracking artifact for code review of b750bde", deps: [docs/code-reviews/2026-04-15-prompt-history-and-ui-smoke.md], state: active, last: "code-reviewer@2026-04-15" } -->
# Tracking — Code Review: Prompt History + `/ui` Smoke Test

**Date:** 2026-04-15
**Phase:** Code Review
**Status:** Complete
**Prior Phase:** Implementation (commit `b750bde`, sprint 4)
**Owner:** code-reviewer (Vik + Tara + Pierrot lenses)
**Full review:** [`docs/code-reviews/2026-04-15-prompt-history-and-ui-smoke.md`](../code-reviews/2026-04-15-prompt-history-and-ui-smoke.md)

## Scope
Reviewed commit `b750bde` — `OpenAIPolicy` rolling history, `/ui` smoke test, episode-reset heuristic. Closes #26 and #27.

## Findings summary
| Severity | Count | Items |
|----------|-------|-------|
| Critical | 0 | — |
| Important | 3 | V1 (untyped dict history rows), V2 (`hasattr` duck typing for `record`), T1 (no system-prompt assertion) |
| Suggestion | 6 | V3 (`field(default_factory=list)`), V4 (`Optional[int]` sentinel), T2 (`choose()` without `record()`), T3 (parametrized obs fixture), P1 (warehouse layout to third-party LLM — doc gap), P2 (SDK exception leakage) |
| **Total** | **9** | — |

## Verdict
Ship-clean. No Critical. Important items are maintainability/coverage gaps, not correctness bugs.

## Resolution status
**All findings deferred to the next `inference.py` touch** (likely "beat the Llama 0.000 baseline" sprint). None block the current sprint or warrant a follow-up commit on this branch.

## Follow-up actions
- **No issues filed.** The findings live in this review doc and will be picked up when `inference.py` is next touched. Filing 9 issues for a 38-line diff would be ceremony over substance.
- **Lesson #5 from the review** ("HTTP routes need a backend test in the same commit") is already encoded in sprint 2 backlog item #30.
- **Finding P1** (warehouse layout to third-party LLM) should be added to the AI Engineer role guide as a project-specific gotcha. Tracked here, not as an issue.

## Links
- Review doc: `docs/code-reviews/2026-04-15-prompt-history-and-ui-smoke.md`
- Implementation commit: `b750bde`
- Closed issues: #26, #27
- Related sprint 2 backlog: #30 (mocked-prompt test mandate, addresses Lesson #5)
