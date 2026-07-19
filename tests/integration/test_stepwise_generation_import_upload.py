"""Integration tests for tier-4 character and background uploads."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from io import BytesIO
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


def _allow_stepwise_generation(tmp_path: Path, project_name: str) -> None:
    from renpy_mcp.blueprint.models import (
        BlueprintFreezeStatus,
        ProjectBlueprint,
        ProjectMeta,
        ProjectStatus,
        RefinementState,
    )
    from renpy_mcp.config import get_settings
    from renpy_mcp.services.project_manager import ProjectManager

    pm = ProjectManager(get_settings())
    pm.write_blueprint(
        project_name,
        ProjectBlueprint(title="Test VN", genre="test", worldview="test world"),
    )
    pm.write_project_meta(
        project_name,
        ProjectMeta(
            name=project_name,
            path=tmp_path / project_name,
            status=ProjectStatus.DRAFT,
            refinement_state=RefinementState.BLUEPRINT_READY,
            blueprint_freeze_status=BlueprintFreezeStatus.FROZEN,
        ),
    )


def _rgba_png_bytes(size=(640, 360), alpha=True) -> bytes:
    mode = "RGBA" if alpha else "RGB"
    image = Image.new(mode, size=size, color=(32, 128, 255, 255) if alpha else (32, 128, 255))
    with BytesIO() as stream:
        image.save(stream, format="PNG")
        return stream.getvalue()


def _project_upload(
    client: TestClient,
    project_name: str,
    path: str,
    filename: str,
    payload: bytes,
) -> object:
    r = client.post(
        f"/api/projects/{project_name}/{path}",
        files={"file": (filename, payload, "image/png")},
    )
    return r


def test_character_upload_valid_png_returns_preview_url_and_relative_paths(client: TestClient, tmp_path: Path):
    project_name = "upload_valid"
    _make_project(client, project_name)
    _allow_stepwise_generation(tmp_path, project_name)
    client.post(f"/api/projects/{project_name}/generation/characters/start")

    r = _project_upload(
        client,
        project_name,
        "generation/characters/Alice/normal/upload",
        "alice.png",
        _rgba_png_bytes(),
    )
    assert r.status_code == 200, r.text

    slot = r.json()
    assert slot["kind"] == "character_sprite"
    assert slot["status"] == "uploaded"
    assert slot["renderable"] is True
    assert slot["preview_url"].startswith(f"/api/projects/{project_name}/asset-file/")
    assert not Path(slot["path"]).is_absolute()
    assert not Path(slot["staging_path"]).is_absolute()


def test_non_image_upload_returns_400(client: TestClient, tmp_path: Path):
    project_name = "upload_invalid"
    _make_project(client, project_name)
    _allow_stepwise_generation(tmp_path, project_name)
    client.post(f"/api/projects/{project_name}/generation/characters/start")

    r = _project_upload(
        client,
        project_name,
        "generation/characters/Alice/normal/upload",
        "not-image.txt",
        b"not-an-image",
    )
    assert r.status_code == 400, r.text


def test_accept_non_renderable_character_without_override_returns_409_and_with_override_succeeds(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    project_name = "upload_override"
    _make_project(client, project_name)
    _allow_stepwise_generation(tmp_path, project_name)
    client.post(f"/api/projects/{project_name}/generation/characters/start")

    # Stub background removal to fail so the RGB upload stays non-renderable;
    # otherwise the outcome depends on whether rembg works in the local environment.
    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.remove_background",
        lambda self, path: None,
    )

    r = _project_upload(
        client,
        project_name,
        "generation/characters/Alice/normal/upload",
        "alice.png",
        _rgba_png_bytes(alpha=False),
    )
    assert r.status_code == 200, r.text
    slot = r.json()
    assert slot["renderable"] is False

    denied = client.post(
        f"/api/projects/{project_name}/generation/characters/{slot['asset_id']}/accept",
    )
    assert denied.status_code == 409, denied.text

    accepted = client.post(
        f"/api/projects/{project_name}/generation/characters/{slot['asset_id']}/accept",
        json={"allow_non_renderable": True},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
