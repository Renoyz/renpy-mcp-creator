"""Integration tests for prototype generation from confirmed blueprint."""

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
    """Helper to create a project with minimal game structure."""
    game_dir = tmp_path / name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")
    r = client.post("/api/projects", json={"name": name})
    assert r.status_code == 200


def _make_blueprint() -> dict:
    """Return a minimal valid blueprint dict for testing."""
    return {
        "title": "Test Prototype",
        "genre": "测试",
        "worldview": "测试世界",
        "themes": ["测试主题"],
        "target_audience": "测试用户",
        "estimated_play_time": "1小时",
        "art_style": "测试风格",
        "audio_style": "测试音乐",
        "characters": [
            {"name": "主角", "role": "主角", "personality": "勇敢", "appearance": "高大"},
            {"name": "配角", "role": "配角", "personality": "聪明", "appearance": "戴眼镜"},
        ],
        "chapters": [
            {
                "id": "ch1",
                "name": "第一章",
                "order": 1,
                "scenes": [
                    {"id": "s1", "name": "开场", "order": 1},
                    {"id": "s2", "name": "发展", "order": 2},
                ],
            },
            {
                "id": "ch2",
                "name": "第二章",
                "order": 2,
                "scenes": [
                    {"id": "s3", "name": "结局", "order": 1},
                ],
            },
        ],
    }


def _make_mock_scene_provider() -> object:
    """Return a mock LLM provider that returns structured prototype scenes as JSON."""
    scenes = [
        {
            "scene_id": "proto-ch1-s1",
            "title": "初次相遇",
            "summary": "主角在图书馆遇到配角，两人因为一本书结缘。",
            "location": "library",
            "characters_present": ["主角", "配角"],
            "entry_label": "prototype_ch1_start",
            "next_scene_id": "proto-ch1-s2",
        },
        {
            "scene_id": "proto-ch1-s2",
            "title": "深夜对话",
            "summary": "两人在闭馆后继续在咖啡厅讨论书中的哲学问题。",
            "location": "cafe",
            "characters_present": ["主角", "配角"],
            "entry_label": "prototype_ch1_scene2",
            "next_scene_id": "proto-ch1-s3",
        },
        {
            "scene_id": "proto-ch1-s3",
            "title": "分别时刻",
            "summary": "夜色渐深，两人在车站告别，约定明天再见。",
            "location": "train_station",
            "characters_present": ["主角", "配角"],
            "entry_label": "prototype_ch1_scene3",
            "next_scene_id": None,
        },
    ]

    class MockSceneProvider:
        tool_format = "anthropic"
        _call_count = 0

        def chat(self, messages, tools=None, system=None, model=None, max_tokens=1024, temperature=None):
            self._call_count += 1
            from renpy_mcp.chat_engine.providers import LLMResponse
            return LLMResponse(
                content_blocks=[{"type": "text", "text": json.dumps(scenes, ensure_ascii=False)}],
                stop_reason="end_turn",
            )

    return MockSceneProvider()


def test_select_prototype_chapter_returns_first_chapter() -> None:
    """select_prototype_chapter must return the first chapter from the blueprint."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService

    blueprint = ProjectBlueprint(**_make_blueprint())
    service = PrototypeGenerationService(pm=None, provider=None)

    chapter = service.select_prototype_chapter(blueprint)
    assert chapter.id == "ch1"
    assert chapter.name == "第一章"


def test_select_prototype_chapter_raises_when_no_chapters() -> None:
    """select_prototype_chapter must raise when blueprint has no chapters."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService

    data = _make_blueprint()
    data["chapters"] = []
    blueprint = ProjectBlueprint(**data)
    service = PrototypeGenerationService(pm=None, provider=None)

    with pytest.raises(ValueError, match="no chapters"):
        service.select_prototype_chapter(blueprint)


@pytest.mark.asyncio
async def test_generate_scenes_produces_2_to_4_structured_scenes() -> None:
    """generate_scenes must return 2-4 structured PrototypeScene objects."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=None, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    assert 2 <= len(scenes) <= 4
    for scene in scenes:
        assert scene.scene_id
        assert scene.title
        assert scene.summary
        assert scene.location
        assert isinstance(scene.characters_present, list)
        assert scene.entry_label


@pytest.mark.asyncio
async def test_write_script_uses_safe_placeholder_commands_without_assets(client: TestClient, tmp_path: Path) -> None:
    """write_script must use safe placeholders that work without any image assets."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_safe"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    script_path = service.write_script(project_name, chapter, scenes)

    full_path = tmp_path / project_name / script_path
    content = full_path.read_text(encoding="utf-8")

    # Must not use show commands without guaranteed image definitions
    assert "show " not in content, f"Must not use show commands: {content}"

    # Must use safe background
    assert "scene black" in content, "Must use safe scene black placeholder"

    # Must express location and characters via narration text
    assert "【地点：" in content, "Must include location placeholder text"
    assert "【登场角色：" in content, "Must include characters placeholder text"


