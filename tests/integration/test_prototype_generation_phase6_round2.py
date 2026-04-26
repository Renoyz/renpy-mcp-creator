"""Phase 6 Round 2: Multi-chapter script generation + workspace readability."""

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
                        "entry_label": "prototype_ch1_scene_2",
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
                        "entry_label": "prototype_ch2_scene_2",
                        "next_scene_id": None,
                        "scene_order": 2,
                    },
                ],
            },
        ]
    }


# ---------------------------------------------------------------------------
# 1. Multi-chapter script files written
# ---------------------------------------------------------------------------


def test_generate_multi_chapter_scripts_writes_one_rpy_per_chapter(
    client: TestClient, tmp_path: Path
) -> None:
    """generate_multi_chapter_scripts must write one .rpy file per chapter."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "multi_chapter_scripts"
    _create_project(client, tmp_path, project_name)

    # Write scene_packages.json directly
    scene_packages = _make_scene_packages()
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Write blueprint
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

    ch1_file = tmp_path / project_name / "game" / "prototype_ch1_Chapter1.rpy"
    ch2_file = tmp_path / project_name / "game" / "prototype_ch2_Chapter2.rpy"
    assert ch1_file.exists(), f"Chapter 1 script must exist at {ch1_file}"
    assert ch2_file.exists(), f"Chapter 2 script must exist at {ch2_file}"


# ---------------------------------------------------------------------------
# 2. Scene chaining correct
# ---------------------------------------------------------------------------


def test_multi_chapter_scripts_chain_scenes_and_jump_to_next_chapter(
    client: TestClient, tmp_path: Path
) -> None:
    """Chapter scripts must chain scenes internally and jump to next chapter start."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "chain_scenes"
    _create_project(client, tmp_path, project_name)

    scene_packages = _make_scene_packages()
    meta_dir = tmp_path / project_name / "meta"
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

    ch1_content = (tmp_path / project_name / "game" / "prototype_ch1_Chapter1.rpy").read_text(encoding="utf-8")
    ch2_content = (tmp_path / project_name / "game" / "prototype_ch2_Chapter2.rpy").read_text(encoding="utf-8")

    # ch1: scene1 jumps to scene2; scene2 jumps to ch2 start
    assert "jump prototype_ch1_scene_2" in ch1_content, "ch1 scene1 must jump to ch1 scene2"
    assert "jump prototype_ch2_start" in ch1_content, "ch1 last scene must jump to ch2 start"
    assert "return" not in ch1_content.split("jump prototype_ch2_start")[-1].split("\n")[0], (
        "ch1 should not return before jumping to ch2"
    )

    # ch2: last scene returns
    assert "return" in ch2_content, "ch2 last scene must return"


# ---------------------------------------------------------------------------
# 3. Index mapping correct
# ---------------------------------------------------------------------------


