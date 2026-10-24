"""Server hardening: clean errors, /healthz, /metrics, isolated per-session episodes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from warehouse_routing.env import reset_session
from warehouse_routing.metrics import METRICS, Metrics
from warehouse_routing.policies import GreedyPolicy
from warehouse_routing.server.app import app as real_app
from warehouse_routing.server.hardening import SessionStore, install_hardening


@pytest.fixture(autouse=True)
def _fresh_state() -> None:
    METRICS.reset()
    reset_session(master_seed=0)


@pytest.fixture
def client() -> TestClient:
    return TestClient(real_app, raise_server_exceptions=False)


def isolated_client(max_sessions: int = 100) -> TestClient:
    app = FastAPI()
    install_hardening(app, store=SessionStore(max_sessions=max_sessions), metrics=Metrics())
    return TestClient(app, raise_server_exceptions=False)


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_validation_errors_are_clean_json_without_input_echo(client: TestClient) -> None:
    r = client.post("/step", json={"action": {"move": "X"}})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error"
    assert body["detail"][0]["field"] == "move"  # openenv validates the inner action model
    assert "input" not in body["detail"][0] and "url" not in str(body)
    bad_json = client.post("/step", content="not json", headers={"content-type": "application/json"})
    assert bad_json.status_code == 422 and bad_json.json()["error"] == "validation_error"


def test_step_before_reset_is_a_409_json_not_a_500(client: TestClient) -> None:
    r = client.post("/step", json={"action": {"move": "E"}})
    assert r.status_code == 409
    assert r.json() == {"error": "episode_not_started", "detail": "call /reset before /step"}


def test_unexpected_errors_return_json_500() -> None:
    app = FastAPI()
    install_hardening(app, store=SessionStore(), metrics=Metrics())

    @app.get("/boom")
    def boom() -> None:
        raise ValueError("secret internals")

    r = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500
    assert r.json() == {"error": "internal_error", "detail": "unexpected server error"}  # no leak


def test_metrics_track_singleton_env_episodes(client: TestClient) -> None:
    m0 = client.get("/metrics").json()
    assert m0 == {
        "episodes_started": 0, "episodes_completed": 0, "episodes_abandoned": 0,
        "active_episodes": 0, "mean_score": None, "steps_total": 0, "open_sessions": 0,
    }
    client.post("/reset", json={})
    assert client.get("/metrics").json()["active_episodes"] == 1
    done = False
    while not done:
        done = client.post("/step", json={"action": {"move": "N"}}).json()["done"]
    m = client.get("/metrics").json()
    assert m["episodes_started"] == 1 and m["episodes_completed"] == 1
    assert m["active_episodes"] == 0 and m["mean_score"] == 0.0 and m["steps_total"] == 64
    client.post("/reset", json={})
    client.post("/reset", json={})  # second reset abandons the first unfinished episode
    m = client.get("/metrics").json()
    assert m["episodes_abandoned"] == 1 and m["active_episodes"] == 1


def test_sessions_are_isolated_and_deterministic() -> None:
    c = isolated_client()
    a = c.post("/sessions", json={"tier": "easy", "seed": 3}).json()
    b = c.post("/sessions", json={"tier": "easy", "seed": 3}).json()
    assert a["session_id"] != b["session_id"]
    assert a["observation"] == b["observation"]  # same seed -> same variation
    r = c.post(f"/sessions/{a['session_id']}/step", json={"action": {"move": "E"}}).json()
    assert r["observation"]["steps_taken"] == 1
    untouched = c.get(f"/sessions/{b['session_id']}").json()
    assert untouched["observation"]["steps_taken"] == 0
    assert untouched["observation"]["robot_pos"] == {"row": 0, "col": 0}


def test_session_can_be_played_to_completion_with_matching_score() -> None:
    c = isolated_client()
    created = c.post("/sessions", json={"tier": "easy", "seed": 1}).json()
    sid, obs = created["session_id"], created["observation"]
    from warehouse_routing.models import Observation

    policy, o, done, last = GreedyPolicy(), Observation.model_validate(obs), False, {}
    while not done:
        move = policy.choose(o)
        last = c.post(f"/sessions/{sid}/step", json={"action": {"move": move}}).json()
        o, done = Observation.model_validate(last["observation"]), last["done"]
    assert last["score"] is not None and 0.0 < last["score"] <= 1.0
    again = c.post(f"/sessions/{sid}/step", json={"action": {"move": "N"}})
    assert again.status_code == 409 and again.json()["error"] == "episode_finished"


def test_session_errors_are_clean() -> None:
    c = isolated_client()
    r = c.get("/sessions/nope")
    assert r.status_code == 404 and r.json()["error"] == "not_found"
    assert c.post("/sessions", json={"tier": "impossible"}).status_code == 422
    assert c.post("/sessions", json={"seed": -1}).status_code == 422
    sid = c.post("/sessions", json={}).json()["session_id"]
    assert c.post(f"/sessions/{sid}/step", json={"action": {"move": "Q"}}).status_code == 422
    assert c.delete(f"/sessions/{sid}").status_code == 200
    assert c.delete(f"/sessions/{sid}").status_code == 404


def test_session_cap_returns_429_but_evicts_finished_sessions_first() -> None:
    c = isolated_client(max_sessions=2)
    s1 = c.post("/sessions", json={}).json()["session_id"]
    c.post("/sessions", json={})
    r = c.post("/sessions", json={})
    assert r.status_code == 429 and r.json()["error"] == "too_many_sessions"
    # finish s1 (budget exhaustion by bumping the north wall) -> it becomes evictable
    done = False
    while not done:
        done = c.post(f"/sessions/{s1}/step", json={"action": {"move": "N"}}).json()["done"]
    assert c.post("/sessions", json={}).status_code == 200
    assert c.get(f"/sessions/{s1}").status_code == 404


def test_session_activity_feeds_the_shared_metrics() -> None:
    metrics = Metrics()
    app = FastAPI()
    install_hardening(app, store=SessionStore(), metrics=metrics)
    c = TestClient(app)
    sid = c.post("/sessions", json={}).json()["session_id"]
    assert metrics.snapshot()["active_episodes"] == 1
    c.post(f"/sessions/{sid}/step", json={"action": {"move": "E"}})
    c.delete(f"/sessions/{sid}")  # deleting an unfinished session abandons it
    snap = c.get("/metrics").json()
    assert snap["active_episodes"] == 0 and snap["episodes_abandoned"] == 1
    assert snap["steps_total"] == 1 and snap["open_sessions"] == 0


def test_other_http_errors_keep_status_and_detail(client: TestClient) -> None:
    r = client.get("/definitely-not-a-route")
    assert r.status_code == 404
    assert r.json() == {"error": "http_error", "detail": "Not Found"}
