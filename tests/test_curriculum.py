# agent-notes: { ctx: "curriculum state machine: mastery, streak reset, force-promote, termination", deps: [src/warehouse_routing/curriculum.py], state: active, last: "sato@2026-04-14" }
import pytest

from warehouse_routing.curriculum import (
    MASTERY_STREAK,
    MAX_ATTEMPTS,
    Curriculum,
)


def test_starts_at_easy_attempt_one() -> None:
    c = Curriculum()
    spec, seed, attempt = c.next_variation()
    assert spec.tier == "easy"
    assert attempt == 1
    assert not c.is_done()


def test_three_in_a_row_masters_easy() -> None:
    c = Curriculum()
    for _ in range(MASTERY_STREAK):
        c.record_score(1.0)
    assert c.state.mastered["easy"] is True
    assert c.current_spec().tier == "medium"
    assert c.state.attempt_in_tier == 1
    assert c.state.streak == 0


def test_low_score_resets_streak() -> None:
    c = Curriculum()
    c.record_score(1.0)
    c.record_score(1.0)
    c.record_score(0.5)  # breaks streak
    c.record_score(1.0)
    c.record_score(1.0)
    assert c.current_spec().tier == "easy"  # still not mastered
    assert c.state.streak == 2


def test_force_promote_after_max_attempts() -> None:
    c = Curriculum()
    for _ in range(MAX_ATTEMPTS):
        c.record_score(0.1)
    assert c.state.mastered["easy"] is False
    assert c.current_spec().tier == "medium"


def test_mastery_short_circuits_force_promote() -> None:
    c = Curriculum()
    # 3 good -> master, even if under max attempts
    for _ in range(MASTERY_STREAK):
        c.record_score(0.95)
    assert c.state.mastered["easy"] is True


def test_full_curriculum_terminates() -> None:
    c = Curriculum()
    for _ in range(3 * MASTERY_STREAK):  # master easy, medium, hard
        c.record_score(1.0)
    assert c.is_done()
    with pytest.raises(RuntimeError):
        c.record_score(1.0)


def test_seeds_vary_across_attempts() -> None:
    c = Curriculum(master_seed=100)
    seeds = []
    for _ in range(5):
        _spec, seed, _ = c.next_variation()
        seeds.append(seed)
        c.record_score(0.5)
    assert len(set(seeds)) == 5


def test_seeds_vary_across_tiers() -> None:
    c = Curriculum(master_seed=0)
    _, easy_seed, _ = c.next_variation()
    for _ in range(MASTERY_STREAK):
        c.record_score(1.0)
    _, medium_seed, _ = c.next_variation()
    assert easy_seed != medium_seed


def test_reset_clears_state() -> None:
    c = Curriculum()
    for _ in range(MASTERY_STREAK):
        c.record_score(1.0)
    c.reset()
    assert c.current_spec().tier == "easy"
    assert c.state.mastered == {}
    assert not c.is_done()


def test_summary_reports_full_history() -> None:
    c = Curriculum()
    c.record_score(1.0)
    c.record_score(0.3)
    summary = c.summary()
    assert summary["n_attempts"] == 2
    history = summary["history"]
    assert isinstance(history, list) and len(history) == 2


def test_wall_clock_cap_terminates_early() -> None:
    fake_time = [0.0]

    def clock() -> float:
        return fake_time[0]

    c = Curriculum(time_limit_seconds=100.0, clock=clock)
    c.next_variation()  # starts the clock at 0
    fake_time[0] = 50.0
    c.record_score(1.0)  # still under the cap
    assert not c.is_done()
    fake_time[0] = 150.0  # past the cap
    c.record_score(1.0)
    assert c.is_done()
    assert c.state.mastered.get("easy") is False


def test_no_time_limit_never_auto_terminates() -> None:
    c = Curriculum(time_limit_seconds=None)
    for _ in range(MAX_ATTEMPTS - 1):
        c.record_score(0.1)
    assert not c.is_done()
