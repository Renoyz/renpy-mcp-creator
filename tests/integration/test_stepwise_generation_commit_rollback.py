"""Integration tests for Tier-4 stepwise commit transactional boundaries."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath

import json
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


def _rgba_png_bytes(color=(32, 128, 255, 255), size=(640, 360)) -> bytes:
    image = Image.new("RGBA", size=size, color=color)
    with BytesIO() as stream:
        image.save(stream, format="PNG")
        return stream.getvalue()


def _project_upload(
    client: TestClient,
    project_name: str,
    path: str,
    filename: str,
    payload: bytes,
) -> dict:
    response = client.post(
        f"/api/projects/{project_name}/{path}",
        files={"file": (filename, payload, "image/png")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _seed_single_scene_packages(pm, project_name: str) -> None:
    from renpy_mcp.blueprint.models import (
        BlueprintFreezeStatus,
        ProjectBlueprint,
        ProjectMeta,
        ProjectStatus,
        RefinementState,
        ScenePackageChapter,
        ScenePackageScene,
        ScenePackagesSnapshot,
    )

    pm.write_blueprint(
        project_name,
        ProjectBlueprint(title="Stepwise Commit VN", genre="test", worldview="test world"),
    )
    pm.write_project_meta(
        project_name,
        ProjectMeta(
            name=project_name,
            path=pm._project_dir(project_name),
            status=ProjectStatus.DRAFT,
            refinement_state=RefinementState.BLUEPRINT_READY,
            blueprint_freeze_status=BlueprintFreezeStatus.FROZEN,
        ),
    )

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
                            title="Rooftop Scene",
                            summary="Alice meets Bob.",
                            location="rooftop",
                            location_visual_brief="city roof",
                            mood="calm",
                            characters_present=["Alice"],
                            dialogue_beats=[],
                            scene_order=1,
                        )
                    ],
                )
            ]
        ),
    )


def _assert_no_absolute_paths(value: object) -> None:
    if isinstance(value, str):
        if value.startswith("/api/"):
            return
        if Path(value).is_absolute() or PureWindowsPath(value).is_absolute():
            assert False, f"Absolute path leaked to API payload: {value}"
        return
    if isinstance(value, list):
        for item in value:
            _assert_no_absolute_paths(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_absolute_paths(item)


def _drive_to_committable(client: TestClient, project_name: str) -> None:
    """Drive a single-scene project to just before script commit."""
    from renpy_mcp.config import get_settings
    from renpy_mcp.services.project_manager import ProjectManager

    pm = ProjectManager(get_settings())
    _seed_single_scene_packages(pm, project_name)

    assert client.post(f"/api/projects/{project_name}/generation/characters/start").status_code == 200
    alice_slot = _project_upload(
        client, project_name,
        "generation/characters/Alice/normal/upload", "alice.png", _rgba_png_bytes(),
    )
    accepted = client.post(
        f"/api/projects/{project_name}/generation/characters/{alice_slot['asset_id']}/accept"
    )
    assert accepted.status_code == 200, accepted.text

    assert client.post(f"/api/projects/{project_name}/generation/backgrounds/start").status_code == 200
    bg_slot = _project_upload(
        client, project_name,
        "generation/backgrounds/scene_01/main/upload", "scene_01.png",
        _rgba_png_bytes(size=(1280, 720)),
    )
    bg_accepted = client.post(
        f"/api/projects/{project_name}/generation/backgrounds/{bg_slot['asset_id']}/accept"
    )
    assert bg_accepted.status_code == 200, bg_accepted.text

    assert client.post(f"/api/projects/{project_name}/generation/characters/confirm").status_code == 200
    assert client.post(f"/api/projects/{project_name}/generation/backgrounds/confirm").status_code == 200
    preview = client.post(f"/api/projects/{project_name}/generation/script/preview")
    assert preview.status_code == 200, preview.text


def test_commit_injects_cjk_font_for_web_builds(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stepwise commit must inject a CJK font + override config.

    Real-run evidence (2026-07-19): the web preview rendered all CJK dialogue
    as tofu boxes because generated projects carried no CJK font.
    """
    fake_font = tmp_path / "fake_cjk.ttf"
    fake_font.write_bytes(b"FAKE-TTF" * 1024)
    monkeypatch.setattr(
        "renpy_mcp.services.prototype_generation_service.resolve_cjk_font_path",
        lambda config_path=None: fake_font,
    )

    project_name = "stepwise_commit_cjk_font"
    _make_project(client, project_name)
    _drive_to_committable(client, project_name)

    commit = client.post(f"/api/projects/{project_name}/generation/script/commit")
    assert commit.status_code == 200, commit.text

    project_dir = tmp_path / project_name
    assert (project_dir / "game" / "fonts" / "simhei.ttf").read_bytes() == fake_font.read_bytes()
    font_cfg = (project_dir / "game" / "prototype_fonts.rpy").read_text(encoding="utf-8")
    assert "fonts/simhei.ttf" in font_cfg

    index_payload = json.loads((project_dir / "meta" / "index.json").read_text(encoding="utf-8"))
    assert index_payload["cjk_font_config"]["configured"] is True


