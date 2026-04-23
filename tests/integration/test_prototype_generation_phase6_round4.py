"""Phase 6 Round 4: Active prototype readiness boundary for build/preview."""

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
# 1. Candidate multi-chapter is NOT active / buildable
# ---------------------------------------------------------------------------


def test_prototype_status_marks_generated_but_unactivated_multi_chapter_as_not_active(
    client: TestClient, tmp_path: Path
) -> None:
    """After generate_multi_chapter_scripts (but before activate), status must show not active / not buildable."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "candidate_not_active"
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
    service.generate_multi_chapter_scripts(project_name, blueprint)

    response = client.get(f"/api/projects/{project_name}/prototype/status")
    assert response.status_code == 200
    data = response.json()

    assert data.get("mode") is None, f"Expected mode=None for candidate, got {data.get('mode')}"
    assert data.get("is_active") is False, f"Expected is_active=False for candidate, got {data.get('is_active')}"
    assert data.get("manifest_consistent") is False, (
        f"Expected manifest_consistent=False for candidate, got {data.get('manifest_consistent')}"
    )
    assert data.get("is_buildable") is False, (
        f"Expected is_buildable=False for candidate, got {data.get('is_buildable')}"
    )
    assert data.get("wired") is False, "script.rpy should not be wired before activation"


# ---------------------------------------------------------------------------
# 2. Activated multi-chapter is active / buildable when consistent
# ---------------------------------------------------------------------------


def test_prototype_status_marks_activated_multi_chapter_as_active_and_buildable(
    client: TestClient, tmp_path: Path
) -> None:
    """After activate_multi_chapter_prototype, status must show active / buildable / consistent."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "activated_active"
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
    service.generate_multi_chapter_scripts(project_name, blueprint)
    service.activate_multi_chapter_prototype(project_name)

    response = client.get(f"/api/projects/{project_name}/prototype/status")
    assert response.status_code == 200
    data = response.json()

    assert data["mode"] == "multi_chapter"
    assert data["is_active"] is True
    assert data["manifest_consistent"] is True
    assert data["is_buildable"] is True
    assert data["wired"] is True
    assert data["entry_label"] == "prototype_ch1_start"
    assert data["entry_file"] == "game/prototype_ch1_Chapter1.rpy"
    assert "game/prototype_ch1_Chapter1.rpy" in data["script_files"]
    assert "game/prototype_ch2_Chapter2.rpy" in data["script_files"]
    assert data["chapter_ids"] == ["ch1", "ch2"]


# ---------------------------------------------------------------------------
# 3. Manifest says multi_chapter but entry file missing -> inconsistent
# ---------------------------------------------------------------------------


def test_prototype_status_reports_inconsistent_when_manifest_entry_file_is_missing(
    client: TestClient, tmp_path: Path
) -> None:
    """If manifest claims multi_chapter but the entry file is missing, status must report inconsistent."""
    from renpy_mcp.blueprint.models import PrototypeManifest
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "missing_entry_file"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    manifest = PrototypeManifest(
        mode="multi_chapter",
        entry_label="prototype_ch1_start",
        entry_file="game/missing.rpy",
        script_files=["game/missing.rpy"],
        chapter_ids=["ch1"],
        updated_at="2024-01-01T00:00:00Z",
    )
    pm.write_prototype_manifest(project_name, manifest)

    # Wire script.rpy so the only failure is missing entry file
    game_dir = tmp_path / project_name / "game"
    (game_dir / "script.rpy").write_text(
        "label start:\n    # PROTOTYPE START (managed)\n    call prototype_ch1_start\n    return\n    # PROTOTYPE END (managed)\n",
        encoding="utf-8",
    )

    response = client.get(f"/api/projects/{project_name}/prototype/status")
    assert response.status_code == 200
    data = response.json()

    assert data["mode"] == "multi_chapter"
    assert data["is_active"] is False, "is_active must be False when entry_file is missing"
    assert data["manifest_consistent"] is False
    assert data["is_buildable"] is False


