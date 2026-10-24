"""Evaluation runner: policy x tier x seed, with budget, tracing, logging, retries.

Contract
--------
* Jobs are enumerated in a fixed order: policies in the order given, then tiers
  in ``config.tiers``, then ``config.seeds``. They execute on a bounded thread
  pool (``max_workers``) but results are collected *by job index*, so
  ``RunResult.records`` order never depends on completion order.
* Each job has an idempotent ``run_id`` (``make_run_id``). If the
  ``EpisodeLog`` already holds it, the job is skipped and the logged record is
  returned (``skipped``); otherwise the episode is played with a *fresh policy*
  from the factory, logged, and returned (``executed``).
* An episode that raises is retried up to ``max_episode_attempts`` times with a
  new policy; ``BudgetExceeded`` is never retried. After the last attempt it
  goes to the dead-letter log (error text + attempt count) and into
  ``RunResult.failures``; one failing episode never aborts the run.
* Per step the runner charges the ledger (step ceilings), runs
  ``policy.choose`` inside a ``policy.choose`` span, feeds the visited state to
  the tracer's loop detector and the reward back via ``policy.record`` when the
  policy has one. Cost per episode is read from the ledger.
* Policy factories take an ``EpisodeContext`` (episode id, seed, tracer, ledger)
  and return anything with ``choose(obs) -> Move``; counters ``fallbacks`` and
  ``llm_calls`` are picked up from the policy if present.
* Concurrency note: episodes share the tracer and ledger (both thread-safe).
  Anything *stateful and shared* in a factory (e.g. one circuit breaker for all
  episodes) would make results depend on thread timing, so the provided
  factories build per-episode state.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from warehouse_routing.budget import BudgetExceeded, BudgetLedger
from warehouse_routing.episode_log import (
    DeadLetter,
    DeadLetterLog,
    EpisodeLog,
    EpisodeRecord,
    StepRecord,
    make_run_id,
    replay_dead_letters,
)
from warehouse_routing.eval import Policy
from warehouse_routing.grader import grade_variation
from warehouse_routing.models import Action
from warehouse_routing.reward import compute_reward
from warehouse_routing.sim import GridEnv
from warehouse_routing.tasks import ALL_TASKS, make_variation
from warehouse_routing.tracing import Tracer


@dataclass(frozen=True)
class EpisodeContext:
    policy_name: str
    run_id: str
    episode_id: str
    tier: str
    seed: int
    attempt: int
    tracer: Tracer
    ledger: BudgetLedger


PolicyFactory = Callable[[EpisodeContext], Policy]


@dataclass(frozen=True)
class RunConfig:
    tiers: tuple[str, ...] = ("easy", "medium", "hard")
    seeds: Sequence[int] = tuple(range(5))
    max_workers: int = 4
    max_episode_attempts: int = 2


@dataclass
class RunResult:
    records: list[EpisodeRecord]
    failures: list[DeadLetter]
    executed: int = 0
    skipped: int = 0
    tiers: tuple[str, ...] = field(default_factory=tuple)


class EvalRunner:
    def __init__(
        self,
        policies: Mapping[str, PolicyFactory],
        config: RunConfig | None = None,
        *,
        log: EpisodeLog | None = None,
        dead: DeadLetterLog | None = None,
        tracer: Tracer | None = None,
        ledger: BudgetLedger | None = None,
        on_episode_done: Callable[[EpisodeRecord], None] | None = None,
    ) -> None:
        config = config if config is not None else RunConfig()
        if config.max_workers < 1 or config.max_episode_attempts < 1:
            raise ValueError("max_workers and max_episode_attempts must be >= 1")
        self.policies = dict(policies)
        self.config = config
        self.log = log
        self.dead = dead
        self.tracer = tracer if tracer is not None else Tracer()
        self.ledger = ledger if ledger is not None else BudgetLedger(prices={})
        self._on_done = on_episode_done

    # -- one episode ---------------------------------------------------------
    def play(self, policy_name: str, tier: str, seed: int, attempt: int = 1) -> EpisodeRecord:
        run_id = make_run_id(policy_name, tier, seed)
        spec = next(t for t in ALL_TASKS if t.tier == tier)
        variation = make_variation(spec, seed=seed, attempt=1)
        ctx = EpisodeContext(policy_name, run_id, run_id, tier, seed, attempt,
                             self.tracer, self.ledger)
        with self.tracer.episode(run_id) as ep:
            policy = self.policies[policy_name](ctx)
            env = GridEnv(variation.observation)
            steps: list[StepRecord] = []
            while not env.observation.done:
                self.ledger.charge_step(run_id)
                obs = env.observation
                with self.tracer.span("policy.choose", step=obs.steps_taken):
                    move = policy.choose(obs)
                result = env.step(Action(move=move))
                reward = compute_reward(result, variation.optimal_length)
                if hasattr(policy, "record"):
                    policy.record(move, reward.value)
                o = result.observation
                pos = (o.robot_pos.row, o.robot_pos.col)
                self.tracer.observe_state((pos, tuple(o.visited)))
                steps.append(StepRecord(move, pos, list(o.visited), reward.value,
                                        result.done, result.invalid))
            final = env.observation
            cost = self.ledger.episode_cost(run_id)
            self.tracer.add_cost(cost)
            return EpisodeRecord(
                run_id=run_id, policy=policy_name, tier=tier, seed=seed, attempt=1,
                optimal_length=variation.optimal_length, steps=steps,
                final_score=grade_variation(final, variation.optimal_length),
                success=all(final.visited) and final.robot_pos == final.warehouse,
                cost=cost,
                fallbacks=int(getattr(policy, "fallbacks", 0)),
                alerts=ep.alerts,
                llm_calls=int(getattr(policy, "llm_calls", 0)),
            )

    # -- job handling -------------------------------------------------------
    def _job(self, job: tuple[str, str, int]) -> tuple[EpisodeRecord | None, DeadLetter | None]:
        name, tier, seed = job
        run_id = make_run_id(name, tier, seed)
        error = ""
        attempts = 0
        for attempt in range(1, self.config.max_episode_attempts + 1):
            attempts = attempt
            try:
                record = self.play(name, tier, seed, attempt)
            except BudgetExceeded as exc:
                error = f"{type(exc).__name__}: {exc}"
                break  # not retryable
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                continue
            if self.log is not None:
                self.log.append(record)
            if self._on_done is not None:
                self._on_done(record)
            return record, None
        entry = DeadLetter(run_id=run_id, policy=name, tier=tier, seed=seed,
                           error=error, attempts=attempts)
        if self.dead is not None:
            self.dead.append(entry)
        return None, entry

    def run(self) -> RunResult:
        jobs = [
            (name, tier, seed)
            for name in self.policies
            for tier in self.config.tiers
            for seed in self.config.seeds
        ]
        logged = {r.run_id: r for r in self.log.load()} if self.log is not None else {}
        slots: list[tuple[EpisodeRecord | None, DeadLetter | None]] = [(None, None)] * len(jobs)
        pending: list[int] = []
        skipped = 0
        for i, (name, tier, seed) in enumerate(jobs):
            existing = logged.get(make_run_id(name, tier, seed))
            if existing is not None:
                slots[i] = (existing, None)
                skipped += 1
            else:
                pending.append(i)

        with ThreadPoolExecutor(max_workers=self.config.max_workers) as pool:
            futures = {i: pool.submit(self._job, jobs[i]) for i in pending}
            for i, fut in futures.items():  # collected by job index, not completion order
                slots[i] = fut.result()

        return RunResult(
            records=[r for r, _ in slots if r is not None],
            failures=[f for _, f in slots if f is not None],
            executed=len(pending) - sum(1 for i in pending if slots[i][1] is not None),
            skipped=skipped,
            tiers=tuple(self.config.tiers),
        )

    def replay_dead_letters(self) -> tuple[list[str], list[DeadLetter]]:
        if self.dead is None:
            raise ValueError("no dead-letter log configured")

        def rerun(entry: DeadLetter) -> None:
            record = self.play(entry.policy, entry.tier, entry.seed)
            if self.log is not None:
                self.log.append(record)

        return replay_dead_letters(self.dead, rerun)
