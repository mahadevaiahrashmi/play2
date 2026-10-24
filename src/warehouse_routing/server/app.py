# agent-notes: { ctx: "FastAPI app exposing WarehouseRoutingEnvironment over HTTP", deps: [src/warehouse_routing/env.py, src/warehouse_routing/models.py], state: active, last: "sato@2026-04-14" }
"""FastAPI entrypoint for the warehouse-routing OpenEnv environment.

Endpoints (provided by openenv-core's `create_app`):
    POST /reset   -> initial Observation
    POST /step    -> Observation after applying an Action
    GET  /state   -> current episode state
    GET  /schema  -> action/observation JSON schema
    GET  /health  -> liveness

Added by ``server.hardening`` (see its docstring): clean JSON errors, GET /healthz,
GET /metrics, and isolated per-client episodes under /sessions.
"""

from openenv.core.env_server.http_server import create_app

from warehouse_routing.env import WarehouseRoutingEnvironment
from warehouse_routing.models import Action, Observation
from warehouse_routing.server.hardening import install_hardening
from warehouse_routing.server.ui import mount_ui

app = create_app(
    WarehouseRoutingEnvironment,
    Action,
    Observation,
    env_name="warehouse_routing",
    max_concurrent_envs=1,
)

mount_ui(app)
install_hardening(app)


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
