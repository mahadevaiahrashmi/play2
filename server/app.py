# agent-notes: { ctx: "openenv validator entrypoint at env root; delegates to warehouse_routing package", deps: [src/warehouse_routing/server/app.py], state: active, last: "sato@2026-04-14" }
"""Repo-root FastAPI entrypoint for `openenv validate`.

The real environment lives in `warehouse_routing.server.app`; this
module re-exports the FastAPI `app` and provides a `main()` + `__main__`
block because the OpenEnv validator scans for them literally here.
"""

from warehouse_routing.server.app import app

__all__ = ["app", "main"]


def main(host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