def test_multi_chapter_index_maps_scene_ids_to_correct_file_and_label(
    client: TestClient, tmp_path: Path
) -> None:
    """index.json must map each scene to its correct chapter script and label."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "multi_chapter_index"
    _create_project(client, tmp_path, project_name)

    scene_packages = _make_scene_packages()
    meta_dir = tmp_path / project_name / "meta"
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

    index = json.loads((meta_dir / "index.json").read_text(encoding="utf-8"))
    scenes = index.get("scenes", {})

    # All 4 scenes must be present
    assert "s1" in scenes
    assert "s2" in scenes
    assert "s3" in scenes
    assert "s4" in scenes

    # s1, s2 point to ch1 script
    assert scenes["s1"]["file_path"] == "game/prototype_ch1_Chapter1.rpy"
    assert scenes["s1"]["label"] == "prototype_ch1_start"
    assert scenes["s2"]["file_path"] == "game/prototype_ch1_Chapter1.rpy"
    assert scenes["s2"]["label"] == "prototype_ch1_scene_2"

    # s3, s4 point to ch2 script
    assert scenes["s3"]["file_path"] == "game/prototype_ch2_Chapter2.rpy"
    assert scenes["s3"]["label"] == "prototype_ch2_start"
    assert scenes["s4"]["file_path"] == "game/prototype_ch2_Chapter2.rpy"
    assert scenes["s4"]["label"] == "prototype_ch2_scene_2"

    # All marked as prototype
    for sid in ("s1", "s2", "s3", "s4"):
        assert scenes[sid]["source"] == "prototype"
        assert scenes[sid]["chapter_id"] in ("ch1", "ch2")


# ---------------------------------------------------------------------------
# 4. Scene script API readable for multi-chapter
# ---------------------------------------------------------------------------


def test_scene_script_api_reads_correct_chapter_script_for_multi_chapter_scene(
    client: TestClient, tmp_path: Path
) -> None:
    """GET /scenes/{scene_id}/script must return the correct chapter script for multi-chapter scenes."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "api_multi_chapter_script"
    _create_project(client, tmp_path, project_name)

    scene_packages = _make_scene_packages()
    meta_dir = tmp_path / project_name / "meta"
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

    # Request ch2 scene script via API
    response = client.get(f"/api/projects/{project_name}/scenes/s4/script")
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert "prototype_ch2_scene_2" in data["content"], "API must return ch2 script content"
    assert data["file_path"] == "game/prototype_ch2_Chapter2.rpy"

    # Request ch1 scene script via API
    response = client.get(f"/api/projects/{project_name}/scenes/s1/script")
    assert response.status_code == 200
    data = response.json()
    assert "prototype_ch1_start" in data["content"], "API must return ch1 script content"
    assert data["file_path"] == "game/prototype_ch1_Chapter1.rpy"


# ---------------------------------------------------------------------------
# 5. Phase 5 single-chapter pipeline not broken
# ---------------------------------------------------------------------------


