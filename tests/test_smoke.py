# agent-notes: { ctx: "smoke test: package imports + /ui route", deps: [src/warehouse_routing/__init__.py, src/warehouse_routing/server/app.py], state: active, last: "sato@2026-04-15" }
from fastapi.testclient import TestClient

import warehouse_routing
from warehouse_routing.server.app import app


def test_import_version() -> None:
    assert warehouse_routing.__version__ == "0.0.1"


def test_ui_route_serves_grid_viewer() -> None:
    client = TestClient(app)
    r = client.get("/ui")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert '<svg id="grid"' in body
    assert 'id="b-reset"' in body
    assert 'class="dpad"' in body
    # Regression guard: the deployed Space once shipped a refresh() that
    # reassigned `latest = data` from /state (which has no observation),
    # blanking the panel one second after reset. Don't let it come back.
    assert "latest = data" not in body
