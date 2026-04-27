from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from renpy_mcp.web.fastapi_app import create_app, set_config


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from renpy_mcp.config import RenPyConfig, get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)

    import renpy_mcp.web.fastapi_app as fa

    dashboard_dir = tmp_path / "dashboard_dist"
    dashboard_dir.mkdir()
    (dashboard_dir / "index.html").write_text("<html><body>dashboard</body></html>", encoding="utf-8")
    set_config(RenPyConfig(sdk_path=Path("."), project_path=tmp_path))
    monkeypatch.setattr(fa, "DASHBOARD_DIR", dashboard_dir)
    monkeypatch.setattr(fa, "_last_build_results", {})

    return TestClient(create_app())


def _create_project(client: TestClient, name: str) -> None:
    response = client.post("/api/projects", json={"name": name})
    assert response.status_code == 200, response.text


def test_get_game_shell_derives_default_config(client: TestClient):
    project_name = "shell_demo"
    _create_project(client, project_name)
    client.put(
        f"/api/projects/{project_name}/blueprint",
        json={"title": "派生标题", "genre": "test", "worldview": "world"},
    )

    response = client.get(f"/api/projects/{project_name}/game-shell")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["title"] == "派生标题"
    assert payload["show_gallery"] is True
    assert "Created with RenPy MCP Creator" in payload["credits"]


def test_put_game_shell_rejects_absolute_path(client: TestClient, tmp_path: Path):
    project_name = "shell_bad_path"
    _create_project(client, project_name)

    response = client.put(
        f"/api/projects/{project_name}/game-shell",
        json={
            "title": "Bad",
            "main_menu_background": str(tmp_path / "outside.png"),
            "gallery_items": [],
            "ending_items": [],
            "credits": [],
        },
    )

    assert response.status_code == 400


def test_render_preview_writes_staged_shell_files(client: TestClient):
    project_name = "shell_preview"
    _create_project(client, project_name)
    save = client.put(
        f"/api/projects/{project_name}/game-shell",
        json={
            "title": "Shell Preview",
            "subtitle": "A generated shell",
            "theme": "default",
            "main_menu_background": "",
            "show_gallery": True,
            "show_endings": True,
            "show_replay": False,
            "show_credits": True,
            "gallery_items": [
                {
                    "id": "bg_1",
                    "title": "Rain Street",
                    "image_path": "game/images/backgrounds/rain.png",
                    "source": "background",
                    "unlock_mode": "always",
                    "persistent_key": "",
                }
            ],
            "ending_items": [],
            "credits": ["Writer: AI"],
        },
    )
    assert save.status_code == 200, save.text

    response = client.post(f"/api/projects/{project_name}/game-shell/render-preview")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["gallery_count"] == 1
    assert "game/__staging__/shell/zz_generated_shell.rpy" in payload["script_files"]
    assert "screen mcp_gallery" in payload["preview"]


def test_render_preview_can_use_unsaved_request_body(client: TestClient):
    project_name = "shell_unsaved_preview"
    _create_project(client, project_name)
    response = client.post(
        f"/api/projects/{project_name}/game-shell/render-preview",
        json={
            "title": "Unsaved Shell",
            "subtitle": "",
            "theme": "default",
            "main_menu_background": "",
            "show_gallery": True,
            "show_endings": True,
            "show_replay": True,
            "show_credits": True,
            "gallery_items": [
                {
                    "id": "bg_unsaved",
                    "title": "Unsaved Gallery",
                    "image_path": "game/images/bg.png",
                    "source": "background",
                    "unlock_mode": "always",
                    "persistent_key": "",
                }
            ],
            "ending_items": [],
            "credits": ["Unsaved Credit"],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "Unsaved Shell" in payload["preview"]
    assert "Unsaved Gallery" in payload["preview"]


def test_derive_endpoint_overwrites_saved_shell(client: TestClient):
    project_name = "shell_derive"
    _create_project(client, project_name)
    client.put(
        f"/api/projects/{project_name}/blueprint",
        json={"title": "Fresh Blueprint", "genre": "test", "worldview": "world"},
    )
    client.put(
        f"/api/projects/{project_name}/game-shell",
        json={
            "title": "Manual Old",
            "gallery_items": [],
            "ending_items": [],
            "credits": [],
        },
    )

    response = client.post(f"/api/projects/{project_name}/game-shell/derive")

    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Fresh Blueprint"
