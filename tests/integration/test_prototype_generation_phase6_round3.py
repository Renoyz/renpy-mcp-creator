"""Phase 6 Round 3: Prototype activation boundary + build/preview contract."""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from renpy_mcp.web.fastapi_app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from renpy_mcp.config import RenPyConfig, get_settings
    from renpy_mcp.web.fastapi_app import set_config

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)
    set_config(RenPyConfig(sdk_path=Path(".")))
    app = create_app()
    return TestClient(app)


def _create_project(client: TestClient, tmp_path: Path, name: str) -> None:
    game_dir = tmp_path / name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text(
        'label start:\n    "Hello from the Ren\'Py MCP server!"\n    return\n',
        encoding="utf-8",
    )
    r = client.post("/api/projects", json={"name": name})
    assert r.status_code == 200


def _make_scene_packages() -> dict:
    """Return a raw scene_packages dict with two chapters, two scenes each."""
    return {
        "chapters": [
            {
                "chapter_id": "ch1",
                "chapter_name": "Chapter1",
                "chapter_order": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "title": "Opening",
                        "summary": "The opening scene.",
                        "location": "classroom",
                        "location_visual_brief": "A quiet classroom",
                        "mood": "calm",
                        "characters_present": ["Alice"],
                        "dialogue_beats": [
                            {
                                "speaker": "Alice",
                                "intent": "intro",
                                "content_brief": "Hello",
                                "spoken_line": "Hello everyone",
                            }
                        ],
                        "entry_label": "prototype_ch1_start",
                        "next_scene_id": "s2",
                        "scene_order": 1,
                    },
                    {
                        "scene_id": "s2",
                        "title": "Development",
                        "summary": "Things develop.",
                        "location": "hallway",
                        "location_visual_brief": "A dim hallway",
                        "mood": "tense",
                        "characters_present": ["Alice", "Bob"],
                        "dialogue_beats": [
                            {
                                "speaker": "Bob",
                                "intent": "warn",
                                "content_brief": "Be careful",
                                "spoken_line": "Be careful",
                            }
                        ],
                        "entry_label": "prototype_ch1_scene2",
                        "next_scene_id": None,
                        "scene_order": 2,
                    },
                ],
            },
            {
                "chapter_id": "ch2",
                "chapter_name": "Chapter2",
                "chapter_order": 2,
                "scenes": [
                    {
                        "scene_id": "s3",
                        "title": "Twist",
                        "summary": "A shocking revelation.",
                        "location": "roof",
                        "location_visual_brief": "School rooftop",
                        "mood": "shocking",
                        "characters_present": ["Alice"],
                        "dialogue_beats": [
                            {
                                "speaker": "Alice",
                                "intent": "realize",
                                "content_brief": "No way",
                                "spoken_line": "No way",
                            }
                        ],
                        "entry_label": "prototype_ch2_start",
                        "next_scene_id": "s4",
                        "scene_order": 1,
                    },
                    {
                        "scene_id": "s4",
                        "title": "Climax",
                        "summary": "The final confrontation.",
                        "location": "roof",
                        "location_visual_brief": "School rooftop at night",
                        "mood": "determined",
                        "characters_present": ["Alice", "Bob"],
                        "dialogue_beats": [
                            {
                                "speaker": "Alice",
                                "intent": "decide",
                                "content_brief": "I will do it",
                                "spoken_line": "I will do it",
                            }
                        ],
                        "entry_label": "prototype_ch2_scene2",
                        "next_scene_id": None,
                        "scene_order": 2,
                    },
                ],
            },
        ]
    }


# ---------------------------------------------------------------------------
# 1. Multi-chapter generate does NOT auto-activate runtime entry
# ---------------------------------------------------------------------------