def test_single_chapter_prototype_pipeline_still_uses_existing_entrypoint(
    client: TestClient, tmp_path: Path
) -> None:
    """The existing single-chapter confirmation pipeline must still produce a working prototype."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "single_chapter_not_broken"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(
        title="Test Single",
        genre="Test",
        worldview="Test",
        themes=["test"],
        characters=[
            {"name": "Alice", "role": "Protagonist", "personality": "brave", "appearance": "tall"},
        ],
        chapters=[
            {
                "id": "ch1",
                "name": "Chapter1",
                "order": 1,
                "scenes": [
                    {"id": "s1", "name": "Scene1", "order": 1},
                ],
            },
        ],
    )
    pm = ProjectManager(get_settings())
    pm.write_blueprint(project_name, blueprint)

    service = PrototypeGenerationService(pm=pm, provider=None)
    chapter = service.select_prototype_chapter(blueprint)

    # Manually create a scene (simulating generate_scenes output)
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

    # Run the existing single-chapter pipeline
    staging_path = service.write_script(project_name, chapter, scenes)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)
    service.update_index(project_name, chapter, scenes, staging_path)
    service.commit_prototype_replacement(project_name, [s.scene_id for s in scenes], staging_path)

    # Verify script.rpy is wired correctly
    script_path = tmp_path / project_name / "game" / "script.rpy"
    assert script_path.exists()
    content = script_path.read_text(encoding="utf-8")
    assert "call prototype_ch1_start" in content

    # Verify index has the scene
    index_path = tmp_path / project_name / "meta" / "index.json"
    assert index_path.exists()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert "proto-s1" in index.get("scenes", {})


# ---------------------------------------------------------------------------
# 6. Product-level API entry point
# ---------------------------------------------------------------------------


def test_multi_chapter_generate_api_persists_scripts_and_index(
    client: TestClient, tmp_path: Path
) -> None:
    """POST /api/projects/{name}/prototype/multi-chapter/generate must trigger multi-chapter script generation."""
    project_name = "multi_chapter_api"
    _create_project(client, tmp_path, project_name)

    # Write scene_packages and blueprint
    scene_packages = _make_scene_packages()
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

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

    response = client.post(f"/api/projects/{project_name}/prototype/multi-chapter/generate")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("success") is True
    assert "chapters" in data
    assert len(data["chapters"]) == 2

    # Verify files on disk
    ch1_file = tmp_path / project_name / "game" / "prototype_ch1_Chapter1.rpy"
    ch2_file = tmp_path / project_name / "game" / "prototype_ch2_Chapter2.rpy"
    assert ch1_file.exists()
    assert ch2_file.exists()

    # Verify index
    index = json.loads((meta_dir / "index.json").read_text(encoding="utf-8"))
    assert len(index.get("scenes", {})) == 4

# ---------------------------------------------------------------------------
# 7. Transaction rollback
# ---------------------------------------------------------------------------


def test_generate_multi_chapter_scripts_rolls_back_when_wiring_main_script_fails(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If commit fails (e.g. wire_main_script_to_prototype), old state is restored."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "rollback_test"
    _create_project(client, tmp_path, project_name)

    game_dir = tmp_path / project_name / "game"
    meta_dir = tmp_path / project_name / "meta"

    # Old stable state
    old_script = 'label start:\n    "Old script"\n    return\n'
    (game_dir / "script.rpy").write_text(old_script, encoding="utf-8")

    old_index = {"scenes": {"old_scene": {"source": "prototype", "title": "Old"}}}
    (meta_dir / "index.json").write_text(json.dumps(old_index), encoding="utf-8")

    old_proto = game_dir / "prototype_ch1_Old.rpy"
    old_proto.write_text("label old_start:\n    return\n", encoding="utf-8")

    # Scene packages
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

    def _fail_index(*args, **kwargs):
        raise RuntimeError("Simulated index write failure")

    monkeypatch.setattr(pm, "write_project_index", _fail_index)

    with pytest.raises(RuntimeError, match="Simulated index write failure"):
        asyncio.run(service.generate_multi_chapter_scripts(project_name, blueprint))

    # Old script untouched (generate no longer wires script.rpy)
    assert (game_dir / "script.rpy").read_text(encoding="utf-8") == old_script

    # Old index restored
    index = json.loads((meta_dir / "index.json").read_text(encoding="utf-8"))
    assert "old_scene" in index.get("scenes", {})
    assert "s1" not in index.get("scenes", {})

    # No new chapter files left behind
    assert not (game_dir / "prototype_ch1_Chapter1.rpy").exists()
    assert not (game_dir / "prototype_ch2_Chapter2.rpy").exists()

    # Old prototype file still present
    assert old_proto.exists()


# ---------------------------------------------------------------------------
# 8. Stale prototype index entries removed on re-generation
# ---------------------------------------------------------------------------


def test_generate_multi_chapter_scripts_removes_stale_prototype_index_entries(
    client: TestClient, tmp_path: Path
) -> None:
    """Re-generation removes old prototype scenes that are no longer present."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "stale_index"
    _create_project(client, tmp_path, project_name)

    meta_dir = tmp_path / project_name / "meta"
    game_dir = tmp_path / project_name / "game"

    # Old index with extra prototype scenes
    old_index = {
        "scenes": {
            "s1": {"source": "prototype", "title": "Keep1"},
            "s2": {"source": "prototype", "title": "Keep2"},
            "s_old1": {"source": "prototype", "title": "Stale1"},
            "s_old2": {"source": "prototype", "title": "Stale2"},
            "non_proto": {"source": "user", "title": "UserScene"},
        }
    }
    (meta_dir / "index.json").write_text(json.dumps(old_index), encoding="utf-8")

    # Old prototype file
    (game_dir / "prototype_ch1_Chapter1.rpy").write_text("old", encoding="utf-8")

    # Only s1 and s2 in new scene packages
    scene_packages = {
        "chapters": [
            {
                "chapter_id": "ch1",
                "chapter_name": "Chapter1",
                "chapter_order": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "title": "Opening",
                        "summary": "Open",
                        "location": "classroom",
                        "location_visual_brief": "",
                        "mood": "calm",
                        "characters_present": ["Alice"],
                        "dialogue_beats": [
                            {"speaker": "Alice", "intent": "intro", "content_brief": "Hi", "spoken_line": "Hi"}
                        ],
                        "entry_label": "prototype_ch1_start",
                        "next_scene_id": "s2",
                        "scene_order": 1,
                    },
                    {
                        "scene_id": "s2",
                        "title": "End",
                        "summary": "End",
                        "location": "hallway",
                        "location_visual_brief": "",
                        "mood": "calm",
                        "characters_present": ["Alice"],
                        "dialogue_beats": [
                            {"speaker": "Alice", "intent": "out", "content_brief": "Bye", "spoken_line": "Bye"}
                        ],
                        "entry_label": "prototype_ch1_scene_2",
                        "next_scene_id": None,
                        "scene_order": 2,
                    },
                ],
            },
        ]
    }
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
        ],
        chapters=[
            {"id": "ch1", "name": "Chapter1", "order": 1, "scenes": []},
        ],
    )
    pm = ProjectManager(get_settings())
    pm.write_blueprint(project_name, blueprint)

    service = PrototypeGenerationService(pm=pm, provider=None)
    asyncio.run(service.generate_multi_chapter_scripts(project_name, blueprint))

    index = json.loads((meta_dir / "index.json").read_text(encoding="utf-8"))
    scenes = index.get("scenes", {})

    assert "s1" in scenes
    assert "s2" in scenes
    assert "s_old1" not in scenes
    assert "s_old2" not in scenes
    assert "non_proto" in scenes