# ---------------------------------------------------------------------------
# 4. Manifest says active but script.rpy not wired -> inconsistent
# ---------------------------------------------------------------------------


def test_prototype_status_reports_inconsistent_when_main_script_is_not_wired_to_active_prototype(
    client: TestClient, tmp_path: Path
) -> None:
    """If manifest has a valid mode but script.rpy lacks the managed prototype marker, status must report inconsistent."""
    from renpy_mcp.blueprint.models import PrototypeManifest
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "not_wired"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    # Create the entry file so only wiring is missing
    game_dir = tmp_path / project_name / "game"
    entry_path = game_dir / "prototype_ch1_Chapter1.rpy"
    entry_path.write_text('label prototype_ch1_start:\n    "Hello"\n    return\n', encoding="utf-8")

    manifest = PrototypeManifest(
        mode="single_chapter",
        entry_label="prototype_ch1_start",
        entry_file="game/prototype_ch1_Chapter1.rpy",
        script_files=["game/prototype_ch1_Chapter1.rpy"],
        chapter_ids=["ch1"],
        updated_at="2024-01-01T00:00:00Z",
    )
    pm.write_prototype_manifest(project_name, manifest)

    # script.rpy is NOT wired (it still has the default template content from _create_project)

    response = client.get(f"/api/projects/{project_name}/prototype/status")
    assert response.status_code == 200
    data = response.json()

    assert data["mode"] == "single_chapter"
    assert data["wired"] is False
    assert data["is_active"] is False, "is_active must be False when script.rpy is not wired"
    assert data["manifest_consistent"] is False
    assert data["is_buildable"] is False


# ---------------------------------------------------------------------------
# 5. Single-chapter path still reports active correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prototype_status_reports_single_chapter_active_after_confirmation_commit(
    client: TestClient, tmp_path: Path
) -> None:
    """After a full single-chapter confirmation pipeline, status must show single_chapter active / buildable."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "single_chapter_active"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    blueprint = ProjectBlueprint(
        title="Test",
        genre="Test",
        worldview="Test",
        themes=["test"],
        characters=[
            {"name": "Alice", "role": "Protagonist", "personality": "brave", "appearance": "tall"},
        ],
        chapters=[
            {"id": "ch1", "name": "Chapter1", "order": 1, "scenes": []},
        ],
    )

    service = PrototypeGenerationService(pm=pm, provider=None)

    # Manually construct a scene and write script (simulate confirmation pipeline)
    from renpy_mcp.services.prototype_generation_service import PrototypeScene, DialogueBeat

    scenes = [
        PrototypeScene(
            scene_id="s1",
            title="Opening",
            summary="The opening.",
            location="classroom",
            characters_present=["Alice"],
            dialogue_beats=[
                DialogueBeat(speaker="Alice", intent="greet", content_brief="Hello"),
            ],
            entry_label="prototype_ch1_start",
            next_scene_id=None,
        ),
    ]

    chapter = blueprint.chapters[0]
    staging_path = service.write_script(project_name, chapter, scenes)
    final_path = service._final_path_from_staging(staging_path)
    new_scene_ids = [s.scene_id for s in scenes]
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)
    service.update_index(project_name, chapter, scenes, final_path)
    service.commit_prototype_replacement(project_name, new_scene_ids, staging_path)
    service.activate_single_chapter_prototype(
        project_name,
        entry_label=scenes[0].entry_label,
        entry_file=final_path,
        chapter_ids=[chapter.id],
        script_files=[final_path],
    )

    response = client.get(f"/api/projects/{project_name}/prototype/status")
    assert response.status_code == 200
    data = response.json()

    assert data["mode"] == "single_chapter"
    assert data["is_active"] is True
    assert data["manifest_consistent"] is True
    assert data["is_buildable"] is True
    assert data["wired"] is True
    assert data["entry_label"] == "prototype_ch1_start"
    assert data["entry_file"] == final_path


# ---------------------------------------------------------------------------
# 6. Build API rejects candidate multi-chapter (mode=None)
# ---------------------------------------------------------------------------


def test_build_rejects_candidate_multi_chapter_with_no_active_mode(
    client: TestClient, tmp_path: Path
) -> None:
    """POST /prototype/build must reject when manifest exists but has no active mode (candidate state)."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "build_rejects_candidate"
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
    service.generate_multi_chapter_scripts(project_name, blueprint)

    # script.rpy is NOT wired (candidate state)
    response = client.post(f"/api/projects/{project_name}/prototype/build", json={"target": "web"})
    assert response.status_code == 400, f"Expected 400 for candidate build, got {response.status_code}: {response.text}"
    detail = response.json().get("detail", "")
    assert "active" in detail.lower() or "wire" in detail.lower() or "prototype" in detail.lower(), (
        f"Expected active/wire-related rejection, got: {detail}"
    )


