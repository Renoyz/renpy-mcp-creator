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


def _rgba_png_bytes(size=(640, 360)) -> bytes:
    image = Image.new("RGBA", size=size, color=(32, 128, 255, 255))
    from io import BytesIO

    with BytesIO() as stream:
        image.save(stream, format="PNG")
        return stream.getvalue()


class FakeImageService:
    def __init__(self, settings):
        self.settings = settings

    def is_available(self) -> bool:
        return True

    async def generate_image(
        self,
        *,
        project_dir: Path,
        prompt: str,
        image_type: str,
        base_name: str | None = None,
        generate_emotions: bool = False,
    ):
        from renpy_mcp.models import ImageGenerationResult

        output_dir = project_dir / "game" / "images" / image_type
        output_dir.mkdir(parents=True, exist_ok=True)
        primary = output_dir / f"{base_name or 'generated'}.png"
        size = (1280, 720) if image_type == "background" else (640, 720)
        primary.write_bytes(_rgba_png_bytes(size=size))
        return ImageGenerationResult(
            success=True,
            prompt=prompt,
            image_type=image_type,
            files=[primary],
            primary_file=primary,
        )


def _install_fake_image_service(monkeypatch: pytest.MonkeyPatch) -> None:
    import renpy_mcp.ai.image_service as image_service_module

    monkeypatch.setattr(image_service_module, "ImageService", FakeImageService)


def _seed_scene_packages(project_name: str) -> None:
    from renpy_mcp.blueprint.models import ScenePackageChapter, ScenePackageScene, ScenePackagesSnapshot
    from renpy_mcp.config import get_settings
    from renpy_mcp.services.project_manager import ProjectManager

    pm = ProjectManager(get_settings())
    pm.write_scene_packages(
        project_name,
        ScenePackagesSnapshot(
            chapters=[
                ScenePackageChapter(
                    chapter_id="ch1",
                    chapter_name="Chapter 1",
                    chapter_order=1,
                    scenes=[
                        ScenePackageScene(
                            scene_id="scene_01",
                            title="Rooftop Meeting",
                            summary="Characters talk under the moonlight.",
                            location="rooftop",
                            location_visual_brief="wide street and cafe",
                            mood="calm",
                            characters_present=["Alice", "Bob"],
                            dialogue_beats=[],
                            scene_order=1,
                        )
                    ],
                )
            ]
        ),
    )


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
    _allow_stepwise_generation(tmp_path, project_name)

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

    preview_before_backgrounds = client.post(f"/api/projects/{project_name}/generation/script/preview")
    assert preview_before_backgrounds.status_code == 409, preview_before_backgrounds.text
    assert "character_assets_confirmed" in preview_before_backgrounds.json()["detail"]

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
    assert bg_slot["description"] == "rooftop"
    assert bg_slot["description_source"] == "target"

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
    # Scene-outline draft routes are pre-generation workspace controls and stay ungated.

    start = client.post(f"/api/projects/{project_name}/generation/scene-outline/start")
    assert start.status_code == 200, start.text
    assert start.json()["state"] == "scene_outline_draft"

    confirm = client.post(f"/api/projects/{project_name}/generation/scene-outline/confirm")
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["state"] == "scene_outline_confirmed"


def test_stepwise_generation_mutations_require_frozen_blueprint(client: TestClient):
    project_name = "stepwise_requires_freeze"
    _make_project(client, project_name)

    start_characters = client.post(f"/api/projects/{project_name}/generation/characters/start")
    char_generate = client.post(
        f"/api/projects/{project_name}/generation/characters/Alice/normal/generate",
        json={"prompt": "ink vampire hunter sprite"},
    )
    background_generate = client.post(
        f"/api/projects/{project_name}/generation/backgrounds/rooftop/main/generate",
        json={"prompt": "moonlit rooftop"},
    )

    assert start_characters.status_code == 403, start_characters.text
    assert "blueprint" in start_characters.json()["detail"].lower()
    assert char_generate.status_code == 403, char_generate.text
    assert "blueprint" in char_generate.json()["detail"].lower()
    assert background_generate.status_code == 403, background_generate.text
    assert "blueprint" in background_generate.json()["detail"].lower()