# ---------------------------------------------------------------------------
# 9. Stale prototype files removed on re-generation
# ---------------------------------------------------------------------------


def test_generate_multi_chapter_scripts_removes_stale_prototype_files(
    client: TestClient, tmp_path: Path
) -> None:
    """Re-generation removes old prototype chapter files not in the new set."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "stale_files"
    _create_project(client, tmp_path, project_name)

    meta_dir = tmp_path / project_name / "meta"
    game_dir = tmp_path / project_name / "game"

    # Old prototype files from previous generation
    (game_dir / "prototype_ch1_Chapter1.rpy").write_text("old ch1", encoding="utf-8")
    (game_dir / "prototype_ch2_Chapter2.rpy").write_text("old ch2", encoding="utf-8")
    (game_dir / "prototype_ch3_Chapter3.rpy").write_text("old ch3", encoding="utf-8")
    # Non-prototype file must not be touched
    (game_dir / "custom.rpy").write_text("custom", encoding="utf-8")

    # New scene packages has only ch1 and ch2
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
    asyncio.run(service.generate_multi_chapter_scripts(project_name, blueprint))

    # Current files regenerated
    assert (game_dir / "prototype_ch1_Chapter1.rpy").exists()
    ch1_content = (game_dir / "prototype_ch1_Chapter1.rpy").read_text(encoding="utf-8")
    assert "prototype_ch1_start" in ch1_content, "ch1 should contain new generated content"

    assert (game_dir / "prototype_ch2_Chapter2.rpy").exists()

    # Stale ch3 removed
    assert not (game_dir / "prototype_ch3_Chapter3.rpy").exists()

    # Non-prototype preserved
    assert (game_dir / "custom.rpy").exists()
    assert (game_dir / "custom.rpy").read_text(encoding="utf-8") == "custom"

# ---------------------------------------------------------------------------
# 10. Same-name regeneration restores old stable files on rollback
# ---------------------------------------------------------------------------


def test_generate_multi_chapter_scripts_restores_old_same_named_prototype_files_on_commit_failure(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If commit fails after promoting over existing same-name files, old content is restored."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "same_name_rollback"
    _create_project(client, tmp_path, project_name)

    game_dir = tmp_path / project_name / "game"
    meta_dir = tmp_path / project_name / "meta"

    # Old stable script.rpy
    old_script = 'label start:\n    "Old script"\n    return\n'
    (game_dir / "script.rpy").write_text(old_script, encoding="utf-8")

    # Old stable index
    old_index = {"scenes": {"old_scene": {"source": "prototype", "title": "Old"}}}
    (meta_dir / "index.json").write_text(json.dumps(old_index), encoding="utf-8")

    # Old stable prototype files with SAME NAMES as the new generation
    old_ch1_content = "label old_ch1_start:\n    \"Old ch1 stable\"\n    return\n"
    old_ch2_content = "label old_ch2_start:\n    \"Old ch2 stable\"\n    return\n"
    (game_dir / "prototype_ch1_Chapter1.rpy").write_text(old_ch1_content, encoding="utf-8")
    (game_dir / "prototype_ch2_Chapter2.rpy").write_text(old_ch2_content, encoding="utf-8")

    # Scene packages (will generate same-named files)
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

    def _fail_index(*args, **kwargs):
        raise RuntimeError("Simulated index write failure")

    monkeypatch.setattr(pm, "write_project_index", _fail_index)

    with pytest.raises(RuntimeError, match="Simulated index write failure"):
        asyncio.run(service.generate_multi_chapter_scripts(project_name, blueprint))

    # Old script untouched (generate no longer wires script.rpy)
    assert (game_dir / "script.rpy").read_text(encoding="utf-8") == old_script

    # Old index restored
    index = json.loads((meta_dir / "index.json").read_text(encoding="utf-8"))
    assert "old_scene" in index.get("scenes", {})
    assert "s1" not in index.get("scenes", {})

    # Old SAME-NAME prototype files RESTORED (key assertion)
    assert (game_dir / "prototype_ch1_Chapter1.rpy").exists()
    assert (game_dir / "prototype_ch1_Chapter1.rpy").read_text(encoding="utf-8") == old_ch1_content

    assert (game_dir / "prototype_ch2_Chapter2.rpy").exists()
    assert (game_dir / "prototype_ch2_Chapter2.rpy").read_text(encoding="utf-8") == old_ch2_content


def test_multi_chapter_promotion_never_unlinks_final_files_before_replace_succeeds(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If staging->final promotion fails, old final files must never be unlinked first.

    The promotion step must atomically replace the destination, not unlink-then-rename.
    An unlink-before-rename creates a data-loss window where both files are gone if
    the rename fails or the process crashes between the two operations.
    """
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "no_unlink_before_promote"
    _create_project(client, tmp_path, project_name)

    game_dir = tmp_path / project_name / "game"
    meta_dir = tmp_path / project_name / "meta"

    # Seed old stable prototype files with known content (same names new gen will use)
    old_ch1_content = "label old_ch1_start:\n    \"Old stable chapter 1\"\n    return\n"
    old_ch2_content = "label old_ch2_start:\n    \"Old stable chapter 2\"\n    return\n"
    (game_dir / "prototype_ch1_Chapter1.rpy").write_text(old_ch1_content, encoding="utf-8")
    (game_dir / "prototype_ch2_Chapter2.rpy").write_text(old_ch2_content, encoding="utf-8")

    old_index = {"scenes": {"old_scene": {"source": "prototype", "title": "Old"}}}
    (meta_dir / "index.json").write_text(json.dumps(old_index), encoding="utf-8")

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

    # Track prototype .rpy files that get unlinked
    unlinked_prototype_files: list[str] = []
    _original_unlink = Path.unlink

    def _track_unlink(self):
        # Only track final prototype files, not staging or backup files
        if self.suffix == ".rpy" and "prototype" in self.name and ".__staging__" not in str(self) and ".__backup__" not in str(self):
            unlinked_prototype_files.append(str(self))
        return _original_unlink(self)

    monkeypatch.setattr(Path, "unlink", _track_unlink)

    # Force replace to fail, simulating a disk-full scenario
    def _fail_replace(self, target):
        raise OSError("Simulated replace failure during promotion")

    monkeypatch.setattr(Path, "replace", _fail_replace)

    # generate_multi_chapter_scripts should raise because replace fails
    with pytest.raises(OSError, match="Simulated replace failure"):
        asyncio.run(service.generate_multi_chapter_scripts(project_name, blueprint))

    # KEY ASSERTION: no prototype .rpy file should have been unlinked.
    # The promotion step uses atomic replace, not unlink-then-rename.
    assert len(unlinked_prototype_files) == 0, (
        f"Prototype files were unlinked during failed promotion: {unlinked_prototype_files}. "
        "Path.replace() must be used instead of unlink()+rename() to avoid data-loss window."
    )