# ---------------------------------------------------------------------------
# 7. Status reports inconsistent when managed script calls wrong label
# ---------------------------------------------------------------------------


def test_prototype_status_reports_inconsistent_when_managed_script_calls_wrong_entry_label(
    client: TestClient, tmp_path: Path
) -> None:
    """If script.rpy has a managed region but calls a different label than manifest.entry_label, status must report inconsistent."""
    from renpy_mcp.blueprint.models import PrototypeManifest
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "wrong_wired_label"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    # Create entry file
    game_dir = tmp_path / project_name / "game"
    entry_path = game_dir / "prototype_ch2_Chapter2.rpy"
    entry_path.write_text('label prototype_ch2_start:\n    "Hello"\n    return\n', encoding="utf-8")

    # Manifest says entry_label should be prototype_ch2_start
    manifest = PrototypeManifest(
        mode="multi_chapter",
        entry_label="prototype_ch2_start",
        entry_file="game/prototype_ch2_Chapter2.rpy",
        script_files=["game/prototype_ch2_Chapter2.rpy"],
        chapter_ids=["ch2"],
        updated_at="2024-01-01T00:00:00Z",
    )
    pm.write_prototype_manifest(project_name, manifest)

    # But script.rpy is wired to call prototype_ch1_start (wrong label)
    (game_dir / "script.rpy").write_text(
        "label start:\n    # PROTOTYPE START (managed)\n    call prototype_ch1_start\n    return\n    # PROTOTYPE END (managed)\n",
        encoding="utf-8",
    )

    response = client.get(f"/api/projects/{project_name}/prototype/status")
    assert response.status_code == 200
    data = response.json()

    assert data["mode"] == "multi_chapter"
    assert data["wired"] is True, "managed region with a valid call line should still be wired"
    assert data.get("wired_entry_label") == "prototype_ch1_start"
    assert data.get("entry_label_matches") is False
    assert data["is_active"] is False, "is_active must be False when wired label does not match manifest"
    assert data["manifest_consistent"] is False
    assert data["is_buildable"] is False


# ---------------------------------------------------------------------------
# 8. Build rejects when managed script is wired to different entry than manifest
# ---------------------------------------------------------------------------


def test_build_rejects_when_main_script_is_wired_to_different_entry_than_manifest(
    client: TestClient, tmp_path: Path
) -> None:
    """POST /prototype/build must reject when script.rpy calls a different label than manifest.entry_label."""
    from renpy_mcp.blueprint.models import PrototypeManifest
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "build_rejects_wrong_label"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    # Create entry file with correct label
    game_dir = tmp_path / project_name / "game"
    entry_path = game_dir / "prototype_ch2_Chapter2.rpy"
    entry_path.write_text('label prototype_ch2_start:\n    "Hello"\n    return\n', encoding="utf-8")

    # Manifest says entry_label = prototype_ch2_start
    manifest = PrototypeManifest(
        mode="multi_chapter",
        entry_label="prototype_ch2_start",
        entry_file="game/prototype_ch2_Chapter2.rpy",
        script_files=["game/prototype_ch2_Chapter2.rpy"],
        chapter_ids=["ch2"],
        updated_at="2024-01-01T00:00:00Z",
    )
    pm.write_prototype_manifest(project_name, manifest)

    # Also need a prototype index entry so build step 1 passes
    index = {"scenes": {"s3": {"source": "prototype", "file_path": "game/prototype_ch2_Chapter2.rpy", "chapter_id": "ch2"}}}
    pm.write_project_index(project_name, index)

    # script.rpy wired to WRONG label
    (game_dir / "script.rpy").write_text(
        "label start:\n    # PROTOTYPE START (managed)\n    call prototype_ch1_start\n    return\n    # PROTOTYPE END (managed)\n",
        encoding="utf-8",
    )

    response = client.post(f"/api/projects/{project_name}/prototype/build", json={"target": "web"})
    assert response.status_code == 400, f"Expected 400 for wrong label build, got {response.status_code}: {response.text}"
    detail = response.json().get("detail", "")
    assert "inconsistent" in detail.lower() or "entry" in detail.lower() or "label" in detail.lower(), (
        f"Expected inconsistency-related rejection, got: {detail}"
    )


