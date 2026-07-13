from starlette.routing import Mount

from renpy_mcp.web import fastapi_app


def test_dashboard_dir_uses_frozen_bundle_root(monkeypatch, tmp_path):
    bundle_root = tmp_path / "bundle"
    dashboard = bundle_root / "dashboard" / "dist"
    dashboard.mkdir(parents=True)
    monkeypatch.setattr(fastapi_app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(fastapi_app.sys, "_MEIPASS", str(bundle_root), raising=False)

    assert fastapi_app._resolve_dashboard_dir() == dashboard


def test_create_app_allows_missing_dashboard_build(monkeypatch, tmp_path):
    missing_dashboard = tmp_path / "dashboard" / "dist"
    monkeypatch.setattr(fastapi_app, "DASHBOARD_DIR", missing_dashboard)

    app = fastapi_app.create_app()

    assert not any(isinstance(route, Mount) and route.path == "/dashboard" for route in app.routes)
