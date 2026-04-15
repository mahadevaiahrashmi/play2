#!/usr/bin/env python
# agent-notes: { ctx: "baseline inference entrypoint; OpenAI client + [START]/[STEP]/[END] logs", deps: [src/warehouse_routing/tasks.py, src/warehouse_routing/sim.py, src/warehouse_routing/reward.py, src/warehouse_routing/grader.py], state: active, last: "sato@2026-04-14" }
"""
Inference Script
================

MANDATORY
- Before submitting, the following env vars must be set:
    API_BASE_URL   The LLM endpoint.
    MODEL_NAME     The model identifier.
    HF_TOKEN       Hugging Face / API key.

- This file must be named ``inference.py`` and sit in the repo root.
- All LLM calls must go through the OpenAI client.

STDOUT FORMAT (per hackathon spec, field names and ordering are load-bearing)

    [START] task=<task_name> env=<benchmark> model=<model_name>
    [STEP]  step=<n> action=<action_str> reward=<0.00> done=<true|false> error=<msg|null>
    [END]   success=<true|false> steps=<n> score=<score> rewards=<r1,r2,...,rn>

Rules:
    - One [START] per variation.
    - One [STEP] per env.step() call.
    - One [END] per variation, always emitted (even on exception).
    - reward and rewards formatted to 2 decimals; score to 3 decimals.
    - done / success lowercase booleans.
    - error = raw error string or "null".

OFFLINE SMOKE
    python inference.py --dry-run
    (uses a random policy, makes no network calls)
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
import traceback
from dataclasses import dataclass

from warehouse_routing.curriculum import DEFAULT_TIME_LIMIT_SECONDS, Curriculum
from warehouse_routing.eval import Policy
from warehouse_routing.grader import grade_variation
from warehouse_routing.models import Action, Move, Observation
from warehouse_routing.policies import VALID_MOVES, RandomPolicy
from warehouse_routing.reward import compute_reward
from warehouse_routing.sim import GridEnv, StepResult
from warehouse_routing.tasks import TaskSpec, make_variation

API_BASE_URL = os.getenv("API_BASE_URL") or "https://api.groq.com/openai/v1"
MODEL_NAME = os.getenv("MODEL_NAME") or "llama-3.3-70b-versatile"
API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("HF_TOKEN") or os.getenv("API_KEY")

BENCHMARK = "warehouse_routing"

SYSTEM_PROMPT = (
    "You control a warehouse autonomous mobile robot (AMR) on a grid. Your goal: "
    "visit every SKU cell, then return to the packing station (warehouse), using "
    "the fewest moves. Obstacles block movement; leaving the grid is invalid.\n"
    "Each turn you receive the current state as JSON. Respond with EXACTLY ONE of "
    "N, S, E, W (single uppercase letter). No explanation."
)


# ---------------------------------------------------------------------------
# Logging helpers — field order and formatting must match spec exactly.
# ---------------------------------------------------------------------------


def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: str | None) -> None:
    error_val = error if error else "null"
    done_val = str(done).lower()
    print(
        f"[STEP] step={step} action={action} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: list[float]) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.3f} rewards={rewards_str}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------


HISTORY_WINDOW = 8


@dataclass
class OpenAIPolicy:
    client: object  # openai.OpenAI, left untyped to avoid hard import at module scope
    model: str
    history: list[dict] = None  # type: ignore[assignment]
    last_steps_taken: int = -1

    def __post_init__(self) -> None:
        self.history = []

    def reset(self) -> None:
        self.history = []
        self.last_steps_taken = -1

    def choose(self, obs: Observation) -> Move:
        # New episode detection: step counter went backward (or first call).
        if obs.steps_taken <= self.last_steps_taken:
            self.history = []
        self.last_steps_taken = obs.steps_taken

        recent = self.history[-HISTORY_WINDOW:]
        history_str = (
            "; ".join(f"{h['action']}->r={h['reward']:.2f}" for h in recent) if recent else "none"
        )
        user_content = (
            f"recent_moves: {history_str}\n"
            f"state: {obs.model_dump_json()}"
        )
        try:
            completion = self.client.chat.completions.create(  # type: ignore[attr-defined]
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=4,
                temperature=0.0,
            )
            text = (completion.choices[0].message.content or "").strip().upper()
        except Exception as exc:  # pragma: no cover - network path
            print(f"[DEBUG] LLM call failed: {exc}", flush=True)
            return "N"
        m = re.search(r"[NSEW]", text)
        return m.group(0) if m else "N"  # type: ignore[return-value]

    def record(self, action: Move, reward: float) -> None:
        self.history.append({"action": action, "reward": reward})


def build_policy(dry_run: bool) -> Policy:
    if dry_run:
        return RandomPolicy(rng=random.Random(0))
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        print(f"[ERROR] openai package missing: {exc}", file=sys.stderr)
        sys.exit(2)
    if not API_KEY:
        print("[ERROR] HF_TOKEN (or API_KEY) must be set, or pass --dry-run", file=sys.stderr)
        sys.exit(2)
    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)
    return OpenAIPolicy(client=client, model=MODEL_NAME)


# ---------------------------------------------------------------------------
# Run a single variation
# ---------------------------------------------------------------------------


def _step_error(result: StepResult) -> str | None:
    return "invalid_move" if result.invalid else None


def run_variation(spec: TaskSpec, seed: int, attempt: int, policy: Policy, model_label: str) -> float:
    variation = make_variation(spec, seed=seed, attempt=attempt)
    env = GridEnv(variation.observation)
    task_name = f"{spec.tier}-seed{seed}-attempt{attempt}"

    rewards: list[float] = []
    steps_taken = 0
    score = 0.0
    success = False

    log_start(task=task_name, env=BENCHMARK, model=model_label)
    try:
        while not env.observation.done:
            obs = env.observation
            move = policy.choose(obs)
            result = env.step(Action(move=move))
            reward = compute_reward(result, variation.optimal_length)
            rewards.append(reward.value)
            if hasattr(policy, "record"):
                policy.record(move, reward.value)  # type: ignore[attr-defined]
            steps_taken = result.observation.steps_taken
            log_step(
                step=steps_taken,
                action=move,
                reward=reward.value,
                done=result.done,
                error=_step_error(result),
            )
        final = env.observation
        success = all(final.visited) and final.robot_pos == final.warehouse
        score = grade_variation(final, variation.optimal_length)
    except Exception as exc:
        traceback.print_exc()
        log_end(success=False, steps=steps_taken, score=0.0, rewards=rewards)
        raise exc
    log_end(success=success, steps=steps_taken, score=score, rewards=rewards)
    return score


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="random policy, no network")
    parser.add_argument(
        "--max-variations",
        type=int,
        default=0,
        help="hard cap on total variations (default: curriculum termination)",
    )
    parser.add_argument("--master-seed", type=int, default=0)
    args = parser.parse_args()

    policy = build_policy(args.dry_run)
    model_label = "random-dryrun" if args.dry_run else MODEL_NAME

    # Dry-run skips the wall-clock cap so the smoke test is deterministic;
    # real runs honor the default 19-minute budget from the curriculum.
    curriculum = Curriculum(
        master_seed=args.master_seed,
        time_limit_seconds=None if args.dry_run else DEFAULT_TIME_LIMIT_SECONDS,
    )

    scores: list[float] = []
    while not curriculum.is_done():
        if args.max_variations and len(scores) >= args.max_variations:
            break
        spec, seed, attempt = curriculum.next_variation()
        score = run_variation(spec, seed, attempt, policy, model_label)
        scores.append(score)
        curriculum.record_score(score)

    mean = sum(scores) / len(scores) if scores else 0.0
    summary = curriculum.summary()
    print(
        f"[SUMMARY] mean_score={mean:.3f} n={len(scores)} mastered={summary['mastered']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
