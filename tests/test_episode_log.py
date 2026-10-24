"""episode_log: JSONL episodes, deterministic replay, idempotent run ids, dead letters."""

import json
from pathlib import Path

import pytest

from warehouse_routing.episode_log import (
    DeadLetter,
    DeadLetterLog,
    EpisodeLog,
    EpisodeRecord,
    ReplayMismatch,
    StepRecord,
    make_run_id,
    replay_dead_letters,
    replay_episode,
)
from warehouse_routing.grader import grade_variation
from warehouse_routing.models import Action
from warehouse_routing.policies import GreedyPolicy
from warehouse_routing.reward import compute_reward
from warehouse_routing.sim import GridEnv
from warehouse_routing.tasks import ALL_TASKS, make_variation


def play(policy_name: str, tier: str, seed: int) -> EpisodeRecord:
    spec = next(t for t in ALL_TASKS if t.tier == tier)
    variation = make_variation(spec, seed=seed, attempt=1)
    env = GridEnv(variation.observation)
    policy = GreedyPolicy()
    steps = []
    while not env.observation.done:
        move = policy.choose(env.observation)
        result = env.step(Action(move=move))
        reward = compute_reward(result, variation.optimal_length)
        o = result.observation
        steps.append(
            StepRecord(
                action=move, robot_pos=(o.robot_pos.row, o.robot_pos.col),
                visited=list(o.visited), reward=reward.value, done=result.done,
                invalid=result.invalid,
            )
        )
    final = env.observation
    return EpisodeRecord(
        run_id=make_run_id(policy_name, tier, seed), policy=policy_name, tier=tier, seed=seed,
        attempt=1, optimal_length=variation.optimal_length, steps=steps,
        final_score=grade_variation(final, variation.optimal_length),
        success=all(final.visited) and final.robot_pos == final.warehouse,
    )


def test_run_id_is_deterministic_and_distinguishes_inputs() -> None:
    a = make_run_id("greedy", "easy", 3)
    assert a == make_run_id("greedy", "easy", 3)
    assert len({a, make_run_id("greedy", "easy", 4), make_run_id("greedy", "hard", 3),
                make_run_id("oracle", "easy", 3)}) == 4
    assert make_run_id("a|b", "easy", 1) != make_run_id("a", "b|easy", 1)  # no delimiter collision


def test_replay_reproduces_score_and_rewards() -> None:
    rec = play("greedy", "medium", 2)
    assert rec.final_score > 0
    assert replay_episode(rec) == rec.final_score


def test_replay_detects_tampered_score_action_and_reward() -> None:
    rec = play("greedy", "easy", 1)
    bad_score = EpisodeRecord.from_json(rec.to_json())
    bad_score.final_score = 0.5
    with pytest.raises(ReplayMismatch, match="score"):
        replay_episode(bad_score)

    bad_action = EpisodeRecord.from_json(rec.to_json())
    bad_action.steps[0].action = "S" if rec.steps[0].action != "S" else "E"
    with pytest.raises(ReplayMismatch):
        replay_episode(bad_action)

    bad_reward = EpisodeRecord.from_json(rec.to_json())
    bad_reward.steps[3].reward += 0.5
    with pytest.raises(ReplayMismatch, match="reward"):
        replay_episode(bad_reward)


def test_jsonl_roundtrip_one_line_per_episode(tmp_path: Path) -> None:
    log = EpisodeLog(tmp_path / "episodes.jsonl")
    r1, r2 = play("greedy", "easy", 1), play("greedy", "easy", 2)
    assert log.append(r1) is True
    assert log.append(r2) is True
    lines = (tmp_path / "episodes.jsonl").read_text().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["seed"] == 1 and first["tier"] == "easy" and "final_score" in first
    assert {"action", "robot_pos", "visited", "reward", "done", "invalid"} <= set(first["steps"][0])
    loaded = EpisodeLog(tmp_path / "episodes.jsonl").load()
    assert [r.run_id for r in loaded] == [r1.run_id, r2.run_id]
    assert loaded[0].final_score == r1.final_score
    assert replay_episode(loaded[1]) == r2.final_score


def test_append_is_idempotent_by_run_id_even_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "e.jsonl"
    rec = play("greedy", "easy", 1)
    assert EpisodeLog(path).append(rec) is True
    fresh = EpisodeLog(path)
    assert fresh.has(rec.run_id)
    assert fresh.append(rec) is False
    assert len(path.read_text().splitlines()) == 1


def test_truncated_trailing_line_is_skipped_not_fatal(tmp_path: Path) -> None:
    path = tmp_path / "e.jsonl"
    log = EpisodeLog(path)
    log.append(play("greedy", "easy", 1))
    with path.open("a") as fh:
        fh.write('{"run_id": "half-writ')  # crash mid-write
    reloaded = EpisodeLog(path)
    assert len(reloaded.load()) == 1
    assert reloaded.corrupt_lines == 1


def test_dead_letter_roundtrip_and_replay(tmp_path: Path) -> None:
    dead = DeadLetterLog(tmp_path / "dead.jsonl")
    dead.append(DeadLetter(run_id="r1", policy="p", tier="easy", seed=1, error="boom", attempts=2))
    dead.append(DeadLetter(run_id="r2", policy="p", tier="easy", seed=2, error="bang", attempts=2))
    assert [d.run_id for d in dead.load()] == ["r1", "r2"]

    seen: list[str] = []

    def run(entry: DeadLetter) -> None:
        seen.append(entry.run_id)
        if entry.run_id == "r2":
            raise RuntimeError("still broken")

    ok, still = replay_dead_letters(dead, run)
    assert ok == ["r1"] and seen == ["r1", "r2"]
    assert [d.run_id for d in still] == ["r2"]
    remaining = DeadLetterLog(tmp_path / "dead.jsonl").load()
    assert [d.run_id for d in remaining] == ["r2"]
    assert remaining[0].attempts == 3 and "still broken" in remaining[0].error


def test_dead_letter_missing_file_is_empty(tmp_path: Path) -> None:
    assert DeadLetterLog(tmp_path / "nope.jsonl").load() == []