def test_stepwise_generation_rejects_existing_unfrozen_blueprint(client: TestClient):
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.config import get_settings
    from renpy_mcp.services.project_manager import ProjectManager

    project_name = "stepwise_rejects_unfrozen_blueprint"
    _make_project(client, project_name)
    pm = ProjectManager(get_settings())
    pm.write_blueprint(
        project_name,
        ProjectBlueprint(title="Unfrozen VN", genre="test", worldview="test world"),
    )

    r = client.post(f"/api/projects/{project_name}/generation/characters/start")

    assert r.status_code == 403, r.text
    assert "frozen" in r.json()["detail"].lower()


def test_character_generate_endpoint_returns_generated_slot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    _install_fake_image_service(monkeypatch)
    project_name = "stepwise_character_generate"
    _make_project(client, project_name)
    _allow_stepwise_generation(tmp_path, project_name)
    start = client.post(f"/api/projects/{project_name}/generation/characters/start")
    assert start.status_code == 200, start.text

    r = client.post(
        f"/api/projects/{project_name}/generation/characters/Alice/normal/generate",
        json={"prompt": "ink vampire hunter sprite"},
    )
    assert r.status_code == 200, r.text
    slot = r.json()
    assert slot["asset_id"] == "char_Alice_normal"
    assert slot["source"] == "generated"
    assert slot["status"] == "generated"
    assert slot["generation_prompt"] == "ink vampire hunter sprite"
    assert slot["preview_url"].startswith(f"/api/projects/{project_name}/asset-file/__staging__/")
    assert not Path(slot["staging_path"]).is_absolute()