@pytest.mark.asyncio
async def test_prototype_script_can_run_without_asset_references(client: TestClient, tmp_path: Path) -> None:
    """Generated prototype script must not reference any asset names that require pre-existing files."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_no_assets"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    script_path = service.write_script(project_name, chapter, scenes)

    full_path = tmp_path / project_name / script_path
    content = full_path.read_text(encoding="utf-8")

    # No scene commands referencing specific locations as image names
    for scene in scenes:
        assert f"    scene {scene.location}" not in content, f"Unsafe scene {scene.location} found"

    # No show commands
    assert "show " not in content


@pytest.mark.asyncio
async def test_wire_main_script_preserves_non_template_content(client: TestClient, tmp_path: Path) -> None:
    """wire_main_script_to_prototype must not overwrite non-template custom script.rpy content."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_preserve"
    _create_project(client, tmp_path, project_name)

    # Write custom non-template content
    custom_content = 'label start:\n    "Custom user intro."\n    "More custom logic."\n    return\n'
    script_path = tmp_path / project_name / "game" / "script.rpy"
    script_path.write_text(custom_content, encoding="utf-8")

    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    with pytest.raises(RuntimeError, match="Cannot safely wire"):
        service.wire_main_script_to_prototype(project_name, "prototype_ch1_start")

    # Verify original content is preserved
    assert script_path.read_text(encoding="utf-8") == custom_content


@pytest.mark.asyncio
async def test_wire_main_script_updates_managed_region_only(client: TestClient, tmp_path: Path) -> None:
    """When script.rpy already has a managed region, only the entry label inside it should be updated."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_managed"
    _create_project(client, tmp_path, project_name)

    # Write script with managed region
    managed_content = """label start:
    "User intro."
    # PROTOTYPE START (managed)
    call old_label
    return
    # PROTOTYPE END (managed)
    "User outro."
    return
"""
    script_path = tmp_path / project_name / "game" / "script.rpy"
    script_path.write_text(managed_content, encoding="utf-8")

    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    service.wire_main_script_to_prototype(project_name, "prototype_ch1_new")

    content = script_path.read_text(encoding="utf-8")
    assert "call prototype_ch1_new" in content
    assert "call old_label" not in content
    assert '"User intro."' in content
    assert '"User outro."' in content


@pytest.mark.asyncio
async def test_write_script_does_not_define_second_start_label(client: TestClient, tmp_path: Path) -> None:
    """write_script must NOT define label start in the prototype file (main script owns it)."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_no_start"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    script_path = service.write_script(project_name, chapter, scenes)

    # script_path is relative like "game/prototype_ch1.rpy"
    full_path = tmp_path / project_name / script_path
    assert full_path.exists(), f"Script file not found at {full_path}"

    content = full_path.read_text(encoding="utf-8")
    assert "label start:" not in content, "Prototype file must not define label start"
    for scene in scenes:
        assert f"label {scene.entry_label}:" in content


@pytest.mark.asyncio
async def test_main_script_is_wired_to_prototype_entry(client: TestClient, tmp_path: Path) -> None:
    """wire_main_script_to_prototype must rewrite game/script.rpy to call the prototype entry label."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_wire"
    _create_project(client, tmp_path, project_name)

    # Use default template content so wiring is allowed
    script_path = tmp_path / project_name / "game" / "script.rpy"
    script_path.write_text(
        'label start:\n    "Welcome to your new Ren\'Py project!"\n    return\n',
        encoding="utf-8",
    )

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    service.write_script(project_name, chapter, scenes)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)

    content = script_path.read_text(encoding="utf-8")
    assert "label start:" in content
    assert f"call {scenes[0].entry_label}" in content
    assert "return" in content
    assert "# PROTOTYPE START (managed)" in content
    assert "# PROTOTYPE END (managed)" in content


@pytest.mark.asyncio
async def test_update_index_writes_full_prototype_metadata(client: TestClient, tmp_path: Path) -> None:
    """update_index must write full prototype scene metadata including title, summary, location, next_scene_id, source."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_index"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    script_path = service.write_script(project_name, chapter, scenes)
    service.update_index(project_name, chapter, scenes, script_path)

    index_path = tmp_path / project_name / "meta" / "index.json"
    assert index_path.exists(), f"Index file not found at {index_path}"

    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert "scenes" in index
    for scene in scenes:
        mapping = index["scenes"].get(scene.scene_id)
        assert mapping is not None, f"Scene {scene.scene_id} missing from index"
        assert mapping["chapter_id"] == chapter.id
        assert mapping["scene_id"] == scene.scene_id
        assert mapping["title"] == scene.title
        assert mapping["summary"] == scene.summary
        assert mapping["location"] == scene.location
        assert mapping.get("next_scene_id") == scene.next_scene_id
        assert mapping["label"] == scene.entry_label
        assert mapping["file_path"] == script_path
        assert mapping["source"] == "prototype"


