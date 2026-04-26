"""Integration tests for Stepwise generation state and full commit flow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from renpy_mcp.web.fastapi_app import create_app, set_config


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from renpy_mcp.config import RenPyConfig, get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)

    import renpy_mcp.web.fastapi_app as fa

    dashboard_dir = tmp_path / "dashboard_dist"
    dashboard_dir.mkdir()
    (dashboard_dir / "index.html").write_text("<html><body>dashboard</body></html>", encoding="utf-8")
    (dashboard_dir / "assets").mkdir()
    (dashboard_dir / "assets" / "test.js").write_text("console.log('test');", encoding="utf-8")
    set_config(RenPyConfig(sdk_path=Path("."), project_path=tmp_path))
    monkeypatch.setattr(fa, "DASHBOARD_DIR", dashboard_dir)
    monkeypatch.setattr(fa, "_last_build_results", {})

    app = create_app()
    return TestClient(app)


def _make_project(client: TestClient, project_name: str) -> None:
    r = client.post("/api/projects", json={"name": project_name})
    assert r.status_code == 200, r.text


def _rgba_png_bytes(size=(640, 360)) -> bytes:
    image = Image.new("RGBA", size=size, color=(32, 128, 255, 255))
    from io import BytesIO

    with BytesIO() as stream:
        image.save(stream, format="PNG")
        return stream.getvalue()


def test_generation_state_returns_idle_default_for_existing_project(client: TestClient, tmp_path: Path):
    project_name = "stepwise_state_idle"
    _make_project(client, project_name)

    r = client.get(f"/api/projects/{project_name}/generation-state")
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["state"] == "idle"
    assert first["round_id"] is None
    assert first["character_assets"] == {}
    assert first["background_assets"] == {}

    # Should be recoverable after refresh.
    r = client.get(f"/api/projects/{project_name}/generation-state")
    assert r.status_code == 200, r.text
    second = r.json()
    assert second == first


def test_full_stepwise_happy_path_upload_char_and_background(client: TestClient, tmp_path: Path):
    project_name = "stepwise_full_happy"
    _make_project(client, project_name)

    r = client.post(f"/api/projects/{project_name}/generation/characters/start")
    assert r.status_code == 200, r.text

    char_upload = client.post(
        f"/api/projects/{project_name}/generation/characters/Alice/normal/upload",
        files={"file": ("alice.png", _rgba_png_bytes(), "image/png")},
    )
    assert char_upload.status_code == 200, char_upload.text
    char_slot = char_upload.json()
    assert char_slot["asset_id"] == "char_Alice_normal"
    assert char_slot["status"] == "uploaded"
    assert char_slot["kind"] == "character_sprite"
    assert char_slot["renderable"] is True

    r = client.post(f"/api/projects/{project_name}/generation/characters/{char_slot['asset_id']}/accept")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"

    r = client.post(f"/api/projects/{project_name}/generation/characters/confirm")
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "character_assets_confirmed"

    r = client.post(f"/api/projects/{project_name}/generation/backgrounds/start")
    assert r.status_code == 200, r.text

    bg_upload = client.post(
        f"/api/projects/{project_name}/generation/backgrounds/rooftop/main/upload",
        files={"file": ("rooftop.png", _rgba_png_bytes(size=(1280, 720)), "image/png")},
    )
    assert bg_upload.status_code == 200, bg_upload.text
    bg_slot = bg_upload.json()
    assert bg_slot["asset_id"] == "bg_rooftop_main"
    assert bg_slot["status"] == "uploaded"
    assert bg_slot["kind"] == "background"

    r = client.post(f"/api/projects/{project_name}/generation/backgrounds/{bg_slot['asset_id']}/accept")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"

    r = client.post(f"/api/projects/{project_name}/generation/backgrounds/confirm")
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "background_assets_confirmed"

    r = client.post(f"/api/projects/{project_name}/generation/script/preview")
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["label"] == "script_preview"
    assert "script" in preview

    r = client.post(f"/api/projects/{project_name}/generation/script/commit")
    assert r.status_code == 200, r.text
    commit_state = r.json()
    assert commit_state["state"] == "committed"

    final_state = client.get(f"/api/projects/{project_name}/generation-state").json()
    assert final_state["state"] == "committed"
    assert final_state["round_id"] == "r0001"

    assert (tmp_path / project_name / char_slot["path"]).exists()
    assert (tmp_path / project_name / bg_slot["path"]).exists()

    index_path = tmp_path / project_name / "meta" / "index.json"
    assert index_path.exists()
    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    assert "scenes" in index_data
    assert any(
        scene.get("source") == "prototype"
        for scene in index_data.get("scenes", {}).values()
        if isinstance(scene, dict)
    )

    manifest_path = tmp_path / project_name / "meta" / "prototype_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["mode"] == "single_chapter"


def test_scene_outline_start_and_confirm_routes_set_state(client: TestClient):
    project_name = "stepwise_scene_outline_state"
    _make_project(client, project_name)

    start = client.post(f"/api/projects/{project_name}/generation/scene-outline/start")
    assert start.status_code == 200, start.text
    assert start.json()["state"] == "scene_outline_draft"

    confirm = client.post(f"/api/projects/{project_name}/generation/scene-outline/confirm")
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["state"] == "scene_outline_confirmed"


def test_character_generate_endpoint_is_not_implemented(client: TestClient):
    project_name = "stepwise_character_generate_not_impl"
    _make_project(client, project_name)

    r = client.post(
        f"/api/projects/{project_name}/generation/characters/Alice/normal/generate"
    )
    assert r.status_code == 501, r.text
    assert "not implemented" in r.json()["detail"].lower()


def test_background_generate_endpoint_is_not_implemented(client: TestClient):
    project_name = "stepwise_background_generate_not_impl"
    _make_project(client, project_name)

    r = client.post(f"/api/projects/{project_name}/generation/backgrounds/rooftop/generate")
    assert r.status_code == 501, r.text
    assert "not implemented" in r.json()["detail"].lower()