def test_generate_multi_chapter_scripts_does_not_activate_runtime_entry(
    client: TestClient, tmp_path: Path
) -> None:
    """generate_multi_chapter_scripts must only write scripts and index; it must NOT wire script.rpy or mark manifest as active multi_chapter."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "generate_no_activate"
    _create_project(client, tmp_path, project_name)

    game_dir = tmp_path / project_name / "game"
    meta_dir = tmp_path / project_name / "meta"

    original_script = (game_dir / "script.rpy").read_text(encoding="utf-8")

    scene_packages = _make_scene_packages()
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    blueprint = ProjectBlueprint(
        title="Test",
        genre="Test",
        worldview="Test",
        themes=["test"],
        characters=[
            {"name": "Alice", "role": "Protagonist", "personality": "brave", "appearance": "tall"},
            {"name": "Bob", "role": "Companion", "personality": "smart", "appearance": "glasses"},
        ],
        chapters=[
            {"id": "ch1", "name": "Chapter1", "order": 1, "scenes": []},
            {"id": "ch2", "name": "Chapter2", "order": 2, "scenes": []},
        ],
    )
    pm = ProjectManager(get_settings())
    pm.write_blueprint(project_name, blueprint)

    service = PrototypeGenerationService(pm=pm, provider=None)
    result = asyncio.run(service.generate_multi_chapter_scripts(project_name, blueprint))

    assert "chapters" in result
    assert len(result["chapters"]) == 2

    assert (game_dir / "script.rpy").read_text(encoding="utf-8") == original_script

    manifest_path = meta_dir / "prototype_manifest.json"
    assert manifest_path.exists(), "prototype_manifest.json must be written by generate"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest.get("mode") != "multi_chapter"
    assert "script_files" in manifest
    assert manifest.get("entry_label") == "prototype_ch1_start"


# ---------------------------------------------------------------------------
# 2. Multi-chapter activate succeeds
# ---------------------------------------------------------------------------


def test_activate_multi_chapter_prototype_updates_manifest_and_entrypoint(
    client: TestClient, tmp_path: Path
) -> None:
    """POST /prototype/multi-chapter/activate must wire script.rpy and set manifest mode to multi_chapter."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "activate_multi"
    _create_project(client, tmp_path, project_name)

    game_dir = tmp_path / project_name / "game"
    meta_dir = tmp_path / project_name / "meta"

    stable_script = 'label start:\n    "Hello from the Ren\'Py MCP server!"\n    return\n'
    (game_dir / "script.rpy").write_text(stable_script, encoding="utf-8")

    scene_packages = _make_scene_packages()
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    blueprint = ProjectBlueprint(
        title="Test",
        genre="Test",
        worldview="Test",
        themes=["test"],
        characters=[
            {"name": "Alice", "role": "Protagonist", "personality": "brave", "appearance": "tall"},
            {"name": "Bob", "role": "Companion", "personality": "smart", "appearance": "glasses"},
        ],
        chapters=[
            {"id": "ch1", "name": "Chapter1", "order": 1, "scenes": []},
            {"id": "ch2", "name": "Chapter2", "order": 2, "scenes": []},
        ],
    )
    pm = ProjectManager(get_settings())
    pm.write_blueprint(project_name, blueprint)

    service = PrototypeGenerationService(pm=pm, provider=None)
    asyncio.run(service.generate_multi_chapter_scripts(project_name, blueprint))

    assert (game_dir / "script.rpy").read_text(encoding="utf-8") == stable_script

    response = client.post(f"/api/projects/{project_name}/prototype/multi-chapter/activate")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("success") is True

    script_content = (game_dir / "script.rpy").read_text(encoding="utf-8")
    assert "call prototype_ch1_start" in script_content

    manifest = json.loads((meta_dir / "prototype_manifest.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "multi_chapter"
    assert manifest["entry_label"] == "prototype_ch1_start"
    assert manifest["entry_file"] == "game/prototype_ch1_Chapter1.rpy"
    assert "game/prototype_ch1_Chapter1.rpy" in manifest["script_files"]
    assert "game/prototype_ch2_Chapter2.rpy" in manifest["script_files"]
    assert manifest["chapter_ids"] == ["ch1", "ch2"]


# ---------------------------------------------------------------------------
# 3. Activate failure rolls back
# ---------------------------------------------------------------------------


def test_activate_multi_chapter_prototype_rolls_back_manifest_and_entrypoint_on_failure(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If activate fails mid-way, script.rpy and manifest must be restored to previous stable state."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "activate_rollback"
    _create_project(client, tmp_path, project_name)

    game_dir = tmp_path / project_name / "game"
    meta_dir = tmp_path / project_name / "meta"

    stable_script = 'label start:\n    "Hello from the Ren\'Py MCP server!"\n    return\n'
    (game_dir / "script.rpy").write_text(stable_script, encoding="utf-8")

    scene_packages = _make_scene_packages()
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    blueprint = ProjectBlueprint(
        title="Test",
        genre="Test",
        worldview="Test",
        themes=["test"],
        characters=[
            {"name": "Alice", "role": "Protagonist", "personality": "brave", "appearance": "tall"},
            {"name": "Bob", "role": "Companion", "personality": "smart", "appearance": "glasses"},
        ],
        chapters=[
            {"id": "ch1", "name": "Chapter1", "order": 1, "scenes": []},
            {"id": "ch2", "name": "Chapter2", "order": 2, "scenes": []},
        ],
    )
    pm = ProjectManager(get_settings())
    pm.write_blueprint(project_name, blueprint)

    service = PrototypeGenerationService(pm=pm, provider=None)
    asyncio.run(service.generate_multi_chapter_scripts(project_name, blueprint))

    candidate_manifest = json.loads((meta_dir / "prototype_manifest.json").read_text(encoding="utf-8"))
    assert candidate_manifest.get("mode") is None

    def _fail_wire(*args, **kwargs):
        raise RuntimeError("Simulated wire failure during activation")

    monkeypatch.setattr(service, "wire_main_script_to_prototype", _fail_wire)

    with pytest.raises(RuntimeError, match="Simulated wire failure during activation"):
        service.activate_multi_chapter_prototype(project_name)

    assert (game_dir / "script.rpy").read_text(encoding="utf-8") == stable_script

    manifest = json.loads((meta_dir / "prototype_manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("mode") is None
    assert manifest.get("entry_label") == "prototype_ch1_start"


# ---------------------------------------------------------------------------
# 4. Single-chapter confirmation restores single_chapter active mode
# ---------------------------------------------------------------------------


def test_single_chapter_pipeline_restores_single_chapter_active_manifest_after_multi_chapter_mode(
    client: TestClient, tmp_path: Path
) -> None:
    """After multi-chapter is active, running the single-chapter confirmation pipeline must switch manifest back to single_chapter."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "single_after_multi"
    _create_project(client, tmp_path, project_name)

    meta_dir = tmp_path / project_name / "meta"
    game_dir = tmp_path / project_name / "game"

    scene_packages = _make_scene_packages()
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    blueprint = ProjectBlueprint(
        title="Test",
        genre="Test",
        worldview="Test",
        themes=["test"],
        characters=[
            {"name": "Alice", "role": "Protagonist", "personality": "brave", "appearance": "tall"},
            {"name": "Bob", "role": "Companion", "personality": "smart", "appearance": "glasses"},
        ],
        chapters=[
            {"id": "ch1", "name": "Chapter1", "order": 1, "scenes": []},
            {"id": "ch2", "name": "Chapter2", "order": 2, "scenes": []},
        ],
    )
    pm = ProjectManager(get_settings())
    pm.write_blueprint(project_name, blueprint)

    service = PrototypeGenerationService(pm=pm, provider=None)
    asyncio.run(service.generate_multi_chapter_scripts(project_name, blueprint))
    service.activate_multi_chapter_prototype(project_name)

    manifest = json.loads((meta_dir / "prototype_manifest.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "multi_chapter"

    chapter = service.select_prototype_chapter(blueprint)
    from renpy_mcp.services.prototype_generation_service import PrototypeScene
    scenes = [
        PrototypeScene(
            scene_id="proto-s1",
            title="Test Scene",
            summary="A test scene.",
            location="classroom",
            characters_present=["Alice"],
            entry_label="prototype_ch1_start",
            next_scene_id=None,
        )
    ]
    staging_path = service.write_script(project_name, chapter, scenes)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)
    service.update_index(project_name, chapter, scenes, staging_path)
    service.commit_prototype_replacement(project_name, [s.scene_id for s in scenes], staging_path)

    final_path = staging_path.replace(".__staging__", "").replace("\\", "/")
    service.activate_single_chapter_prototype(
        project_name,
        entry_label=scenes[0].entry_label,
        entry_file=final_path,
        chapter_ids=[chapter.id],
        script_files=[final_path],
    )

    manifest = json.loads((meta_dir / "prototype_manifest.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "single_chapter"
    assert manifest["entry_label"] == "prototype_ch1_start"
    assert manifest["script_files"] == ["game/prototype_ch1_Chapter1.rpy"]
    assert manifest["chapter_ids"] == ["ch1"]


# ---------------------------------------------------------------------------
# 5. Prototype status API reports active mode and entry metadata
# ---------------------------------------------------------------------------


def test_prototype_status_api_reports_active_mode_and_entry_metadata(
    client: TestClient, tmp_path: Path
) -> None:
    """GET /prototype/status must return mode, entry_label, entry_file, script_files, chapter_ids."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "status_api"
    _create_project(client, tmp_path, project_name)

    meta_dir = tmp_path / project_name / "meta"

    scene_packages = _make_scene_packages()
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    blueprint = ProjectBlueprint(
        title="Test",
        genre="Test",
        worldview="Test",
        themes=["test"],
        characters=[
            {"name": "Alice", "role": "Protagonist", "personality": "brave", "appearance": "tall"},
            {"name": "Bob", "role": "Companion", "personality": "smart", "appearance": "glasses"},
        ],
        chapters=[
            {"id": "ch1", "name": "Chapter1", "order": 1, "scenes": []},
            {"id": "ch2", "name": "Chapter2", "order": 2, "scenes": []},
        ],
    )
    pm = ProjectManager(get_settings())
    pm.write_blueprint(project_name, blueprint)

    service = PrototypeGenerationService(pm=pm, provider=None)
    asyncio.run(service.generate_multi_chapter_scripts(project_name, blueprint))

    response = client.get(f"/api/projects/{project_name}/prototype/status")
    assert response.status_code == 200
    data = response.json()
    assert data.get("mode") is None or data.get("mode") != "multi_chapter"
    assert "script_files" in data
    assert "chapter_ids" in data

    service.activate_multi_chapter_prototype(project_name)

    response = client.get(f"/api/projects/{project_name}/prototype/status")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "multi_chapter"
    assert data["entry_label"] == "prototype_ch1_start"
    assert data["entry_file"] == "game/prototype_ch1_Chapter1.rpy"
    assert "game/prototype_ch1_Chapter1.rpy" in data["script_files"]
    assert "game/prototype_ch2_Chapter2.rpy" in data["script_files"]
    assert data["chapter_ids"] == ["ch1", "ch2"]


# ---------------------------------------------------------------------------
# Review fix A: manifest write failure rolls back generate output
# ---------------------------------------------------------------------------


def test_generate_multi_chapter_scripts_rolls_back_when_manifest_write_fails(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If manifest write fails during commit after overwriting old manifest, generate must roll back to previous stable state."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "manifest_rollback_test"
    _create_project(client, tmp_path, project_name)

    game_dir = tmp_path / project_name / "game"
    meta_dir = tmp_path / project_name / "meta"

    old_script = 'label start:\n    "Old script"\n    return\n'
    (game_dir / "script.rpy").write_text(old_script, encoding="utf-8")

    old_index = {"scenes": {"old_scene": {"source": "prototype", "title": "Old"}}}
    (meta_dir / "index.json").write_text(json.dumps(old_index), encoding="utf-8")

    old_manifest = {
        "mode": "single_chapter",
        "entry_label": "old_start",
        "entry_file": "game/old.rpy",
        "script_files": ["game/old.rpy"],
        "chapter_ids": ["old_ch"],
        "source": "prototype",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    (meta_dir / "prototype_manifest.json").write_text(
        json.dumps(old_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    old_ch1 = game_dir / "prototype_ch1_Chapter1.rpy"
    old_ch1.write_text("label old_ch1:\n    return\n", encoding="utf-8")

    scene_packages = _make_scene_packages()
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    blueprint = ProjectBlueprint(
        title="Test",
        genre="Test",
        worldview="Test",
        themes=["test"],
        characters=[
            {"name": "Alice", "role": "Protagonist", "personality": "brave", "appearance": "tall"},
            {"name": "Bob", "role": "Companion", "personality": "smart", "appearance": "glasses"},
        ],
        chapters=[
            {"id": "ch1", "name": "Chapter1", "order": 1, "scenes": []},
            {"id": "ch2", "name": "Chapter2", "order": 2, "scenes": []},
        ],
    )
    pm = ProjectManager(get_settings())
    pm.write_blueprint(project_name, blueprint)

    service = PrototypeGenerationService(pm=pm, provider=None)

    original_write = pm.write_prototype_manifest
    manifest_overwritten = False

    def _fail_after_write(*args, **kwargs):
        nonlocal manifest_overwritten
        # Write the file first, then fail — simulating a failure after overwrite
        original_write(*args, **kwargs)
        manifest_overwritten = True
        raise RuntimeError("Simulated manifest write failure after overwrite")

    monkeypatch.setattr(pm, "write_prototype_manifest", _fail_after_write)

    with pytest.raises(RuntimeError, match="Simulated manifest write failure after overwrite"):
        asyncio.run(service.generate_multi_chapter_scripts(project_name, blueprint))

    # Confirm the monkeypatch actually overwrote the manifest before failing
    assert manifest_overwritten, "Monkeypatch must have overwritten the manifest before failing"

    # script.rpy untouched
    assert (game_dir / "script.rpy").read_text(encoding="utf-8") == old_script

    # Old index restored
    index = json.loads((meta_dir / "index.json").read_text(encoding="utf-8"))
    assert "old_scene" in index.get("scenes", {})
    assert "s1" not in index.get("scenes", {})

    # Old manifest restored — NOT just because it was never touched,
    # but because rollback actively wrote the old content back.
    manifest = json.loads((meta_dir / "prototype_manifest.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "single_chapter"
    assert manifest["entry_label"] == "old_start"
    assert manifest["entry_file"] == "game/old.rpy"
    assert manifest["script_files"] == ["game/old.rpy"]
    assert manifest["chapter_ids"] == ["old_ch"]
    assert manifest["updated_at"] == "2024-01-01T00:00:00Z"

    # Old same-name file restored
    assert old_ch1.exists()
    assert old_ch1.read_text(encoding="utf-8") == "label old_ch1:\n    return\n"

    # No new chapter files left behind
    assert not (game_dir / "prototype_ch2_Chapter2.rpy").exists()

    # stale cleanup did NOT run (old stale file should still exist if any)
    # We don't create stale files here; the key point is rollback happened


# ---------------------------------------------------------------------------
# Review fix B: invalid manifest read raises explicitly
# ---------------------------------------------------------------------------


def test_invalid_prototype_manifest_file_raises_instead_of_silent_fallback(
    client: TestClient, tmp_path: Path
) -> None:
    """read_prototype_manifest must raise ValueError for an existing but corrupt file."""
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "bad_manifest"
    _create_project(client, tmp_path, project_name)

    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "prototype_manifest.json").write_text(
        "this is not json {", encoding="utf-8"
    )

    pm = ProjectManager(get_settings())
    with pytest.raises(ValueError, match="invalid JSON"):
        pm.read_prototype_manifest(project_name)


# ---------------------------------------------------------------------------
# Review fix C: status API returns 500 on invalid manifest
# ---------------------------------------------------------------------------


def test_prototype_status_api_returns_500_for_invalid_manifest(
    client: TestClient, tmp_path: Path
) -> None:
    """GET /prototype/status must return 500 when prototype_manifest.json is corrupt."""
    project_name = "status_bad_manifest"
    _create_project(client, tmp_path, project_name)

    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "prototype_manifest.json").write_text(
        "not valid json", encoding="utf-8"
    )

    response = client.get(f"/api/projects/{project_name}/prototype/status")
    assert response.status_code == 500
    data = response.json()
    assert "manifest" in data.get("detail", "").lower() or "invalid" in data.get("detail", "").lower()


# ---------------------------------------------------------------------------
# Review fix D: activate API returns explicit error on invalid manifest
# ---------------------------------------------------------------------------


def test_activate_multi_chapter_prototype_returns_500_for_invalid_manifest(
    client: TestClient, tmp_path: Path
) -> None:
    """POST /prototype/multi-chapter/activate must return 500 (not "run generate first") when manifest is corrupt."""
    project_name = "activate_bad_manifest"
    _create_project(client, tmp_path, project_name)

    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "prototype_manifest.json").write_text(
        "not valid json", encoding="utf-8"
    )

    response = client.post(f"/api/projects/{project_name}/prototype/multi-chapter/activate")
    assert response.status_code == 500
    data = response.json()
    detail = data.get("detail", "")
    assert "invalid" in detail.lower() or "manifest" in detail.lower()
    assert "generate first" not in detail.lower()


# ---------------------------------------------------------------------------
# Review fix E: valid manifest roundtrip is structured
# ---------------------------------------------------------------------------


def test_prototype_manifest_roundtrip_uses_structured_model(
    client: TestClient, tmp_path: Path
) -> None:
    """read_prototype_manifest must return a structured model, not a raw dict."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings
    from renpy_mcp.blueprint.models import PrototypeManifest

    project_name = "manifest_roundtrip"
    _create_project(client, tmp_path, project_name)

    meta_dir = tmp_path / project_name / "meta"

    scene_packages = _make_scene_packages()
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    blueprint = ProjectBlueprint(
        title="Test",
        genre="Test",
        worldview="Test",
        themes=["test"],
        characters=[
            {"name": "Alice", "role": "Protagonist", "personality": "brave", "appearance": "tall"},
            {"name": "Bob", "role": "Companion", "personality": "smart", "appearance": "glasses"},
        ],
        chapters=[
            {"id": "ch1", "name": "Chapter1", "order": 1, "scenes": []},
            {"id": "ch2", "name": "Chapter2", "order": 2, "scenes": []},
        ],
    )
    pm = ProjectManager(get_settings())
    pm.write_blueprint(project_name, blueprint)

    service = PrototypeGenerationService(pm=pm, provider=None)
    asyncio.run(service.generate_multi_chapter_scripts(project_name, blueprint))

    manifest = pm.read_prototype_manifest(project_name)
    assert isinstance(manifest, PrototypeManifest)
    assert manifest.entry_label == "prototype_ch1_start"
    assert manifest.script_files == ["game/prototype_ch1_Chapter1.rpy", "game/prototype_ch2_Chapter2.rpy"]
    assert manifest.chapter_ids == ["ch1", "ch2"]
    assert manifest.mode is None
    assert manifest.source == "prototype"


# ---------------------------------------------------------------------------
# Review fix F: first manifest write failure leaves no manifest behind
# ---------------------------------------------------------------------------


def test_generate_multi_chapter_scripts_removes_new_manifest_on_first_write_failure(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If manifest write fails during the first-ever generate, rollback must remove any partial manifest file."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "first_manifest_rollback"
    _create_project(client, tmp_path, project_name)

    game_dir = tmp_path / project_name / "game"
    meta_dir = tmp_path / project_name / "meta"

    old_script = 'label start:\n    "Hello from the Ren\'Py MCP server!"\n    return\n'
    (game_dir / "script.rpy").write_text(old_script, encoding="utf-8")

    old_index = {"scenes": {"old_scene": {"source": "prototype", "title": "Old"}}}
    (meta_dir / "index.json").write_text(json.dumps(old_index), encoding="utf-8")

    # NO prototype_manifest.json exists initially
    assert not (meta_dir / "prototype_manifest.json").exists()

    scene_packages = _make_scene_packages()
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    blueprint = ProjectBlueprint(
        title="Test",
        genre="Test",
        worldview="Test",
        themes=["test"],
        characters=[
            {"name": "Alice", "role": "Protagonist", "personality": "brave", "appearance": "tall"},
            {"name": "Bob", "role": "Companion", "personality": "smart", "appearance": "glasses"},
        ],
        chapters=[
            {"id": "ch1", "name": "Chapter1", "order": 1, "scenes": []},
            {"id": "ch2", "name": "Chapter2", "order": 2, "scenes": []},
        ],
    )
    pm = ProjectManager(get_settings())
    pm.write_blueprint(project_name, blueprint)

    service = PrototypeGenerationService(pm=pm, provider=None)

    original_write = pm.write_prototype_manifest

    def _fail_after_write(*args, **kwargs):
        # Write the file first, then fail — simulating a partial/corrupted write
        original_write(*args, **kwargs)
        raise RuntimeError("Simulated manifest write failure")

    monkeypatch.setattr(pm, "write_prototype_manifest", _fail_after_write)

    with pytest.raises(RuntimeError, match="Simulated manifest write failure"):
        asyncio.run(service.generate_multi_chapter_scripts(project_name, blueprint))

    # manifest must NOT exist after rollback (it never existed before)
    assert not (meta_dir / "prototype_manifest.json").exists()

    # Old index restored
    index = json.loads((meta_dir / "index.json").read_text(encoding="utf-8"))
    assert "old_scene" in index.get("scenes", {})
    assert "s1" not in index.get("scenes", {})

    # No new chapter files left behind
    assert not (game_dir / "prototype_ch1_Chapter1.rpy").exists()
    assert not (game_dir / "prototype_ch2_Chapter2.rpy").exists()


# ---------------------------------------------------------------------------
# Review fix G: invalid mode is rejected by schema
# ---------------------------------------------------------------------------


def test_invalid_prototype_manifest_mode_raises_validation_error(
    client: TestClient, tmp_path: Path
) -> None:
    """read_prototype_manifest must raise ValueError when mode is not a valid protocol value."""
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "invalid_mode"
    _create_project(client, tmp_path, project_name)

    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    bad_manifest = {
        "mode": "not_real_mode",
        "entry_label": "foo",
        "entry_file": "game/foo.rpy",
        "chapter_ids": ["ch1"],
        "script_files": ["game/foo.rpy"],
        "source": "prototype",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    (meta_dir / "prototype_manifest.json").write_text(
        json.dumps(bad_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    pm = ProjectManager(get_settings())
    with pytest.raises(ValueError):
        pm.read_prototype_manifest(project_name)


# ---------------------------------------------------------------------------
# Review fix H: status API returns 500 for invalid mode
# ---------------------------------------------------------------------------


def test_prototype_status_api_returns_500_for_invalid_manifest_mode(
    client: TestClient, tmp_path: Path
) -> None:
    """GET /prototype/status must return 500 when manifest mode is an illegal value."""
    project_name = "status_invalid_mode"
    _create_project(client, tmp_path, project_name)

    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    bad_manifest = {
        "mode": "invalid_mode_value",
        "entry_label": "foo",
        "entry_file": "game/foo.rpy",
        "chapter_ids": ["ch1"],
        "script_files": ["game/foo.rpy"],
        "source": "prototype",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    (meta_dir / "prototype_manifest.json").write_text(
        json.dumps(bad_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    response = client.get(f"/api/projects/{project_name}/prototype/status")
    assert response.status_code == 500


def test_activate_multi_chapter_prototype_returns_500_for_invalid_manifest_mode(
    client: TestClient, tmp_path: Path
) -> None:
    """POST /prototype/multi-chapter/activate must return 500 when manifest mode is illegal."""
    project_name = "activate_invalid_mode"
    _create_project(client, tmp_path, project_name)

    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    bad_manifest = {
        "mode": "bogus",
        "entry_label": "foo",
        "entry_file": "game/foo.rpy",
        "chapter_ids": ["ch1"],
        "script_files": ["game/foo.rpy"],
        "source": "prototype",
        "updated_at": "2024-01-01T00:00:00Z",
    }
    (meta_dir / "prototype_manifest.json").write_text(
        json.dumps(bad_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    response = client.post(f"/api/projects/{project_name}/prototype/multi-chapter/activate")
    assert response.status_code == 500
