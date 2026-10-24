"""HTTP hardening for the FastAPI app: clean errors, health/metrics, isolated sessions.

Contract
--------
* ``RequestValidationError`` -> ``422 {"error": "validation_error", "detail":
  [{"field", "message", "type"}]}`` (no echo of the client's input, no
  docs URLs). ``NotResetError`` (``/step`` before ``/reset``) -> ``409
  {"error": "episode_not_started"}``. Any other unhandled exception -> ``500
  {"error": "internal_error"}`` without leaking details. Other ``HTTPException``s keep
  their status and ``detail`` and gain an ``error`` key.
* ``GET /healthz`` -> ``{"status": "ok", "version": ...}``.
* ``GET /metrics`` -> JSON snapshot of ``Metrics`` plus ``open_sessions``
  (episodes started/completed/abandoned, active episodes, mean score, steps).
* ``/sessions`` API gives each client its *own* episode (``GridEnv``) so
  episodes cannot interfere, unlike openenv's ``/reset``+``/step`` which share one
  process-wide episode (``SUPPORTS_CONCURRENT_SESSIONS = False``):
  ``POST /sessions {tier, seed}``, ``GET /sessions/{id}``,
  ``POST /sessions/{id}/step {"action": {"move": "E"}}``, ``DELETE /sessions/{id}``.
  The store is capped (``max_sessions``): when full it evicts the oldest
  *finished* session, else answers ``429``. Deleting an unfinished session counts
  as abandoned. Sessions live in memory only (lost on restart).
"""

from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

import warehouse_routing
from warehouse_routing.env import NotResetError
from warehouse_routing.grader import grade_variation
from warehouse_routing.metrics import METRICS, Metrics
from warehouse_routing.models import Action, Observation, Tier
from warehouse_routing.reward import compute_reward
from warehouse_routing.sim import GridEnv
from warehouse_routing.tasks import ALL_TASKS, make_variation


class TooManySessions(RuntimeError):
    pass


@dataclass
class Session:
    id: str
    grid: GridEnv
    optimal_length: int
    score: float | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def done(self) -> bool:
        return bool(self.grid.observation.done)


class SessionStore:
    def __init__(self, max_sessions: int = 100) -> None:
        self.max_sessions = max_sessions
        self._lock = threading.Lock()
        self._sessions: OrderedDict[str, Session] = OrderedDict()

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    def create(self, tier: Tier, seed: int) -> Session:
        spec = next(t for t in ALL_TASKS if t.tier == tier)
        variation = make_variation(spec, seed=seed, attempt=1)
        with self._lock:
            if len(self._sessions) >= self.max_sessions:
                finished = next((k for k, s in self._sessions.items() if s.done), None)
                if finished is None:
                    raise TooManySessions(f"at most {self.max_sessions} concurrent sessions")
                del self._sessions[finished]
            session = Session(uuid.uuid4().hex, GridEnv(variation.observation),
                              variation.optimal_length)
            self._sessions[session.id] = session
            return session

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def delete(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.pop(session_id, None)


class CreateSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tier: Tier = "easy"
    seed: int = Field(default=0, ge=0)


class StepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Action


def _error(status: int, error: str, detail: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "detail": detail})


def install_hardening(
    app: FastAPI, *, store: SessionStore | None = None, metrics: Metrics | None = None
) -> None:
    store = store if store is not None else SessionStore()
    metrics = metrics if metrics is not None else METRICS
    app.state.sessions = store

    def clean_errors(errors: Any) -> list[dict[str, str]]:
        return [
            {
                "field": ".".join(str(p) for p in e["loc"] if p != "body" and not isinstance(p, int))
                or "body",
                "message": e["msg"],
                "type": e["type"],
            }
            for e in errors
        ]

    async def on_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(422, "validation_error", clean_errors(exc.errors()))

    async def on_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # openenv's own routes raise HTTPException(422, detail=<pydantic errors>); normalise those.
        if exc.status_code == 422 and isinstance(exc.detail, list):
            return _error(422, "validation_error", clean_errors(exc.detail))
        return _error(exc.status_code, "http_error", exc.detail)

    async def on_not_reset(request: Request, exc: NotResetError) -> JSONResponse:
        return _error(409, "episode_not_started", "call /reset before /step")

    async def on_unexpected(request: Request, exc: Exception) -> JSONResponse:
        return _error(500, "internal_error", "unexpected server error")

    app.add_exception_handler(RequestValidationError, on_validation)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, on_http)  # type: ignore[arg-type]
    app.add_exception_handler(NotResetError, on_not_reset)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, on_unexpected)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": warehouse_routing.__version__}

    @app.get("/metrics")
    def metrics_endpoint() -> dict[str, Any]:
        return {**metrics.snapshot(), "open_sessions": len(store)}

    def view(session: Session, reward: float | None = None, invalid: bool | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {
            "session_id": session.id,
            "observation": session.grid.observation.model_dump(),
            "done": session.done,
            "score": session.score,
        }
        if reward is not None:
            out["reward"] = reward
            out["invalid"] = invalid
        return out

    @app.post("/sessions")
    def create_session(body: CreateSession) -> Any:
        try:
            session = store.create(body.tier, body.seed)
        except TooManySessions as exc:
            return _error(429, "too_many_sessions", str(exc))
        metrics.episode_started()
        return view(session)

    @app.get("/sessions/{session_id}")
    def get_session(session_id: str) -> Any:
        session = store.get(session_id)
        if session is None:
            return _error(404, "not_found", "unknown session")
        return view(session)

    @app.post("/sessions/{session_id}/step")
    def step_session(session_id: str, body: StepRequest) -> Any:
        session = store.get(session_id)
        if session is None:
            return _error(404, "not_found", "unknown session")
        with session.lock:  # one step at a time per session
            if session.done:
                return _error(409, "episode_finished", "session already finished; create a new one")
            result = session.grid.step(body.action)
            reward = compute_reward(result, session.optimal_length)
            metrics.step()
            if result.done:
                session.score = grade_variation(result.observation, session.optimal_length)
                metrics.episode_finished(session.score)
            return view(session, reward.value, result.invalid)

    @app.delete("/sessions/{session_id}")
    def delete_session(session_id: str) -> Any:
        session = store.delete(session_id)
        if session is None:
            return _error(404, "not_found", "unknown session")
        if not session.done:
            metrics.episode_abandoned()
        return {"deleted": session_id}


__all__ = ["Observation", "SessionStore", "install_hardening"]