def test_background_generate_endpoint_returns_generated_slot(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    _install_fake_image_service(monkeypatch)
    project_name = "stepwise_background_generate"
    _make_project(client, project_name)
    _allow_stepwise_generation(tmp_path, project_name)
    start_characters = client.post(f"/api/projects/{project_name}/generation/characters/start")
    assert start_characters.status_code == 200, start_characters.text
    start_backgrounds = client.post(f"/api/projects/{project_name}/generation/backgrounds/start")
    assert start_backgrounds.status_code == 200, start_backgrounds.text

    r = client.post(
        f"/api/projects/{project_name}/generation/backgrounds/rooftop/night/generate",
        json={"prompt": "moonlit rooftop background"},
    )
    assert r.status_code == 200, r.text
    slot = r.json()
    assert slot["asset_id"] == "bg_rooftop_night"
    assert slot["source"] == "generated"
    assert slot["status"] == "generated"
    assert slot["generation_prompt"] == "moonlit rooftop background"
    assert slot["description"] == "rooftop"
    assert slot["description_source"] == "target"
    assert "rooftop" in slot["generation_prompt"]
    assert slot["preview_url"].startswith(f"/api/projects/{project_name}/asset-file/__staging__/")
    assert not Path(slot["staging_path"]).is_absolute()


def test_background_generate_uses_scene_description_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    _install_fake_image_service(monkeypatch)
    project_name = "stepwise_background_scene_description"
    _make_project(client, project_name)
    _allow_stepwise_generation(tmp_path, project_name)
    _seed_scene_packages(project_name)

    start_characters = client.post(f"/api/projects/{project_name}/generation/characters/start")
    assert start_characters.status_code == 200, start_characters.text
    start_backgrounds = client.post(f"/api/projects/{project_name}/generation/backgrounds/start")
    assert start_backgrounds.status_code == 200, start_backgrounds.text

    r = client.post(
        f"/api/projects/{project_name}/generation/backgrounds/scene_01/main/generate",
        json={"prompt": ""},
    )
    assert r.status_code == 200, r.text
    slot = r.json()
    assert slot["asset_id"] == "bg_scene_01_main"
    assert slot["description"] == "wide street and cafe"
    assert slot["description_source"] == "scene_package"
    assert "wide street and cafe" in slot["generation_prompt"]
    assert slot["generation_prompt"] != ""


def test_background_generation_keeps_description_after_regenerate(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    _install_fake_image_service(monkeypatch)
    project_name = "stepwise_background_preserve_after_regen"
    _make_project(client, project_name)
    _allow_stepwise_generation(tmp_path, project_name)

    start_characters = client.post(f"/api/projects/{project_name}/generation/characters/start")
    assert start_characters.status_code == 200, start_characters.text
    start_backgrounds = client.post(f"/api/projects/{project_name}/generation/backgrounds/start")
    assert start_backgrounds.status_code == 200, start_backgrounds.text

    upload = client.post(
        f"/api/projects/{project_name}/generation/backgrounds/scene_01/main/upload",
        files={"file": ("scene_01.png", _rgba_png_bytes(size=(1280, 720)), "image/png")},
    )
    assert upload.status_code == 200, upload.text
    state = client.get(f"/api/projects/{project_name}/generation-state").json()
    assert state["background_assets"]["bg_scene_01_main"]["description"] == "scene_01"
    assert state["background_assets"]["bg_scene_01_main"]["description_source"] == "target"

    generated = client.post(
        f"/api/projects/{project_name}/generation/backgrounds/scene_01/main/generate",
        json={"prompt": "moonlit city background"},
    )
    assert generated.status_code == 200, generated.text
    generated_slot = generated.json()
    assert generated_slot["description"] == "scene_01"
    assert generated_slot["description_source"] == "target"
    assert generated_slot["generation_prompt"] == "moonlit city background"


def test_background_upload_accepts_user_description(
    client: TestClient,
    tmp_path: Path,
):
    project_name = "stepwise_background_upload_description"
    _make_project(client, project_name)
    _allow_stepwise_generation(tmp_path, project_name)

    start_characters = client.post(f"/api/projects/{project_name}/generation/characters/start")
    assert start_characters.status_code == 200, start_characters.text
    start_backgrounds = client.post(f"/api/projects/{project_name}/generation/backgrounds/start")
    assert start_backgrounds.status_code == 200, start_backgrounds.text

    upload = client.post(
        f"/api/projects/{project_name}/generation/backgrounds/scene_01/main/upload",
        files={"file": ("scene_01.png", _rgba_png_bytes(size=(1280, 720)), "image/png")},
        data={"description": "rainy moonlit alley"},
    )

    assert upload.status_code == 200, upload.text
    slot = upload.json()
    assert slot["description"] == "rainy moonlit alley"
    assert slot["description_source"] == "user"


def test_stepwise_pipeline_requires_manual_preview_and_commit(client: TestClient, tmp_path: Path):
    project_name = "stepwise_manual_progression"
    _make_project(client, project_name)
    _allow_stepwise_generation(tmp_path, project_name)

    start_characters = client.post(f"/api/projects/{project_name}/generation/characters/start")
    assert start_characters.status_code == 200, start_characters.text
    char_upload = client.post(
        f"/api/projects/{project_name}/generation/characters/Alice/normal/upload",
        files={"file": ("alice.png", _rgba_png_bytes(), "image/png")},
    )
    assert char_upload.status_code == 200, char_upload.text
    char_slot = char_upload.json()
    accept_char = client.post(f"/api/projects/{project_name}/generation/characters/{char_slot['asset_id']}/accept")
    assert accept_char.status_code == 200, accept_char.text
    confirm_char = client.post(f"/api/projects/{project_name}/generation/characters/confirm")
    assert confirm_char.status_code == 200, confirm_char.text

    start_backgrounds = client.post(f"/api/projects/{project_name}/generation/backgrounds/start")
    assert start_backgrounds.status_code == 200, start_backgrounds.text
    bg_upload = client.post(
        f"/api/projects/{project_name}/generation/backgrounds/rooftop/main/upload",
        files={"file": ("rooftop.png", _rgba_png_bytes(size=(1280, 720)), "image/png")},
    )
    assert bg_upload.status_code == 200, bg_upload.text
    bg_slot = bg_upload.json()
    accept_bg = client.post(f"/api/projects/{project_name}/generation/backgrounds/{bg_slot['asset_id']}/accept")
    assert accept_bg.status_code == 200, accept_bg.text
    confirm_bg = client.post(f"/api/projects/{project_name}/generation/backgrounds/confirm")
    assert confirm_bg.status_code == 200, confirm_bg.text
    assert confirm_bg.json()["state"] == "background_assets_confirmed"

    commit_without_preview = client.post(f"/api/projects/{project_name}/generation/script/commit")
    assert commit_without_preview.status_code == 409, commit_without_preview.text
    assert "preview" in commit_without_preview.json()["detail"].lower()

    state = client.get(f"/api/projects/{project_name}/generation-state").json()
    assert state["state"] == "background_assets_confirmed"