@pytest.mark.asyncio
async def test_commit_prototype_replacement_removes_old_artifacts(client: TestClient, tmp_path: Path) -> None:
    """commit_prototype_replacement must remove old prototype files and index entries, keeping only the new set."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_commit"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    # Seed old prototype artifacts
    old_index = {
        "scenes": {
            "old-s1": {
                "chapter_id": "ch1",
                "scene_id": "old-s1",
                "title": "Old Scene",
                "summary": "Old.",
                "location": "old_place",
                "next_scene_id": None,
                "label": "old_start",
                "file_path": "game/prototype_old.rpy",
                "source": "prototype",
                "order": 1,
            }
        }
    }
    pm.write_project_index(project_name, old_index)
    old_file = tmp_path / project_name / "game" / "prototype_old.rpy"
    old_file.write_text("label old_start:\n    return\n", encoding="utf-8")

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    new_script_path = service.write_script(project_name, chapter, scenes)
    service.update_index(project_name, chapter, scenes, new_script_path)

    new_scene_ids = [s.scene_id for s in scenes]

    # Commit: this should remove old artifacts
    service.commit_prototype_replacement(project_name, new_scene_ids, new_script_path)

    # Old file must be gone
    assert not old_file.exists(), "Old prototype file should have been removed after commit"

    # Old index entry must be gone
    index = pm.read_project_index(project_name)
    assert "old-s1" not in index.get("scenes", {}), "Old prototype index entry should be removed after commit"

    # New entries must still exist
    for sid in new_scene_ids:
        assert sid in index.get("scenes", {}), f"New scene {sid} should survive commit"


@pytest.mark.asyncio
async def test_failed_regeneration_preserves_previous_prototype_artifacts(client: TestClient, tmp_path: Path) -> None:
    """If a new prototype generation fails, the previous stable prototype must remain intact."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_preserve_old"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    # Seed an old stable prototype
    old_index = {
        "scenes": {
            "old-s1": {
                "chapter_id": "ch1",
                "scene_id": "old-s1",
                "title": "Old Scene",
                "summary": "Old stable scene.",
                "location": "old_place",
                "next_scene_id": None,
                "label": "old_start",
                "file_path": "game/prototype_old.rpy",
                "source": "prototype",
                "order": 1,
            }
        }
    }
    pm.write_project_index(project_name, old_index)
    old_file = tmp_path / project_name / "game" / "prototype_old.rpy"
    old_file.write_text("label old_start:\n    return\n", encoding="utf-8")
    script_path = tmp_path / project_name / "game" / "script.rpy"
    script_path.write_text(
        'label start:\n    "Hello from the Ren\'Py MCP server!"\n    call old_start\n    return\n',
        encoding="utf-8",
    )

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    new_script_path = service.write_script(project_name, chapter, scenes)
    new_scene_ids = [s.scene_id for s in scenes]
    old_script_content = service.backup_main_script(project_name)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)

    # Simulate failure after wire
    def failing_update(*args, **kwargs):
        raise RuntimeError("Simulated index failure")
    service.update_index = failing_update

    try:
        service.update_index(project_name, chapter, scenes, new_script_path)
    except RuntimeError:
        # Rollback as chat_ws.py would do
        service.rollback_prototype_generation(
            project_name, new_script_path, new_scene_ids, old_script_content
        )

    # Old prototype file must survive
    assert old_file.exists(), "Old prototype file should have been preserved"

    # Old index entries must survive
    index = pm.read_project_index(project_name)
    assert "old-s1" in index.get("scenes", {}), "Old prototype index entry should be preserved"

    # Old main script must be restored
    content = script_path.read_text(encoding="utf-8")
    assert "call old_start" in content, "Main script should be restored to old entry"
    assert "call prototype_ch1_start" not in content, "New entry label should not remain"

    # New script file must be gone
    assert not (tmp_path / project_name / new_script_path).exists(), "New script artifact should have been removed"