def test_commit_without_available_cjk_font_still_succeeds(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No CJK font on the host must not break commit; config degrades gracefully."""
    monkeypatch.setattr(
        "renpy_mcp.services.prototype_generation_service.resolve_cjk_font_path",
        lambda config_path=None: None,
    )

    project_name = "stepwise_commit_cjk_font_missing"
    _make_project(client, project_name)
    _drive_to_committable(client, project_name)

    commit = client.post(f"/api/projects/{project_name}/generation/script/commit")
    assert commit.status_code == 200, commit.text

    project_dir = tmp_path / project_name
    assert not (project_dir / "game" / "fonts" / "simhei.ttf").exists()
    font_cfg = (project_dir / "game" / "prototype_fonts.rpy").read_text(encoding="utf-8")
    assert "fallback disabled" in font_cfg

    index_payload = json.loads((project_dir / "meta" / "index.json").read_text(encoding="utf-8"))
    assert index_payload.get("cjk_font_config", {}).get("configured") is False


def test_commit_promotes_only_accepted_assets_and_skips_unaccepted(client: TestClient, tmp_path: Path) -> None:
    project_name = "stepwise_commit_accepted_only"
    _make_project(client, project_name)

    from renpy_mcp.config import get_settings
    from renpy_mcp.services.project_manager import ProjectManager

    pm = ProjectManager(get_settings())
    _seed_single_scene_packages(pm, project_name)

    r = client.post(f"/api/projects/{project_name}/generation/characters/start")
    assert r.status_code == 200, r.text

    alice_bytes = _rgba_png_bytes()
    dave_bytes = _rgba_png_bytes(color=(64, 64, 64, 255))
    alice_slot = _project_upload(
        client,
        project_name,
        "generation/characters/Alice/normal/upload",
        "alice.png",
        alice_bytes,
    )
    dave_slot = _project_upload(
        client,
        project_name,
        "generation/characters/Dave/happy/upload",
        "dave.png",
        dave_bytes,
    )

    accepted = client.post(
        f"/api/projects/{project_name}/generation/characters/{alice_slot['asset_id']}/accept"
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"

    start_bg = client.post(f"/api/projects/{project_name}/generation/backgrounds/start")
    assert start_bg.status_code == 200, start_bg.text

    bg_bytes = _rgba_png_bytes(size=(1280, 720))
    bg_slot = _project_upload(
        client,
        project_name,
        "generation/backgrounds/scene_01/main/upload",
        "scene_01.png",
        bg_bytes,
    )
    bg_accepted = client.post(
        f"/api/projects/{project_name}/generation/backgrounds/{bg_slot['asset_id']}/accept"
    )
    assert bg_accepted.status_code == 200, bg_accepted.text
    assert bg_accepted.json()["status"] == "accepted"

    confirm_char = client.post(f"/api/projects/{project_name}/generation/characters/confirm")
    assert confirm_char.status_code == 200, confirm_char.text
    confirm_bg = client.post(f"/api/projects/{project_name}/generation/backgrounds/confirm")
    assert confirm_bg.status_code == 200, confirm_bg.text

    preview = client.post(f"/api/projects/{project_name}/generation/script/preview")
    assert preview.status_code == 200, preview.text
    commit = client.post(f"/api/projects/{project_name}/generation/script/commit")
    assert commit.status_code == 200, commit.text

    for payload in (alice_slot, dave_slot, bg_slot):
        assert not Path(payload["path"]).is_absolute()
        assert not Path(payload["staging_path"]).is_absolute()
        assert payload["preview_url"].startswith(f"/api/projects/{project_name}/asset-file/")

    state = commit.json()
    assert state["state"] == "committed"
    _assert_no_absolute_paths(state["script_preview"])

    project_dir = tmp_path / project_name
    assert (project_dir / alice_slot["path"]).exists()
    assert (project_dir / bg_slot["path"]).exists()
    assert not (project_dir / dave_slot["path"]).exists()

    assert (project_dir / alice_slot["path"]).read_bytes() == alice_bytes
    assert (project_dir / bg_slot["path"]).read_bytes() == bg_bytes

    index_payload = json.loads((project_dir / "meta" / "index.json").read_text(encoding="utf-8"))
    assert "character_assets" in index_payload
    assert "Alice" in index_payload["character_assets"]
    assert index_payload["character_assets"]["Alice"]["path"] == alice_slot["path"]
    assert "Dave" not in index_payload["character_assets"]
    assert index_payload["scenes"]["scene_01"]["background_asset_path"] == bg_slot["path"]
    _assert_no_absolute_paths(index_payload)


def test_commit_failure_does_not_pollute_final_runtime_paths(client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_name = "stepwise_commit_failure_rollbacks"
    _make_project(client, project_name)

    from renpy_mcp.config import get_settings
    from renpy_mcp.services.project_manager import ProjectManager
    import renpy_mcp.services.stepwise_generation_service as stepwise_service

    pm = ProjectManager(get_settings())
    _seed_single_scene_packages(pm, project_name)

    baseline_script = "label start:\n    \"Hello from the Ren'Py MCP server!\"\n"
    script_path = tmp_path / project_name / "game" / "script.rpy"
    script_path.write_text(baseline_script, encoding="utf-8")

    legacy_index = {
        "scenes": {
            "old_scene": {
                "source": "prototype",
                "scene_id": "old_scene",
                "title": "Old Scene",
                "chapter_id": "legacy",
                "file_path": "game/prototype_old.rpy",
                "label": "prototype_legacy_start",
            }
        }
    }
    (tmp_path / project_name / "meta" / "index.json").write_text(
        json.dumps(legacy_index),
        encoding="utf-8",
    )
    legacy_manifest = {
        "mode": "single_chapter",
        "entry_label": "legacy_entry",
        "entry_file": "game/prototype_old.rpy",
        "chapter_ids": ["legacy"],
        "script_files": ["game/prototype_old.rpy"],
        "updated_at": "legacy",
    }
    (tmp_path / project_name / "meta" / "prototype_manifest.json").write_text(
        json.dumps(legacy_manifest),
        encoding="utf-8",
    )
    old_script_text = script_path.read_text(encoding="utf-8")
    old_index_text = (tmp_path / project_name / "meta" / "index.json").read_text(
        encoding="utf-8"
    )
    old_manifest_text = (
        tmp_path / project_name / "meta" / "prototype_manifest.json"
    ).read_text(encoding="utf-8")

    r = client.post(f"/api/projects/{project_name}/generation/characters/start")
    assert r.status_code == 200, r.text

    alice_slot = _project_upload(
        client,
        project_name,
        "generation/characters/Alice/normal/upload",
        "alice.png",
        _rgba_png_bytes(),
    )
    client.post(f"/api/projects/{project_name}/generation/characters/{alice_slot['asset_id']}/accept")

    start_bg = client.post(f"/api/projects/{project_name}/generation/backgrounds/start")
    assert start_bg.status_code == 200, start_bg.text

    bg_slot = _project_upload(
        client,
        project_name,
        "generation/backgrounds/scene_01/main/upload",
        "scene_01.png",
        _rgba_png_bytes(size=(1280, 720)),
    )
    client.post(
        f"/api/projects/{project_name}/generation/backgrounds/{bg_slot['asset_id']}/accept",
    )

    assert client.post(
        f"/api/projects/{project_name}/generation/characters/confirm"
    ).status_code == 200
    assert client.post(
        f"/api/projects/{project_name}/generation/backgrounds/confirm"
    ).status_code == 200
    assert client.post(
        f"/api/projects/{project_name}/generation/script/preview"
    ).status_code == 200

    alice_final_path = tmp_path / project_name / alice_slot["path"]
    bg_final_path = tmp_path / project_name / bg_slot["path"]

    assert not alice_final_path.exists()
    assert not bg_final_path.exists()

    original_promote = stepwise_service.StepwiseGenerationService._promote_staged_asset_slots

    def _failing_promote(project, project_dir: Path, slots: list[dict]) -> None:
        original_promote(project, project_dir, slots)
        assert alice_final_path.exists()
        assert bg_final_path.exists()
        raise RuntimeError("simulated promotion failure")

    monkeypatch.setattr(
        stepwise_service.StepwiseGenerationService,
        "_promote_staged_asset_slots",
        _failing_promote,
    )

    commit = client.post(f"/api/projects/{project_name}/generation/script/commit")
    assert commit.status_code == 503, commit.text
    assert commit.json()["detail"] == "simulated promotion failure"

    assert script_path.read_text(encoding="utf-8") == old_script_text
    assert (tmp_path / project_name / "meta" / "index.json").read_text(
        encoding="utf-8"
    ) == old_index_text
    assert (tmp_path / project_name / "meta" / "prototype_manifest.json").read_text(
        encoding="utf-8"
    ) == old_manifest_text
    assert not alice_final_path.exists()
    assert not bg_final_path.exists()
    assert client.get(f"/api/projects/{project_name}/generation-state").json()["state"] == "failed"


def test_stepwise_api_does_not_return_absolute_payload_paths(client: TestClient, tmp_path: Path) -> None:
    project_name = "stepwise_paths_are_relative"
    _make_project(client, project_name)

    from renpy_mcp.config import get_settings
    from renpy_mcp.services.project_manager import ProjectManager

    pm = ProjectManager(get_settings())
    _seed_single_scene_packages(pm, project_name)

    client.post(f"/api/projects/{project_name}/generation/characters/start")
    alice_slot = _project_upload(
        client,
        project_name,
        "generation/characters/Alice/normal/upload",
        "alice.png",
        _rgba_png_bytes(),
    )
    client.post(f"/api/projects/{project_name}/generation/characters/{alice_slot['asset_id']}/accept")
    client.post(f"/api/projects/{project_name}/generation/backgrounds/start")
    bg_slot = _project_upload(
        client,
        project_name,
        "generation/backgrounds/scene_01/main/upload",
        "scene_01.png",
        _rgba_png_bytes(size=(1280, 720)),
    )
    client.post(f"/api/projects/{project_name}/generation/backgrounds/{bg_slot['asset_id']}/accept")
    client.post(f"/api/projects/{project_name}/generation/characters/confirm")
    client.post(f"/api/projects/{project_name}/generation/backgrounds/confirm")

    preview = client.post(f"/api/projects/{project_name}/generation/script/preview")
    assert preview.status_code == 200, preview.text
    _assert_no_absolute_paths(preview.json())

    commit = client.post(f"/api/projects/{project_name}/generation/script/commit")
    assert commit.status_code == 200, commit.text
    _assert_no_absolute_paths(commit.json())

    index_payload = json.loads((tmp_path / project_name / "meta" / "index.json").read_text(
        encoding="utf-8"
    ))
    _assert_no_absolute_paths(index_payload)
