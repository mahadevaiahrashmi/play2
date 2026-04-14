# agent-notes: { ctx: "smoke test: package imports", deps: [src/warehouse_routing/__init__.py], state: active, last: "sato@2026-04-14" }
import warehouse_routing


def test_import_version() -> None:
    assert warehouse_routing.__version__ == "0.0.1"