@pytest.mark.asyncio
async def test_post_wire_failure_restores_main_script_content(client: TestClient, tmp_path: Path) -> None:
    """If update_index fails after wire_main_script_to_prototype, script.rpy must be restored."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_restore_script"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    # Start with a main script that has a managed region
    script_path = tmp_path / project_name / "game" / "script.rpy"
    original_content = """label start:
    "Hello from the Ren'Py MCP server!"
    # PROTOTYPE START (managed)
    call old_start
    return
    # PROTOTYPE END (managed)
"""
    script_path.write_text(original_content, encoding="utf-8")

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    new_script_path = service.write_script(project_name, chapter, scenes)
    new_scene_ids = [s.scene_id for s in scenes]
    old_script_content = service.backup_main_script(project_name)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)

    # Simulate post-wire failure
    def failing_update(*args, **kwargs):
        raise RuntimeError("Simulated index failure")
    service.update_index = failing_update

    try:
        service.update_index(project_name, chapter, scenes, new_script_path)
    except RuntimeError:
        service.rollback_prototype_generation(
            project_name, new_script_path, new_scene_ids, old_script_content
        )

    # script.rpy must be restored exactly
    restored = script_path.read_text(encoding="utf-8")
    assert restored == original_content, f"script.rpy was not restored. Got: {restored}"


@pytest.mark.asyncio
async def test_successful_regeneration_replaces_previous_prototype_only_after_commit(client: TestClient, tmp_path: Path) -> None:
    """After successful commit, only the new prototype should remain; old should be gone."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_staged"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    # Seed old prototype
    old_index = {
        "scenes": {
            "old-s1": {
                "chapter_id": "ch1",
                "scene_id": "old-s1",
                "title": "Old Scene",
                "summary": "Old.",
                "location": "old_place",
                "next_scene_id": None,
                "label": "old_start",
                "file_path": "game/prototype_old.rpy",
                "source": "prototype",
                "order": 1,
            }
        }
    }
    pm.write_project_index(project_name, old_index)
    old_file = tmp_path / project_name / "game" / "prototype_old.rpy"
    old_file.write_text("label old_start:\n    return\n", encoding="utf-8")

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    new_script_path = service.write_script(project_name, chapter, scenes)
    new_scene_ids = [s.scene_id for s in scenes]
    old_script_content = service.backup_main_script(project_name)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)
    service.update_index(project_name, chapter, scenes, new_script_path)

    # Before commit, old prototype should still exist
    index_before = pm.read_project_index(project_name)
    assert "old-s1" in index_before.get("scenes", {}), "Old prototype should exist before commit"
    assert old_file.exists(), "Old prototype file should exist before commit"

    # Commit
    service.commit_prototype_replacement(project_name, new_scene_ids, new_script_path)

    # After commit, old should be gone and new should remain
    index_after = pm.read_project_index(project_name)
    assert "old-s1" not in index_after.get("scenes", {}), "Old prototype should be removed after commit"
    assert not old_file.exists(), "Old prototype file should be removed after commit"
    for sid in new_scene_ids:
        assert sid in index_after.get("scenes", {}), f"New scene {sid} should remain after commit"


