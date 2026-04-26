"""Unit tests for ImportedAssetService."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image


def _rgba_png_bytes(color=(255, 0, 0, 255), size=(640, 360)) -> bytes:
    image = Image.new("RGBA", size=size, color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _rgb_jpg_bytes(size=(640, 360)) -> bytes:
    image = Image.new("RGB", size=size, color=(160, 40, 40))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture()
def pm(tmp_path, monkeypatch):
    from renpy_mcp.config import get_settings
    from renpy_mcp.services.project_manager import ProjectManager

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)
    return ProjectManager(settings)


@pytest.fixture()
def project(pm):
    project_name = "demo"
    project_dir = pm.ensure_project_dir(project_name)
    (project_dir / "game").mkdir(parents=True, exist_ok=True)
    return project_name, project_dir


@pytest.fixture()
def service(pm):
    from renpy_mcp.services.imported_asset_service import ImportedAssetService

    return ImportedAssetService(pm)


def test_upload_background_writes_staging_and_returns_relative_payload(service, project):
    project_name, project_dir = project
    slot = service.import_image(
        project_name=project_name,
        round_id="r1",
        kind="background",
        target="rooftop",
        variant="main",
        filename="rooftop.png",
        file_bytes=_rgba_png_bytes(),
    )

    assert slot["path"] == "game/images/background/bg_rooftop_main.png"
    assert slot["staging_path"] == "game/__staging__/r1/images/background/bg_rooftop_main.png"
    assert slot["source"] == "uploaded"
    assert slot["status"] == "uploaded"
    assert slot["placeholder"] is False
    assert slot["preview_url"] == (
        "/api/projects/demo/asset-file/__staging__/r1/images/background/"
        "bg_rooftop_main.png"
    )

    staging_file = project_dir / slot["staging_path"]
    assert staging_file.exists()
    assert not Path(slot["path"]).is_absolute()
    assert not Path(slot["staging_path"]).is_absolute()
    assert not Path(slot["preview_url"]).is_absolute()


def test_upload_transparent_character_png_is_renderable(service, project):
    project_name, _ = project
    slot = service.import_image(
        project_name=project_name,
        round_id="r1",
        kind="character_sprite",
        target="alice",
        variant="normal",
        filename="alice.png",
        file_bytes=_rgba_png_bytes(color=(0, 0, 0, 128), size=(400, 400)),
    )

    assert slot["kind"] == "character_sprite"
    assert slot["renderable"] is True
    assert slot["validation"]["reason"] == "ok"
    assert slot["validation"]["ok"] is True
    assert "images/sprites" in slot["path"]


def test_upload_non_transparent_character_jpg_is_not_renderable(service, project):
    project_name, _ = project
    slot = service.import_image(
        project_name=project_name,
        round_id="r1",
        kind="character_sprite",
        target="alice",
        variant="main",
        filename="alice.jpg",
        file_bytes=_rgb_jpg_bytes(size=(400, 400)),
    )

    assert slot["renderable"] is False
    assert slot["validation"]["ok"] is False
    assert slot["validation"]["reason"] == "no_alpha"


def test_upload_non_image_bytes_rejected(service, project):
    project_name, _ = project
    with pytest.raises(ValueError, match="valid image"):
        service.import_image(
            project_name=project_name,
            round_id="r1",
            kind="background",
            target="bad",
            variant="main",
            filename="bad.png",
            file_bytes=b"not-an-image",
        )


def test_upload_malicious_filename_cannot_escape_staging(service, project):
    project_name, project_dir = project
    slot = service.import_image(
        project_name=project_name,
        round_id="r1",
        kind="background",
        target="rooftop",
        variant="main",
        filename="..\\..\\secret.png",
        file_bytes=_rgba_png_bytes(),
    )

    assert slot["staging_path"] == "game/__staging__/r1/images/background/bg_rooftop_main.png"
    assert ".." not in slot["staging_path"]
    assert "\\\\" not in slot["staging_path"]

    final_stored = project_dir / slot["staging_path"]
    assert final_stored.exists()
    assert final_stored.is_file()