# ---------------------------------------------------------------------------
# 9. Status surfaces current wired entry label
# ---------------------------------------------------------------------------


def test_prototype_status_reports_current_wired_entry_label(
    client: TestClient, tmp_path: Path
) -> None:
    """Status response must include wired_entry_label reflecting the actual call in script.rpy."""
    from renpy_mcp.blueprint.models import PrototypeManifest
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "reports_wired_label"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    game_dir = tmp_path / project_name / "game"
    entry_path = game_dir / "prototype.rpy"
    entry_path.write_text('label my_custom_label:\n    "Hello"\n    return\n', encoding="utf-8")

    manifest = PrototypeManifest(
        mode="multi_chapter",
        entry_label="my_custom_label",
        entry_file="game/prototype.rpy",
        script_files=["game/prototype.rpy"],
        chapter_ids=["ch1"],
        updated_at="2024-01-01T00:00:00Z",
    )
    pm.write_prototype_manifest(project_name, manifest)

    (game_dir / "script.rpy").write_text(
        "label start:\n    # PROTOTYPE START (managed)\n    call my_custom_label\n    return\n    # PROTOTYPE END (managed)\n",
        encoding="utf-8",
    )

    response = client.get(f"/api/projects/{project_name}/prototype/status")
    assert response.status_code == 200
    data = response.json()

    assert data.get("wired_entry_label") == "my_custom_label"
    assert data.get("entry_label_matches") is True
    assert data["is_active"] is True
    assert data["manifest_consistent"] is True
    assert data["is_buildable"] is True


# ---------------------------------------------------------------------------
# 10. Pipeline-status does not report ready for generated-but-unactivated
# ---------------------------------------------------------------------------