@pytest.mark.asyncio
async def test_failed_regeneration_with_same_final_path_preserves_previous_prototype_file(client: TestClient, tmp_path: Path) -> None:
    """When the new prototype uses the same final path as the old one, failure must not destroy the old stable file."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_same_path"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    # Seed an old stable prototype at the SAME final path that the new one will use
    blueprint = ProjectBlueprint(**_make_blueprint())
    chapter = blueprint.chapters[0]
    safe_name = "".join(c if c.isalnum() else "_" for c in chapter.name)
    final_file_name = f"prototype_{chapter.id}_{safe_name}.rpy"
    final_file = tmp_path / project_name / "game" / final_file_name
    final_file.write_text("label old_stable:\n    return\n", encoding="utf-8")

    old_index = {
        "scenes": {
            "old-s1": {
                "chapter_id": chapter.id,
                "scene_id": "old-s1",
                "title": "Old",
                "summary": "Old.",
                "location": "old",
                "next_scene_id": None,
                "label": "old_stable",
                "file_path": f"game/{final_file_name}",
                "source": "prototype",
                "order": 1,
            }
        }
    }
    pm.write_project_index(project_name, old_index)

    script_file = tmp_path / project_name / "game" / "script.rpy"
    script_file.write_text(
        'label start:\n    "Hello from the Ren\'Py MCP server!"\n    call old_stable\n    return\n',
        encoding="utf-8",
    )

    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    scenes = await service.generate_scenes(chapter, blueprint)
    staging_path = service.write_script(project_name, chapter, scenes)
    new_scene_ids = [s.scene_id for s in scenes]
    old_script_content = service.backup_main_script(project_name)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)

    # Simulate post-wire failure
    def failing_update(*args, **kwargs):
        raise RuntimeError("Simulated index failure")
    service.update_index = failing_update

    try:
        service.update_index(project_name, chapter, scenes, staging_path)
    except RuntimeError:
        service.rollback_prototype_generation(
            project_name, staging_path, new_scene_ids, old_script_content
        )

    # Old stable final file MUST still exist with its original content
    assert final_file.exists(), "Old stable prototype file should have been preserved"
    assert "label old_stable:" in final_file.read_text(encoding="utf-8")

    # Staging file must be gone
    staging_file = tmp_path / project_name / staging_path
    assert not staging_file.exists(), "Staging file should have been removed"

    # Old index entry must survive
    index = pm.read_project_index(project_name)
    assert "old-s1" in index.get("scenes", {})

    # Main script restored
    assert "call old_stable" in script_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_successful_regeneration_promotes_staging_script_to_final_path(client: TestClient, tmp_path: Path) -> None:
    """After commit, the staging file must be promoted to the final path."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_promote"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    staging_path = service.write_script(project_name, chapter, scenes)
    new_scene_ids = [s.scene_id for s in scenes]

    # Before commit: staging exists, final does not
    staging_file = tmp_path / project_name / staging_path
    final_path = service._final_path_from_staging(staging_path)
    final_file = tmp_path / project_name / final_path
    assert staging_file.exists(), "Staging file should exist before commit"
    assert not final_file.exists(), "Final file should not exist before commit"

    service.commit_prototype_replacement(project_name, new_scene_ids, staging_path)

    # After commit: staging gone, final exists
    assert not staging_file.exists(), "Staging file should be gone after commit"
    assert final_file.exists(), "Final file should exist after commit"
    assert "label prototype_ch1_start:" in final_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_rollback_removes_only_staging_script_not_stable_final_script(client: TestClient, tmp_path: Path) -> None:
    """rollback_prototype_generation must delete the staging file but never a stable final prototype file."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_rollback_staging"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    blueprint = ProjectBlueprint(**_make_blueprint())
    chapter = blueprint.chapters[0]
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    scenes = await service.generate_scenes(chapter, blueprint)
    staging_path = service.write_script(project_name, chapter, scenes)
    new_scene_ids = [s.scene_id for s in scenes]

    final_path = service._final_path_from_staging(staging_path)
    final_file = tmp_path / project_name / final_path
    # Simulate a pre-existing stable final file at the same path
    final_file.write_text("label stable:\n    return\n", encoding="utf-8")

    service.rollback_prototype_generation(project_name, staging_path, new_scene_ids, None)

    # Staging file must be gone
    staging_file = tmp_path / project_name / staging_path
    assert not staging_file.exists(), "Staging file should be removed by rollback"

    # Stable final file must survive
    assert final_file.exists(), "Stable final prototype file should NOT be removed by rollback"
    assert "label stable:" in final_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_service_failure_does_not_corrupt_project(client: TestClient, tmp_path: Path) -> None:
    """If prototype generation fails, the project must not be left with partial script or corrupt index."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_fail"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())

    class ExplodingProvider:
        tool_format = "anthropic"

        def chat(self, messages, tools=None, system=None, model=None, max_tokens=1024, temperature=None):
            raise RuntimeError("Simulated provider failure")

    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=ExplodingProvider())

    chapter = blueprint.chapters[0]

    with pytest.raises(RuntimeError):
        await service.generate_scenes(chapter, blueprint)

    # No partial files should be left
    game_dir = tmp_path / project_name / "game"
    proto_files = list(game_dir.glob("prototype*"))
    assert len(proto_files) == 0, f"Unexpected partial files: {proto_files}"

    index_path = tmp_path / project_name / "meta" / "index.json"
    # Index may or may not exist from project creation; if it does, it should not contain prototype scenes
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for scene_id in ("proto-ch1-s1", "proto-ch1-s2", "proto-ch1-s3"):
            assert scene_id not in index.get("scenes", {}), f"Partial scene {scene_id} leaked into index"
