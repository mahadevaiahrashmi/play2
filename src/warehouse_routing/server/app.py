# agent-notes: { ctx: "FastAPI app exposing WarehouseRoutingEnvironment over HTTP", deps: [src/warehouse_routing/env.py, src/warehouse_routing/models.py], state: active, last: "sato@2026-04-14" }
"""FastAPI entrypoint for the warehouse-routing OpenEnv environment.

Endpoints (provided by openenv-core's `create_app`):
    POST /reset   -> initial Observation
    POST /step    -> Observation after applying an Action
    GET  /state   -> current episode state
    GET  /schema  -> action/observation JSON schema
    GET  /health  -> liveness
"""

from openenv.core.env_server.http_server import create_app

from warehouse_routing.env import WarehouseRoutingEnvironment
from warehouse_routing.models import Action, Observation

app = create_app(
    WarehouseRoutingEnvironment,
    Action,
    Observation,
    env_name="warehouse_routing",
    max_concurrent_envs=1,
)


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