def test_prototype_pipeline_status_does_not_report_ready_for_generated_but_unactivated_multi_chapter(
    client: TestClient, tmp_path: Path
) -> None:
    """A multi-chapter candidate (manifest exists but mode=None) must not report prototype_ready."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "pipeline_candidate_not_ready"
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
    service.generate_multi_chapter_scripts(project_name, blueprint)

    # Candidate state: manifest exists with mode=None, script.rpy not wired
    response = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
    assert response.status_code == 200
    data = response.json()

    assert data["stage"] != "prototype_ready", (
        f"Candidate multi-chapter should not be prototype_ready, got {data['stage']}"
    )
    assert data["stage"] == "idle", f"Expected idle for candidate, got {data['stage']}"


# ---------------------------------------------------------------------------
# 11. Pipeline-status does not report ready when wiring label is inconsistent
# ---------------------------------------------------------------------------


def test_prototype_pipeline_status_does_not_report_ready_when_manifest_and_wiring_label_are_inconsistent(
    client: TestClient, tmp_path: Path
) -> None:
    """If wired_entry_label != manifest.entry_label, pipeline-status must not report prototype_ready."""
    from renpy_mcp.blueprint.models import PrototypeManifest
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "pipeline_inconsistent_not_ready"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    game_dir = tmp_path / project_name / "game"
    entry_path = game_dir / "prototype_ch2_Chapter2.rpy"
    entry_path.write_text('label prototype_ch2_start:\n    "Hello"\n    return\n', encoding="utf-8")

    manifest = PrototypeManifest(
        mode="multi_chapter",
        entry_label="prototype_ch2_start",
        entry_file="game/prototype_ch2_Chapter2.rpy",
        script_files=["game/prototype_ch2_Chapter2.rpy"],
        chapter_ids=["ch2"],
        updated_at="2024-01-01T00:00:00Z",
    )
    pm.write_prototype_manifest(project_name, manifest)

    # script.rpy wired to WRONG label
    (game_dir / "script.rpy").write_text(
        "label start:\n    # PROTOTYPE START (managed)\n    call prototype_ch1_start\n    return\n    # PROTOTYPE END (managed)\n",
        encoding="utf-8",
    )

    response = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
    assert response.status_code == 200
    data = response.json()

    assert data["stage"] != "prototype_ready", (
        f"Inconsistent wiring should not be prototype_ready, got {data['stage']}"
    )
    assert data["stage"] == "idle", f"Expected idle for inconsistent state, got {data['stage']}"


# ---------------------------------------------------------------------------
# 12. Pipeline-status reports ready for active consistent prototype
# ---------------------------------------------------------------------------


def test_prototype_pipeline_status_reports_ready_for_active_consistent_prototype_before_build(
    client: TestClient, tmp_path: Path
) -> None:
    """An active consistent prototype with no build result must report prototype_ready."""
    from renpy_mcp.blueprint.models import PrototypeManifest
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "pipeline_ready_active"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    game_dir = tmp_path / project_name / "game"
    entry_path = game_dir / "prototype.rpy"
    entry_path.write_text('label my_active_label:\n    "Hello"\n    return\n', encoding="utf-8")

    manifest = PrototypeManifest(
        mode="single_chapter",
        entry_label="my_active_label",
        entry_file="game/prototype.rpy",
        script_files=["game/prototype.rpy"],
        chapter_ids=["ch1"],
        updated_at="2024-01-01T00:00:00Z",
    )
    pm.write_prototype_manifest(project_name, manifest)

    (game_dir / "script.rpy").write_text(
        "label start:\n    # PROTOTYPE START (managed)\n    call my_active_label\n    return\n    # PROTOTYPE END (managed)\n",
        encoding="utf-8",
    )

    response = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
    assert response.status_code == 200
    data = response.json()

    assert data["stage"] == "prototype_ready", f"Expected prototype_ready, got {data['stage']}"


# ---------------------------------------------------------------------------
# 13. Pipeline-status returns readiness summary fields
# ---------------------------------------------------------------------------


def test_prototype_pipeline_status_includes_readiness_summary_fields(
    client: TestClient, tmp_path: Path
) -> None:
    """pipeline-status response must include key readiness summary fields from the runtime status."""
    from renpy_mcp.blueprint.models import PrototypeManifest
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "pipeline_summary_fields"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    game_dir = tmp_path / project_name / "game"
    entry_path = game_dir / "prototype.rpy"
    entry_path.write_text('label summary_label:\n    "Hello"\n    return\n', encoding="utf-8")

    manifest = PrototypeManifest(
        mode="multi_chapter",
        entry_label="summary_label",
        entry_file="game/prototype.rpy",
        script_files=["game/prototype.rpy"],
        chapter_ids=["ch1"],
        updated_at="2024-01-01T00:00:00Z",
    )
    pm.write_prototype_manifest(project_name, manifest)

    (game_dir / "script.rpy").write_text(
        "label start:\n    # PROTOTYPE START (managed)\n    call summary_label\n    return\n    # PROTOTYPE END (managed)\n",
        encoding="utf-8",
    )

    response = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
    assert response.status_code == 200
    data = response.json()

    assert "mode" in data, "pipeline-status must include mode"
    assert "is_active" in data, "pipeline-status must include is_active"
    assert "is_buildable" in data, "pipeline-status must include is_buildable"
    assert "manifest_consistent" in data, "pipeline-status must include manifest_consistent"

    assert data["mode"] == "multi_chapter"
    assert data["is_active"] is True
    assert data["is_buildable"] is True
    assert data["manifest_consistent"] is True


# ---------------------------------------------------------------------------
# 14. Candidate manifest with legacy wiring must NOT report ready
# ---------------------------------------------------------------------------


def test_prototype_pipeline_status_keeps_candidate_manifest_idle_even_when_legacy_wiring_exists(
    client: TestClient, tmp_path: Path
) -> None:
    """If a candidate manifest (mode=None) exists but old wiring is still present, pipeline-status must not report prototype_ready.

    This covers the case where:
    1. A previous active prototype left wired script.rpy + index entries
    2. Multi-chapter generate wrote a candidate manifest (mode=None)
    3. The old _has_prototype() heuristic would still return True
    4. But the readiness contract says candidate -> not ready
    """
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "pipeline_candidate_with_legacy_wiring"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    game_dir = tmp_path / project_name / "game"
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)

    # -- Step 1: simulate an old active single-chapter prototype left behind --
    # Old entry file exists and is wired
    entry_path = game_dir / "prototype_ch1_old.rpy"
    entry_path.write_text('label prototype_ch1_start:\n    "Hello"\n    return\n', encoding="utf-8")

    # script.rpy is wired to the OLD label
    (game_dir / "script.rpy").write_text(
        "label start:\n    # PROTOTYPE START (managed)\n    call prototype_ch1_start\n    return\n    # PROTOTYPE END (managed)\n",
        encoding="utf-8",
    )

    # Index has old prototype scenes
    index = {
        "scenes": {
            "old-scene": {
                "source": "prototype",
                "file_path": "game/prototype_ch1_old.rpy",
                "chapter_id": "ch1",
                "label": "prototype_ch1_start",
            }
        }
    }
    pm.write_project_index(project_name, index)

    # -- Step 2: multi-chapter generate writes candidate manifest (mode=None) --
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
    pm.write_blueprint(project_name, blueprint)

    service = PrototypeGenerationService(pm=pm, provider=None)
    service.generate_multi_chapter_scripts(project_name, blueprint)

    # Verify candidate state: manifest exists but mode=None
    manifest = pm.read_prototype_manifest(project_name)
    assert manifest is not None, "Manifest should exist after generate"
    assert manifest.mode is None, f"Expected candidate mode=None, got {manifest.mode}"

    # Verify old wiring still exists (this would fool _has_prototype())
    script_text = (game_dir / "script.rpy").read_text(encoding="utf-8")
    assert "# PROTOTYPE START (managed)" in script_text

    # -- Step 3: pipeline-status must NOT report ready --
    response = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
    assert response.status_code == 200
    data = response.json()

    assert data["stage"] != "prototype_ready", (
        f"Candidate manifest with legacy wiring should not be prototype_ready, got {data['stage']}"
    )
    assert data["stage"] == "idle", f"Expected idle for candidate manifest, got {data['stage']}"
    # has_manifest should be exposed and True even though mode=None
    assert data.get("has_manifest") is True, "has_manifest must be True when manifest file exists"


# ---------------------------------------------------------------------------
# 15. Pipeline-status returns 500 for invalid/corrupt manifest
# ---------------------------------------------------------------------------


def test_prototype_pipeline_status_returns_500_for_invalid_manifest(
    client: TestClient, tmp_path: Path
) -> None:
    """A corrupt or invalid prototype_manifest.json must result in a clear HTTP 500."""
    project_name = "pipeline_bad_manifest"
    _create_project(client, tmp_path, project_name)

    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "prototype_manifest.json").write_text("not json at all {", encoding="utf-8")

    response = client.get(f"/api/projects/{project_name}/prototype/pipeline-status")
    assert response.status_code == 500, (
        f"Expected 500 for invalid manifest, got {response.status_code}"
    )
    detail = response.json().get("detail", "")
    assert "manifest" in detail.lower(), f"Error detail should mention manifest, got: {detail}"
