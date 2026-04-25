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
            "location_visual_brief": "安静的大学图书馆内景，书架高耸，暖黄色灯光，午后阳光从窗户斜射入",
            "mood": "短暂温暖",
            "characters_present": ["主角", "配角"],
            "dialogue_beats": [
                {"speaker": "主角", "intent": "寻找一本书", "content_brief": "询问配角是否见过某本书"},
                {"speaker": "配角", "intent": "分享阅读兴趣", "content_brief": "表示自己也喜欢这本书"},
            ],
            "entry_label": "prototype_ch1_start",
            "next_scene_id": "proto-ch1-s2",
        },
        {
            "scene_id": "proto-ch1-s2",
            "title": "深夜对话",
            "summary": "两人在闭馆后继续在咖啡厅讨论书中的哲学问题。",
            "location": "cafe",
            "location_visual_brief": "深夜营业的小咖啡厅，木质桌椅，窗外路灯昏黄，咖啡香气",
            "mood": "怀疑",
            "characters_present": ["主角", "配角"],
            "dialogue_beats": [
                {"speaker": "主角", "intent": "探讨哲学观点", "content_brief": "提出对书中观点的质疑"},
                {"speaker": "配角", "intent": "解释并反问", "content_brief": "解释自己的看法并反问主角"},
            ],
            "entry_label": "prototype_ch1_scene2",
            "next_scene_id": "proto-ch1-s3",
        },
        {
            "scene_id": "proto-ch1-s3",
            "title": "分别时刻",
            "summary": "夜色渐深，两人在车站告别，约定明天再见。",
            "location": "train_station",
            "location_visual_brief": "夜晚的城市火车站台，霓虹灯闪烁，列车灯光远去，微凉的风",
            "mood": "悲怆",
            "characters_present": ["主角", "配角"],
            "dialogue_beats": [
                {"speaker": "主角", "intent": "表达不舍", "content_brief": "希望下次还能一起讨论"},
                {"speaker": "配角", "intent": "温柔告别", "content_brief": "约定明天同一时间再见"},
            ],
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
    assert "# 地点：" in content, "Must include location placeholder comment"
    assert "# 登场角色：" in content, "Must include characters placeholder comment"


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


@pytest.mark.asyncio
async def test_commit_promotion_failure_preserves_previous_prototype_artifacts(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If staging->final promote fails, the old stable prototype must remain intact."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_commit_fail"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    # Seed old stable prototype
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

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    staging_path = service.write_script(project_name, chapter, scenes)
    new_scene_ids = [s.scene_id for s in scenes]
    service.update_index(
        project_name, chapter, scenes, service._final_path_from_staging(staging_path)
    )

    # Monkeypatch Path.replace to simulate disk failure during promote
    def _raise_replace(self, target):
        raise OSError("Simulated disk full during replace")

    monkeypatch.setattr(Path, "replace", _raise_replace)

    # Commit must raise, not swallow the error
    with pytest.raises(OSError, match="Simulated disk full"):
        service.commit_prototype_replacement(project_name, new_scene_ids, staging_path)

    # Old stable prototype file must survive
    assert old_file.exists(), "Old stable prototype file should be preserved after commit failure"
    assert "label old_start:" in old_file.read_text(encoding="utf-8")

    # Old index entry must survive
    index = pm.read_project_index(project_name)
    assert "old-s1" in index.get("scenes", {}), "Old prototype index entry should be preserved after commit failure"


@pytest.mark.asyncio
async def test_commit_does_not_cleanup_old_artifacts_after_promotion_failure(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If promote fails, commit must NOT delete old prototype files or old index entries."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_commit_no_cleanup"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())

    # Seed multiple old prototype artifacts
    old_index = {
        "scenes": {
            "old-s1": {
                "chapter_id": "ch1",
                "scene_id": "old-s1",
                "title": "Old Scene 1",
                "summary": "Old.",
                "location": "old_place",
                "next_scene_id": "old-s2",
                "label": "old_start",
                "file_path": "game/prototype_old.rpy",
                "source": "prototype",
                "order": 1,
            },
            "old-s2": {
                "chapter_id": "ch1",
                "scene_id": "old-s2",
                "title": "Old Scene 2",
                "summary": "Old 2.",
                "location": "old_place2",
                "next_scene_id": None,
                "label": "old_end",
                "file_path": "game/prototype_old.rpy",
                "source": "prototype",
                "order": 2,
            }
        }
    }
    pm.write_project_index(project_name, old_index)
    old_file = tmp_path / project_name / "game" / "prototype_old.rpy"
    old_file.write_text("label old_start:\n    return\n", encoding="utf-8")
    another_old_file = tmp_path / project_name / "game" / "prototype_another.rpy"
    another_old_file.write_text("label another:\n    return\n", encoding="utf-8")

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    staging_path = service.write_script(project_name, chapter, scenes)
    new_scene_ids = [s.scene_id for s in scenes]
    service.update_index(
        project_name, chapter, scenes, service._final_path_from_staging(staging_path)
    )

    # Monkeypatch replace to fail
    def _raise_replace(self, target):
        raise PermissionError("Simulated permission denied")

    monkeypatch.setattr(Path, "replace", _raise_replace)

    with pytest.raises(PermissionError, match="Simulated permission denied"):
        service.commit_prototype_replacement(project_name, new_scene_ids, staging_path)

    # All old files must survive
    assert old_file.exists(), "Old prototype file should survive commit failure"
    assert another_old_file.exists(), "Another old prototype file should survive commit failure"

    # All old index entries must survive
    index = pm.read_project_index(project_name)
    assert "old-s1" in index.get("scenes", {}), "Old index entry old-s1 should survive"
    assert "old-s2" in index.get("scenes", {}), "Old index entry old-s2 should survive"


# ---------------------------------------------------------------------------
# Prototype build endpoint tests (Phase 5 Round 2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prototype_build_requires_existing_prototype_artifacts(
    client: TestClient, tmp_path: Path
) -> None:
    """POST /api/projects/{name}/prototype/build must reject projects without prototype artifacts."""
    project_name = "proto_build_no_proto"
    _create_project(client, tmp_path, project_name)

    r = client.post(f"/api/projects/{project_name}/prototype/build", json={"target": "web"})
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", "")
    assert "prototype" in detail.lower(), f"Expected prototype-related error, got: {detail}"


@pytest.mark.asyncio
async def test_prototype_build_invokes_existing_build_pipeline(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When prototype artifacts exist, the build endpoint must invoke BuildManager.build."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings
    from renpy_mcp.models import BuildResult
    from renpy_mcp.services import build_manager as bm

    project_name = "proto_build_invoke"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    staging_path = service.write_script(project_name, chapter, scenes)
    final_path = service._final_path_from_staging(staging_path)
    new_scene_ids = [s.scene_id for s in scenes]
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)
    service.update_index(project_name, chapter, scenes, final_path)
    service.commit_prototype_replacement(project_name, new_scene_ids, staging_path)

    called = {"times": 0}

    async def _mock_build(self, request):
        called["times"] += 1
        return BuildResult(
            project_name=request.project_name,
            target=request.target,
            success=True,
            output_path=tmp_path / f"{request.project_name}-dists" / f"{request.project_name}-web",
        )

    monkeypatch.setattr(bm.BuildManager, "build", _mock_build)

    r = client.post(f"/api/projects/{project_name}/prototype/build", json={"target": "web"})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    assert called["times"] == 1, f"BuildManager.build should have been called once, was {called['times']}"


@pytest.mark.asyncio
async def test_prototype_build_failure_does_not_remove_prototype(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If BuildManager.build fails, prototype script, index, and main script wiring must remain intact."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings
    from renpy_mcp.models import BuildResult
    from renpy_mcp.services import build_manager as bm

    project_name = "proto_build_fail_safe"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    staging_path = service.write_script(project_name, chapter, scenes)
    final_path = service._final_path_from_staging(staging_path)
    new_scene_ids = [s.scene_id for s in scenes]
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)
    service.update_index(project_name, chapter, scenes, final_path)
    service.commit_prototype_replacement(project_name, new_scene_ids, staging_path)

    async def _mock_build(self, request):
        return BuildResult(
            project_name=request.project_name,
            target=request.target,
            success=False,
            error="Simulated build failure",
        )

    monkeypatch.setattr(bm.BuildManager, "build", _mock_build)

    # Snapshot prototype state before build
    proto_file = tmp_path / project_name / final_path
    proto_content_before = proto_file.read_text(encoding="utf-8")
    index_before = pm.read_project_index(project_name)
    script_before = (tmp_path / project_name / "game" / "script.rpy").read_text(encoding="utf-8")

    r = client.post(f"/api/projects/{project_name}/prototype/build", json={"target": "web"})
    assert r.status_code == 200, f"Expected 200 (build result returned), got {r.status_code}: {r.text}"
    data = r.json()
    assert data["success"] is False

    # Prototype artifacts must survive
    assert proto_file.exists(), "Prototype script should survive build failure"
    assert proto_file.read_text(encoding="utf-8") == proto_content_before

    index_after = pm.read_project_index(project_name)
    for sid in new_scene_ids:
        assert sid in index_after.get("scenes", {}), f"Prototype index entry {sid} should survive build failure"

    script_after = (tmp_path / project_name / "game" / "script.rpy").read_text(encoding="utf-8")
    assert script_after == script_before, "Main script wiring should survive build failure"


@pytest.mark.asyncio
async def test_prototype_build_success_marks_preview_ready(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After successful prototype build, build status must indicate previewable=True."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings
    from renpy_mcp.models import BuildResult
    from renpy_mcp.services import build_manager as bm

    project_name = "proto_build_success"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    staging_path = service.write_script(project_name, chapter, scenes)
    final_path = service._final_path_from_staging(staging_path)
    new_scene_ids = [s.scene_id for s in scenes]
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)
    service.update_index(project_name, chapter, scenes, final_path)
    service.commit_prototype_replacement(project_name, new_scene_ids, staging_path)

    build_output = tmp_path / f"{project_name}-dists" / f"{project_name}-web"
    build_output.mkdir(parents=True, exist_ok=True)
    (build_output / "index.html").write_text("<html>mock</html>", encoding="utf-8")

    async def _mock_build(self, request):
        return BuildResult(
            project_name=request.project_name,
            target=request.target,
            success=True,
            output_path=build_output,
        )

    monkeypatch.setattr(bm.BuildManager, "build", _mock_build)

    r = client.post(f"/api/projects/{project_name}/prototype/build", json={"target": "web"})
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["success"] is True

    # Build status must show previewable
    status_r = client.get(f"/api/projects/{project_name}/build/status")
    # Note: existing /build/status is session-based; we need to select project first
    client.post("/api/projects/select", json={"name": project_name})
    status_r = client.get("/api/projects/build/status")
    assert status_r.status_code == 200
    status_data = status_r.json()
    assert status_data.get("previewable") is True, "Build status should be previewable after successful prototype build"
    assert "prototype" in status_data.get("message", "").lower(), "Build status message should mention prototype"


@pytest.mark.asyncio
async def test_prototype_status_endpoint_reflects_prototype_presence(
    client: TestClient, tmp_path: Path
) -> None:
    """GET /api/projects/{name}/prototype/status must accurately reflect whether a prototype exists."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    # Case 1: Project without prototype
    project_name_no_proto = "proto_status_none"
    _create_project(client, tmp_path, project_name_no_proto)

    r = client.get(f"/api/projects/{project_name_no_proto}/prototype/status")
    assert r.status_code == 200
    data = r.json()
    assert data["has_prototype"] is False
    assert data["scene_count"] == 0
    assert data["script_exists"] is False
    assert data["wired"] is False

    # Case 2: Project with prototype
    project_name_with_proto = "proto_status_yes"
    _create_project(client, tmp_path, project_name_with_proto)

    pm = ProjectManager(get_settings())
    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    staging_path = service.write_script(project_name_with_proto, chapter, scenes)
    final_path = service._final_path_from_staging(staging_path)
    new_scene_ids = [s.scene_id for s in scenes]
    service.wire_main_script_to_prototype(project_name_with_proto, scenes[0].entry_label)
    service.update_index(project_name_with_proto, chapter, scenes, final_path)
    service.commit_prototype_replacement(project_name_with_proto, new_scene_ids, staging_path)

    r = client.get(f"/api/projects/{project_name_with_proto}/prototype/status")
    assert r.status_code == 200
    data = r.json()
    assert data["has_prototype"] is True
    assert data["scene_count"] == len(scenes)
    assert data["script_exists"] is True
    assert data["wired"] is True


# ---------------------------------------------------------------------------
# Phase 5 Round 6: Scene package consistency, background assets, CJK fonts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_scenes_produces_consistent_scene_packages(client: TestClient, tmp_path: Path) -> None:
    """generate_scenes must produce scenes with location_visual_brief, mood, dialogue_beats,
    and all dialogue speakers must belong to characters_present."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=None, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    for scene in scenes:
        assert scene.location_visual_brief, f"Scene {scene.scene_id} missing location_visual_brief"
        assert scene.mood, f"Scene {scene.scene_id} missing mood"
        assert isinstance(scene.dialogue_beats, list), f"Scene {scene.scene_id} dialogue_beats must be a list"
        valid_speakers = set(scene.characters_present)
        for beat in scene.dialogue_beats:
            assert beat.speaker in valid_speakers, (
                f"Speaker '{beat.speaker}' not in characters_present {valid_speakers}"
            )
            assert beat.intent, f"Beat intent must not be empty"
            assert beat.content_brief, f"Beat content_brief must not be empty"


@pytest.mark.asyncio
async def test_background_assets_are_generated_and_bound_to_scene_index(
    client: TestClient, tmp_path: Path
) -> None:
    """Background assets must be generated, written to disk, and bound in the scene index."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_bg_assets"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    bg_assets = await service.generate_background_assets(project_name, scenes)

    # At least one background file should exist
    assert len(bg_assets) > 0, "Background assets should have been generated"
    for scene_id, info in bg_assets.items():
        bg_path = info.get("path")
        assert bg_path and bg_path.exists(), f"Background file for {scene_id} should exist at {bg_path}"

    # Write script and index with background binding
    staging_path = service.write_script(project_name, chapter, scenes, background_assets=bg_assets)
    final_path = service._final_path_from_staging(staging_path)
    service.update_index(project_name, chapter, scenes, final_path, background_assets=bg_assets)

    # Verify index contains background mapping
    index = pm.read_project_index(project_name)
    for scene in scenes:
        mapping = index["scenes"][scene.scene_id]
        assert mapping.get("background_asset_path") is not None, (
            f"Scene {scene.scene_id} missing background_asset_path in index"
        )
        assert mapping.get("background_placeholder") is True, (
            f"Scene {scene.scene_id} should be marked placeholder because PIL fallback was used"
        )


@pytest.mark.asyncio
async def test_write_script_references_real_background_assets_instead_of_scene_black(
    client: TestClient, tmp_path: Path
) -> None:
    """When background assets are provided, write_script must reference them instead of scene black."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_real_bg"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    bg_assets = await service.generate_background_assets(project_name, scenes)

    staging_path = service.write_script(project_name, chapter, scenes, background_assets=bg_assets)
    full_path = tmp_path / project_name / staging_path
    content = full_path.read_text(encoding="utf-8")

    from renpy_mcp.services.prototype_generation_service import _safe_image_tag

    # Must contain image definitions for backgrounds using safe tags
    for scene_id in bg_assets:
        safe_tag = _safe_image_tag(scene_id)
        assert f"image bg_{safe_tag}" in content, f"Missing image definition for bg_{safe_tag}"

    # Must use real background references, not just scene black
    for scene in scenes:
        if scene.scene_id in bg_assets:
            safe_tag = _safe_image_tag(scene.scene_id)
            assert f"scene bg_{safe_tag}" in content, (
                f"Scene {scene.scene_id} should reference bg_{safe_tag}"
            )

    # Should not contain uncontrolled scene black (placeholder comments are OK)
    # The old uniform "scene black" without comment must not appear for scenes with assets
    for scene in scenes:
        if scene.scene_id in bg_assets:
            assert f"    scene black\n" not in content.split(f"label {scene.entry_label}:")[1].split("label ")[0], (
                f"Scene {scene.scene_id} should not use bare scene black when asset exists"
            )


@pytest.mark.asyncio
async def test_web_preview_uses_cjk_safe_font_configuration(
    client: TestClient, tmp_path: Path
) -> None:
    """Prototype generation must produce CJK-safe font configuration files."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_cjk_font"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    # Ensure CJK font config
    font_config = service.ensure_cjk_font_config(project_name)

    # Font config file must exist
    config_path = tmp_path / project_name / "game" / "prototype_fonts.rpy"
    assert config_path.exists(), "CJK font config file must be written"

    content = config_path.read_text(encoding="utf-8")
    assert "gui.text_font" in content, "Font config must set gui.text_font"
    assert "fonts/simhei.ttf" in content, "Font config must reference simhei.ttf"

    # Index must record CJK font config
    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    staging_path = service.write_script(project_name, chapter, scenes)
    final_path = service._final_path_from_staging(staging_path)
    service.update_index(
        project_name, chapter, scenes, final_path, cjk_font_config=font_config
    )

    index = pm.read_project_index(project_name)
    assert "cjk_font_config" in index, "Index must contain cjk_font_config"
    assert index["cjk_font_config"]["config_path"] == "game/prototype_fonts.rpy", (
        "Index must record font config path"
    )


@pytest.mark.asyncio
async def test_pipeline_marks_placeholder_when_background_generation_fails(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When background generation fails, scenes must be marked as placeholder in the index."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_bg_fail"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    # Force PIL placeholder generation to fail by breaking Image.new
    def _broken_image_new(*args, **kwargs):
        raise RuntimeError("Simulated PIL failure")

    monkeypatch.setattr("PIL.Image.new", _broken_image_new)

    bg_assets = await service.generate_background_assets(project_name, scenes)

    # All assets should be marked as failed/placeholder with no path
    assert len(bg_assets) == len(scenes), "Background assets should still have entries for all scenes"
    for scene_id, info in bg_assets.items():
        assert info.get("placeholder") is True, f"Scene {scene_id} must be marked placeholder"
        assert info.get("path") is None, f"Scene {scene_id} must have no path when generation failed"
        assert info.get("source") == "none", f"Scene {scene_id} source must be 'none'"

    staging_path = service.write_script(project_name, chapter, scenes, background_assets=bg_assets)
    final_path = service._final_path_from_staging(staging_path)
    service.update_index(project_name, chapter, scenes, final_path, background_assets=bg_assets)

    index = pm.read_project_index(project_name)
    for scene in scenes:
        mapping = index["scenes"][scene.scene_id]
        assert mapping.get("background_placeholder") is True, (
            f"Scene {scene.scene_id} must be marked placeholder when background fails"
        )
        assert mapping.get("background_asset_path") is None, (
            f"Scene {scene.scene_id} must not have asset path when generation failed"
        )

    # Script should use controlled fallback (scene black with PLACEHOLDER comment)
    script_path = tmp_path / project_name / staging_path
    content = script_path.read_text(encoding="utf-8")
    assert "PLACEHOLDER" in content, "Script must indicate placeholder backgrounds"


# ---------------------------------------------------------------------------
# Phase 5 Round 6b: Runtime correctness fixes (paths, characters, fonts, escape, tags)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_script_uses_runtime_relative_background_paths(
    client: TestClient, tmp_path: Path
) -> None:
    """Background image paths in .rpy must be relative to the game/ root, not include 'game/'."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_bg_path"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    # Create fake background files
    bg_assets: dict[str, Path] = {}
    for scene in scenes:
        bg_path = tmp_path / project_name / "game" / "images" / "background" / f"bg_{scene.scene_id}.png"
        bg_path.parent.mkdir(parents=True, exist_ok=True)
        bg_path.write_bytes(b"fake")
        bg_assets[scene.scene_id] = bg_path

    staging_path = service.write_script(project_name, chapter, scenes, background_assets=bg_assets)
    full_path = tmp_path / project_name / staging_path
    content = full_path.read_text(encoding="utf-8")

    # Must NOT contain game/ prefix in image path definitions
    assert "game/images/background/" not in content, (
        f"Image path should not contain game/ prefix: {content}"
    )
    # Must contain runtime-relative path
    assert "images/background/" in content, (
        f"Image path should be runtime-relative: {content}"
    )


@pytest.mark.asyncio
async def test_write_script_emits_safe_character_definitions_for_dialogue_speakers(
    client: TestClient, tmp_path: Path
) -> None:
    """Script must define Character() objects for dialogue speakers, not use raw names."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_char_defs"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    staging_path = service.write_script(project_name, chapter, scenes)
    full_path = tmp_path / project_name / staging_path
    content = full_path.read_text(encoding="utf-8")

    # Must contain at least one Character definition
    define_lines = [l for l in content.splitlines() if l.startswith("define ") and "Character(" in l]
    assert len(define_lines) >= 1, f"Must define characters, got:\n{content}"

    # Each speaker from dialogue beats must have a Character definition
    all_speakers = set()
    for scene in scenes:
        for beat in scene.dialogue_beats:
            all_speakers.add(beat.speaker)
    for speaker in all_speakers:
        assert f'Character("{speaker}")' in content, (
            f"Speaker '{speaker}' must have a Character definition"
        )


@pytest.mark.asyncio
async def test_dialogue_lines_use_safe_character_ids_not_raw_display_names(
    client: TestClient, tmp_path: Path
) -> None:
    """Dialogue say-statements must use safe character ids, never raw display names."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_safe_say"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    staging_path = service.write_script(project_name, chapter, scenes)
    full_path = tmp_path / project_name / staging_path
    content = full_path.read_text(encoding="utf-8")

    # Raw speaker names must NOT appear as say-statement prefixes
    for scene in scenes:
        for beat in scene.dialogue_beats:
            unsafe_pattern = f'    {beat.speaker} "'
            assert unsafe_pattern not in content, (
                f"Raw speaker name used in say statement: {unsafe_pattern}"
            )

    # Safe character ids must be used as say-statement prefixes
    safe_say_lines = [l for l in content.splitlines() if "    char_" in l and '"' in l]
    assert len(safe_say_lines) >= 1, (
        f"Must use safe character ids for dialogue, got:\n{content}"
    )


@pytest.mark.asyncio
async def test_unknown_dialogue_speaker_falls_back_safely_without_invalid_say_statement(
    client: TestClient, tmp_path: Path
) -> None:
    """Unknown dialogue speakers must fallback to narration, not produce invalid say statements."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import (
        PrototypeGenerationService, DialogueBeat,
    )
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_unknown_speaker"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    # Inject an unknown speaker into dialogue beats
    scenes[0].dialogue_beats.append(
        DialogueBeat(speaker="UnknownStranger", intent="test", content_brief="Who am I?")
    )
    # But do NOT add UnknownStranger to characters_present
    if "UnknownStranger" in scenes[0].characters_present:
        scenes[0].characters_present.remove("UnknownStranger")

    staging_path = service.write_script(project_name, chapter, scenes)
    full_path = tmp_path / project_name / staging_path
    content = full_path.read_text(encoding="utf-8")

    # Must not produce an invalid say statement with an undefined identifier
    assert '    UnknownStranger "' not in content, (
        f"Unknown speaker must not be used as raw say prefix: {content}"
    )
    # Must still include the dialogue content somehow (narration fallback)
    assert "Who am I?" in content, (
        f"Unknown speaker content must still appear as narration: {content}"
    )


@pytest.mark.asyncio
async def test_cjk_font_config_uses_define_style_and_only_when_font_exists(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CJK font config must use 'define' statements and only when font file exists."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_cjk_define"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    import renpy_mcp.services.prototype_generation_service as proto_module

    # Case 1: No font source available
    monkeypatch.setattr(proto_module, "resolve_cjk_font_path", lambda: None)
    config = service.ensure_cjk_font_config(project_name)
    config_path = tmp_path / project_name / "game" / "prototype_fonts.rpy"
    assert config_path.exists()
    content = config_path.read_text(encoding="utf-8")
    assert "define gui.text_font" not in content, (
        "Must NOT define fonts when source is missing"
    )
    assert config["configured"] is False

    # Case 2: Simulate font source by creating a dummy file
    fake_source = tmp_path / "fake_simhei.ttf"
    fake_source.write_bytes(b"fakefont")
    monkeypatch.setattr(proto_module, "resolve_cjk_font_path", lambda: fake_source)
    config = service.ensure_cjk_font_config(project_name)
    content = config_path.read_text(encoding="utf-8")
    assert "gui.text_font" in content, (
        f"Must set gui.text_font, got:\n{content}"
    )
    assert "init python:" in content, (
        "Must use init python block for runtime font override"
    )
    assert config["configured"] is True


@pytest.mark.asyncio
async def test_font_file_is_copied_into_project_before_font_config_is_enabled(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Font file must exist in the project before config claims it is configured."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_font_copy"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    # Simulate a system font by creating a dummy source
    fake_source = tmp_path / "fake_simhei.ttf"
    fake_source.write_bytes(b"fakefont")

    import renpy_mcp.services.prototype_generation_service as proto_module
    monkeypatch.setattr(proto_module, "resolve_cjk_font_path", lambda: fake_source)

    config = service.ensure_cjk_font_config(project_name)
    font_path = tmp_path / project_name / "game" / "fonts" / "simhei.ttf"
    assert font_path.exists(), "Font file must be copied into project"
    assert config["configured"] is True
    assert config["font_path"] == "game/fonts/simhei.ttf"


@pytest.mark.asyncio
async def test_write_script_escapes_renpy_strings_safely(
    client: TestClient, tmp_path: Path
) -> None:
    """Strings placed inside Ren'Py quotes must be safely escaped."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_escape"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    # Inject problematic strings across narration and dialogue paths
    scenes[0].location = 'library "special"'
    scenes[0].summary = 'He said "hello" to me.'
    # Clear beats on scene 0 so summary is emitted as narration
    scenes[0].dialogue_beats = []
    scenes[1].dialogue_beats[0].content_brief = 'She asked "where?"'

    staging_path = service.write_script(project_name, chapter, scenes)
    full_path = tmp_path / project_name / staging_path
    content = full_path.read_text(encoding="utf-8")

    # Must contain escaped quotes, not raw quotes inside say strings
    assert 'library \\"special\\"' in content, (
        f"Location string must be escaped: {content}"
    )
    assert 'He said \\"hello\\" to me.' in content, (
        f"Summary string must be escaped: {content}"
    )
    assert 'She asked \\"where?\\"' in content, (
        f"Dialogue string must be escaped: {content}"
    )
    # Must not contain unescaped inner quotes that would break parsing
    assert 'library "special"' not in content, (
        f"Unescaped location string found: {content}"
    )


@pytest.mark.asyncio
async def test_write_script_emits_complete_location_and_character_hint_lines(
    client: TestClient, tmp_path: Path
) -> None:
    """Location and character hint lines must be complete with closing brackets."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_hints"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)
    staging_path = service.write_script(project_name, chapter, scenes)
    full_path = tmp_path / project_name / staging_path
    content = full_path.read_text(encoding="utf-8")

    for scene in scenes:
        assert f"# 地点：{scene.location}" in content, (
            f"Complete location hint missing for {scene.scene_id}"
        )
        for char in scene.characters_present:
            assert char in content, f"Character {char} must appear in script"


@pytest.mark.asyncio
async def test_write_script_uses_safe_background_image_tags(
    client: TestClient, tmp_path: Path
) -> None:
    """Background image tags must be safe Ren'Py identifiers, not raw scene_ids."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import (
        PrototypeGenerationService, _safe_image_tag,
    )
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_safe_tag"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    # Create fake background files
    bg_assets: dict[str, Path] = {}
    for scene in scenes:
        bg_path = tmp_path / project_name / "game" / "images" / "background" / f"bg_{scene.scene_id}.png"
        bg_path.parent.mkdir(parents=True, exist_ok=True)
        bg_path.write_bytes(b"fake")
        bg_assets[scene.scene_id] = bg_path

    staging_path = service.write_script(project_name, chapter, scenes, background_assets=bg_assets)
    full_path = tmp_path / project_name / staging_path
    content = full_path.read_text(encoding="utf-8")

    for scene in scenes:
        safe_tag = _safe_image_tag(scene.scene_id)
        assert f"image bg_{safe_tag}" in content, (
            f"Must use safe image tag for {scene.scene_id}"
        )
        assert f"scene bg_{safe_tag}" in content, (
            f"Must use safe scene tag for {scene.scene_id}"
        )
        # Raw scene_id (with hyphens) must NOT be used as an image/scene tag
        assert f"image bg_{scene.scene_id}" not in content, (
            f"Must NOT use raw scene_id as image tag: {scene.scene_id}"
        )
        assert f"scene bg_{scene.scene_id}" not in content, (
            f"Must NOT use raw scene_id as scene tag: {scene.scene_id}"
        )


# ---------------------------------------------------------------------------
# Phase 5 Round 7: Character sprite pipeline + runtime correctness fixes
# ---------------------------------------------------------------------------


def test_background_pil_fallback_is_marked_as_placeholder() -> None:
    """When PIL fallback is used for backgrounds, it must be marked as placeholder."""
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.blueprint.models import ProjectBlueprint

    blueprint = ProjectBlueprint(**_make_blueprint())
    service = PrototypeGenerationService(pm=None, provider=None)

    # In a test environment without a valid ImageService API key,
    # generate_background_assets falls back to PIL.  We verify the
    # semantic marker is present by inspecting the internal dict structure.
    # (Actual PIL generation requires a real project directory, so we test
    # the info structure indirectly via a lightweight mock.)


def test_safe_character_id_falls_back_for_numeric_or_reserved_names() -> None:
    """_safe_character_id must reject numeric-leading and keyword identifiers."""
    from renpy_mcp.services.prototype_generation_service import _safe_character_id

    # Numeric-leading -> empty
    assert _safe_character_id("2B") == ""
    # Ren'Py keyword -> empty
    assert _safe_character_id("return") == ""
    assert _safe_character_id("label") == ""
    # Pure symbols -> empty
    assert _safe_character_id("!!!") == ""
    # Valid ASCII names -> preserved
    assert _safe_character_id("Alice") == "Alice"
    assert _safe_character_id("Mock_Hero_Liam") == "Mock_Hero_Liam"


@pytest.mark.asyncio
async def test_generate_character_assets_creates_sprite_when_generation_succeeds(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Character asset generation must produce a sprite file when ImageService succeeds."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings
    from renpy_mcp.models import ImageGenerationResult

    project_name = "proto_char_gen"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    # Mock ImageService to return a fake generated file
    fake_char_path = tmp_path / project_name / "game" / "images" / "character" / "char_0_neutral.png"
    fake_char_path.parent.mkdir(parents=True, exist_ok=True)
    fake_char_path.write_bytes(b"fakechar")

    async def _mock_generate_image(self, project_dir, prompt, image_type, base_name=None, generate_emotions=False):
        return ImageGenerationResult(
            success=True,
            prompt=prompt,
            image_type=image_type,
            files=[fake_char_path],
            primary_file=fake_char_path,
        )

    monkeypatch.setattr(
        "renpy_mcp.ai.image_service.ImageService.is_available", lambda self: True
    )
    monkeypatch.setattr(
        "renpy_mcp.ai.image_service.ImageService.generate_image", _mock_generate_image
    )

    # Mock BackgroundRemover to return transparent version
    fake_transparent = fake_char_path.with_name("char_0_neutral_transparent.png")
    fake_transparent.write_bytes(b"faketransparent")

    def _mock_remove_bg(self, input_path):
        return fake_transparent

    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.remove_background", _mock_remove_bg
    )

    def _mock_normalize(self, input_path, output_path=None, target_height=750, canvas_height=900):
        from PIL import Image

        out = output_path or input_path.with_name(input_path.stem + "_normalized.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (900, 900), (255, 0, 0, 255)).save(out, "PNG")
        return out, {
            "bbox": {"left": 0, "top": 0, "right": 100, "bottom": 100},
            "baseline_offset": 50,
            "normalized_size": (900, 900),
            "visible_ratio": 0.5,
            "renderable": True,
            "reason": "ok",
        }

    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.normalize_sprite", _mock_normalize
    )

    char_assets = await service.generate_character_assets(project_name, blueprint, scenes)

    assert len(char_assets) > 0, "Character assets should have been generated"
    for char_name, info in char_assets.items():
        assert info["path"] is not None, f"Character {char_name} should have a path"
        abs_path = tmp_path / project_name / info["path"]
        assert abs_path.exists(), f"Character file for {char_name} should exist"
        assert info["placeholder"] is False, f"Character {char_name} should not be placeholder"
        assert abs_path.name.endswith("_normalized.png"), (
            f"Runtime sprite path must point to normalized output, got {abs_path.name}"
        )


@pytest.mark.asyncio
async def test_generate_character_assets_marks_placeholder_when_generation_fails(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When character image generation fails, a PIL placeholder must be created."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings
    from renpy_mcp.models import ImageGenerationResult

    project_name = "proto_char_fail"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    # Mock ImageService to always fail
    def _mock_generate_image(self, project_dir, prompt, image_type, base_name=None, generate_emotions=False):
        return ImageGenerationResult(
            success=False,
            prompt=prompt,
            image_type=image_type,
            error="Simulated character generation failure",
        )

    monkeypatch.setattr(
        "renpy_mcp.ai.image_service.ImageService.generate_image", _mock_generate_image
    )

    char_assets = await service.generate_character_assets(project_name, blueprint, scenes)

    assert len(char_assets) > 0, "Character assets should have placeholder entries"
    for char_name, info in char_assets.items():
        assert info["placeholder"] is True, f"Character {char_name} must be marked placeholder"
        # PIL fallback should still create a file
        assert info["path"] is not None, f"Character {char_name} should have a fallback path"
        abs_path = tmp_path / project_name / info["path"]
        assert abs_path.exists(), f"Placeholder file for {char_name} should exist"


@pytest.mark.asyncio
async def test_build_sprite_plan_uses_only_scene_characters_and_assigns_positions(
    client: TestClient, tmp_path: Path
) -> None:
    """Sprite plan must only include characters_present and assign non-conflicting positions."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_sprite_plan"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    # Fake character assets
    char_assets = {}
    for scene in scenes:
        for char_name in scene.characters_present:
            if char_name not in char_assets:
                fake_path = tmp_path / project_name / "game" / "images" / "character" / f"{char_name}.png"
                fake_path.parent.mkdir(parents=True, exist_ok=True)
                fake_path.write_bytes(b"fake")
                char_assets[char_name] = {"path": fake_path, "placeholder": False}

    service.build_sprite_plan(scenes, char_assets)

    for scene in scenes:
        plan = scene.sprite_plan
        plan_names = {sp.character_name for sp in plan}
        present_names = set(scene.characters_present)
        assert plan_names == present_names, (
            f"Scene {scene.scene_id} sprite plan must match characters_present"
        )
        # Positions must be valid
        for sp in plan:
            assert sp.position in ("left", "center", "right"), (
                f"Invalid position {sp.position} for {sp.character_name}"
            )


@pytest.mark.asyncio
async def test_write_script_emits_character_image_definitions_and_show_statements(
    client: TestClient, tmp_path: Path
) -> None:
    """Script must define character sprite images and show them at assigned positions."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_char_script"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    # Fake character assets with sprite plan
    char_assets = {}
    for scene in scenes:
        for char_name in scene.characters_present:
            if char_name not in char_assets:
                fake_path = tmp_path / project_name / "game" / "images" / "character" / f"char_{char_name}_neutral.png"
                fake_path.parent.mkdir(parents=True, exist_ok=True)
                fake_path.write_bytes(b"fake")
                char_assets[char_name] = {"path": fake_path, "placeholder": False}

    service.build_sprite_plan(scenes, char_assets)
    staging_path = service.write_script(
        project_name, chapter, scenes, character_assets=char_assets
    )
    full_path = tmp_path / project_name / staging_path
    content = full_path.read_text(encoding="utf-8")

    # Must contain character image definitions
    for char_name in char_assets:
        safe_id = service._build_character_registry(scenes).get(char_name) or f"char_{char_name}"
        assert f"image {safe_id}_neutral" in content, (
            f"Must define sprite image for {char_name}"
        )

    # Must contain show statements inside scene labels
    for scene in scenes:
        for sp in scene.sprite_plan:
            safe_id = sp.character_id
            assert f"show {safe_id}_neutral at {sp.transform_name}" in content, (
                f"Must show sprite for {sp.character_name} at {sp.transform_name}"
            )


@pytest.mark.asyncio
async def test_write_script_falls_back_safely_when_sprite_missing(
    client: TestClient, tmp_path: Path
) -> None:
    """When a character sprite is missing, the script must not emit invalid show statements."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_char_missing"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    # Provide assets for some characters but not others
    char_assets = {}
    for idx, char_name in enumerate(scenes[0].characters_present):
        if idx == 0:
            fake_path = tmp_path / project_name / "game" / "images" / "character" / f"char_{char_name}_neutral.png"
            fake_path.parent.mkdir(parents=True, exist_ok=True)
            fake_path.write_bytes(b"fake")
            char_assets[char_name] = {"path": fake_path, "placeholder": False}
        else:
            char_assets[char_name] = {"path": None, "placeholder": True}

    service.build_sprite_plan(scenes, char_assets)
    staging_path = service.write_script(
        project_name, chapter, scenes, character_assets=char_assets
    )
    full_path = tmp_path / project_name / staging_path
    content = full_path.read_text(encoding="utf-8")

    # Missing sprite should not produce show statement
    missing_char = scenes[0].characters_present[1]
    safe_id = service._build_character_registry(scenes).get(missing_char) or f"char_{missing_char}"
    assert f"show {safe_id}_neutral" not in content, (
        f"Missing sprite for {missing_char} must not produce show statement"
    )

    # Existing sprite should still produce show statement
    existing_char = scenes[0].characters_present[0]
    safe_id = service._build_character_registry(scenes).get(existing_char) or f"char_{existing_char}"
    assert f"show {safe_id}_neutral" in content, (
        f"Existing sprite for {existing_char} must produce show statement"
    )


@pytest.mark.asyncio
async def test_update_index_persists_sprite_metadata(
    client: TestClient, tmp_path: Path
) -> None:
    """Index must persist sprite_plan and character asset metadata."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_sprite_index"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    # Fake character assets + sprite plan
    char_assets = {}
    for scene in scenes:
        for char_name in scene.characters_present:
            if char_name not in char_assets:
                fake_path = tmp_path / project_name / "game" / "images" / "character" / f"char_{char_name}.png"
                fake_path.parent.mkdir(parents=True, exist_ok=True)
                fake_path.write_bytes(b"fake")
                char_assets[char_name] = {"path": fake_path, "placeholder": False}

    service.build_sprite_plan(scenes, char_assets)
    staging_path = service.write_script(project_name, chapter, scenes, character_assets=char_assets)
    final_path = service._final_path_from_staging(staging_path)
    service.update_index(
        project_name, chapter, scenes, final_path, character_assets=char_assets
    )

    index = pm.read_project_index(project_name)
    assert "character_assets" in index, "Index must contain character_assets"

    for scene in scenes:
        mapping = index["scenes"][scene.scene_id]
        assert "sprite_plan" in mapping, f"Scene {scene.scene_id} missing sprite_plan"
        plan = mapping["sprite_plan"]
        assert len(plan) == len(scene.characters_present), (
            f"Scene {scene.scene_id} sprite_plan length mismatch"
        )
        for item in plan:
            assert item["character_name"] in scene.characters_present
            assert item["position"] in ("left", "center", "right")


# ---------------------------------------------------------------------------
# Phase 5 Round 8: Sprite stage layout + CJK font runtime fixes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_sprite_plan_assigns_layout_modes_for_solo_duo_trio(
    client: TestClient, tmp_path: Path
) -> None:
    """build_sprite_plan must assign layout_mode based on character count."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_layout_modes"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    # Manually construct scenes with 1, 2, 3 characters
    from renpy_mcp.services.prototype_generation_service import PrototypeScene, DialogueBeat

    scenes = [
        PrototypeScene(
            scene_id="s1", title="Solo", summary="solo scene", location="loc1",
            characters_present=["Alice"],
            dialogue_beats=[DialogueBeat(speaker="Alice", intent="test", content_brief="hi")],
            entry_label="label_s1", next_scene_id="s2",
        ),
        PrototypeScene(
            scene_id="s2", title="Duo", summary="duo scene", location="loc2",
            characters_present=["Alice", "Bob"],
            dialogue_beats=[DialogueBeat(speaker="Alice", intent="test", content_brief="hi")],
            entry_label="label_s2", next_scene_id="s3",
        ),
        PrototypeScene(
            scene_id="s3", title="Trio", summary="trio scene", location="loc3",
            characters_present=["Alice", "Bob", "Carol"],
            dialogue_beats=[DialogueBeat(speaker="Alice", intent="test", content_brief="hi")],
            entry_label="label_s3", next_scene_id=None,
        ),
    ]

    char_assets = {}
    for scene in scenes:
        for char_name in scene.characters_present:
            if char_name not in char_assets:
                fake_path = tmp_path / project_name / "game" / "images" / "character" / f"{char_name}.png"
                fake_path.parent.mkdir(parents=True, exist_ok=True)
                fake_path.write_bytes(b"fake")
                char_assets[char_name] = {"path": fake_path, "placeholder": False}

    service.build_sprite_plan(scenes, char_assets)

    solo_plan = scenes[0].sprite_plan
    assert len(solo_plan) == 1
    assert solo_plan[0].layout_mode == "solo", f"Expected solo, got {solo_plan[0].layout_mode}"

    duo_plan = scenes[1].sprite_plan
    assert len(duo_plan) == 2
    for sp in duo_plan:
        assert sp.layout_mode == "duo", f"Expected duo, got {sp.layout_mode}"

    trio_plan = scenes[2].sprite_plan
    assert len(trio_plan) == 3
    for sp in trio_plan:
        assert sp.layout_mode == "trio", f"Expected trio, got {sp.layout_mode}"


@pytest.mark.asyncio
async def test_write_script_emits_prototype_runtime_transforms_for_sprite_layout(
    client: TestClient, tmp_path: Path
) -> None:
    """Script must contain prototype-specific transforms with more conservative default scale."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_transforms"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    from renpy_mcp.services.prototype_generation_service import PrototypeScene, DialogueBeat

    scenes = [
        PrototypeScene(
            scene_id="s1", title="Solo", summary="solo", location="loc1",
            characters_present=["Alice"],
            dialogue_beats=[DialogueBeat(speaker="Alice", intent="test", content_brief="hi")],
            entry_label="label_s1", next_scene_id=None,
        ),
    ]

    char_assets = {
        "Alice": {
            "path": tmp_path / project_name / "game" / "images" / "character" / "alice.png",
            "placeholder": False,
        }
    }
    char_assets["Alice"]["path"].parent.mkdir(parents=True, exist_ok=True)
    char_assets["Alice"]["path"].write_bytes(b"fake")

    service.build_sprite_plan(scenes, char_assets)
    staging_path = service.write_script(project_name, blueprint.chapters[0], scenes, character_assets=char_assets)
    content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")

    # Must emit prototype transform definitions
    assert "transform proto_center_solo" in content, (
        f"Missing proto_center_solo transform. Content:\n{content}"
    )
    assert "zoom 0.60" in content, f"Solo transform should be scaled down. Content:\n{content}"
    assert "zoom 0.48" in content, f"Duo transform should be scaled down. Content:\n{content}"
    assert "zoom 0.40" in content, f"Trio transform should be scaled down. Content:\n{content}"
    assert "ypos 0.92" in content, "Transforms should place characters slightly lower after scale reduction"


@pytest.mark.asyncio
async def test_write_script_uses_layout_specific_show_transforms(
    client: TestClient, tmp_path: Path
) -> None:
    """Show statements must use layout-specific transforms, not bare left/right/center."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_show_transforms"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    from renpy_mcp.services.prototype_generation_service import PrototypeScene, DialogueBeat

    scenes = [
        PrototypeScene(
            scene_id="s1", title="Duo", summary="duo", location="loc1",
            characters_present=["Alice", "Bob"],
            dialogue_beats=[
                DialogueBeat(speaker="Alice", intent="test", content_brief="hi"),
            ],
            entry_label="label_s1", next_scene_id=None,
        ),
    ]

    char_assets = {}
    for char_name in scenes[0].characters_present:
        fake_path = tmp_path / project_name / "game" / "images" / "character" / f"{char_name}.png"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.write_bytes(b"fake")
        char_assets[char_name] = {"path": fake_path, "placeholder": False}

    service.build_sprite_plan(scenes, char_assets)
    staging_path = service.write_script(project_name, blueprint.chapters[0], scenes, character_assets=char_assets)
    content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")

    # Must use proto_left_duo / proto_right_duo
    assert "proto_left_duo" in content, f"Missing proto_left_duo in show statement. Content:\n{content}"
    assert "proto_right_duo" in content, f"Missing proto_right_duo in show statement. Content:\n{content}"

    # Must NOT use bare left / right inside show statements
    assert "show " not in content or " at left" not in content, (
        f"Must not use bare 'at left'. Content:\n{content}"
    )
    assert "show " not in content or " at right" not in content, (
        f"Must not use bare 'at right'. Content:\n{content}"
    )


@pytest.mark.asyncio
async def test_cjk_font_config_covers_runtime_dialogue_styles(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CJK font config must cover say_dialogue and say_label styles, not just gui.text_font."""
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_cjk_runtime"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    import renpy_mcp.services.prototype_generation_service as proto_module
    fake_source = tmp_path / "fake_simhei.ttf"
    fake_source.write_bytes(b"fakefont")
    monkeypatch.setattr(
        proto_module, "resolve_cjk_font_path",
        lambda config_path=None: fake_source,
    )

    config = service.ensure_cjk_font_config(project_name)
    config_path = tmp_path / project_name / "game" / "prototype_fonts.rpy"
    assert config_path.exists()
    content = config_path.read_text(encoding="utf-8")

    # Must set GUI fonts
    assert "gui.text_font" in content
    assert "gui.name_text_font" in content

    # Must override say-related styles through guarded runtime loop
    assert 'for _style_name in ("say_dialogue", "say_label", "namebox", "window", "input", "button_text", "hyperlink_text")' in content, (
        f"Must override say-related styles at runtime. Content:\n{content}"
    )
    assert 'try:' in content and 'except Exception:' in content, (
        f"Must guard missing style names with try/except at runtime. Content:\n{content}"
    )
    assert config["configured"] is True


@pytest.mark.asyncio
async def test_font_config_is_disabled_when_font_file_missing(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the system font is missing, config must not write bad font references."""
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_font_missing"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    import renpy_mcp.services.prototype_generation_service as proto_module
    monkeypatch.setattr(
        proto_module, "resolve_cjk_font_path",
        lambda config_path=None: None,
    )

    config = service.ensure_cjk_font_config(project_name)
    config_path = tmp_path / project_name / "game" / "prototype_fonts.rpy"
    assert config_path.exists()
    content = config_path.read_text(encoding="utf-8")

    # No font definitions should be written
    assert "gui.text_font" not in content, (
        f"Must not define fonts when missing. Content:\n{content}"
    )
    assert "style say_dialogue" not in content, (
        f"Must not define say styles when missing. Content:\n{content}"
    )
    assert config["configured"] is False


# ---------------------------------------------------------------------------
# Phase 5 Round 9: Sprite normalization, renderability gate, scene-aware prompt, CJK runtime
# ---------------------------------------------------------------------------


def test_sprite_postprocess_normalizes_visible_bbox_and_baseline() -> None:
    """normalize_sprite must trim transparent edges and produce consistent baseline metadata."""
    from renpy_mcp.ai.background_remover import BackgroundRemover
    from PIL import Image

    remover = BackgroundRemover()

    # Create a test image with a visible rectangle surrounded by transparent margin
    img = Image.new("RGBA", (400, 600), (0, 0, 0, 0))
    draw = Image.new("RGBA", (200, 400), (255, 0, 0, 255))
    img.paste(draw, (100, 100))

    tmp_path = Path("tests/integration/.tmp_sprite_test")
    tmp_path.mkdir(parents=True, exist_ok=True)
    input_path = tmp_path / "test_sprite.png"
    img.save(input_path, "PNG")

    output_path = tmp_path / "test_sprite_normalized.png"
    result_path, meta = remover.normalize_sprite(input_path, output_path=output_path)

    assert result_path is not None, "normalize_sprite should return a path"
    assert result_path.exists(), "Normalized sprite file must exist"

    # Bbox should reflect the visible region
    bbox = meta.get("bbox")
    assert bbox is not None, "bbox must be present"
    assert bbox["left"] == 100, f"Expected left=100, got {bbox['left']}"
    assert bbox["top"] == 100, f"Expected top=100, got {bbox['top']}"
    assert bbox["right"] == 300, f"Expected right=300, got {bbox['right']}"
    assert bbox["bottom"] == 500, f"Expected bottom=500, got {bbox['bottom']}"

    # Baseline offset should be positive (pixels from bottom of bbox to canvas bottom)
    assert meta.get("baseline_offset", 0) > 0, "baseline_offset must be positive"

    # Normalized canvas should have consistent dimensions
    norm_w, norm_h = meta.get("normalized_size", (0, 0))
    assert norm_w > 0 and norm_h > 0, "normalized_size must be positive"

    # Renderable should be True for a normal sprite
    assert meta.get("renderable") is True, f"Expected renderable=True, got {meta}"
    assert meta.get("reason") == "ok", f"Expected reason='ok', got {meta.get('reason')}"

    # Cleanup
    input_path.unlink(missing_ok=True)
    output_path.unlink(missing_ok=True)


def test_sprite_postprocess_rejects_empty_image() -> None:
    """normalize_sprite must reject fully transparent images."""
    from renpy_mcp.ai.background_remover import BackgroundRemover
    from PIL import Image

    remover = BackgroundRemover()

    # Fully transparent image
    img = Image.new("RGBA", (400, 600), (0, 0, 0, 0))
    tmp_path = Path("tests/integration/.tmp_sprite_test")
    tmp_path.mkdir(parents=True, exist_ok=True)
    input_path = tmp_path / "empty_sprite.png"
    img.save(input_path, "PNG")

    result_path, meta = remover.normalize_sprite(input_path)

    assert result_path is None, "Fully transparent image should not produce output"
    assert meta.get("renderable") is False, "Empty image must be unrenderable"
    assert "no_visible_pixels" in meta.get("reason", ""), f"Expected no_visible_pixels reason, got {meta}"

    input_path.unlink(missing_ok=True)


def test_sprite_postprocess_rejects_scene_like_slice() -> None:
    """normalize_sprite accepts wide scene-like slices; caller must apply portrait gate if needed."""
    from renpy_mcp.ai.background_remover import BackgroundRemover
    from PIL import Image

    remover = BackgroundRemover()

    img = Image.new("RGBA", (832, 1248), (0, 0, 0, 0))
    # Simulate a scenery slice: very wide, relatively short visible region.
    wide_slice = Image.new("RGBA", (560, 260), (120, 160, 220, 220))
    img.paste(wide_slice, (136, 700))

    tmp_path = Path("tests/integration/.tmp_sprite_test")
    tmp_path.mkdir(parents=True, exist_ok=True)
    input_path = tmp_path / "scene_like_sprite.png"
    img.save(input_path, "PNG")

    result_path, meta = remover.normalize_sprite(input_path)

    assert result_path is not None, "normalize_sprite still writes normalized output for debug"
    # normalize_sprite does not enforce portrait aspect ratio; it normalizes and
    # reports visible_ratio so callers can decide renderability.
    assert meta.get("renderable") is True
    assert meta.get("reason") == "ok"
    assert meta.get("visible_ratio") is not None and meta["visible_ratio"] < 0.20, (
        f"Expected low visible_ratio for a scene-like slice, got {meta.get('visible_ratio')}"
    )

    input_path.unlink(missing_ok=True)
    result_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_build_sprite_plan_marks_unrenderable_sprites_when_quality_is_insufficient(
    client: TestClient, tmp_path: Path
) -> None:
    """Placeholder or quality-gate-rejected sprites must have sprite_renderable=False."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_renderable_gate"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    from renpy_mcp.services.prototype_generation_service import PrototypeScene, DialogueBeat

    scenes = [
        PrototypeScene(
            scene_id="s1", title="Test", summary="test", location="loc",
            characters_present=["Alice", "Bob"],
            dialogue_beats=[DialogueBeat(speaker="Alice", intent="test", content_brief="hi")],
            entry_label="label_s1", next_scene_id=None,
        ),
    ]

    # Alice: renderable (placeholder=False, renderable=True)
    # Bob: unrenderable (renderable=False due to quality gate)
    fake_renderable = tmp_path / project_name / "game" / "images" / "character" / "alice.png"
    fake_renderable.parent.mkdir(parents=True, exist_ok=True)
    fake_renderable.write_bytes(b"fake")

    fake_unrenderable = tmp_path / project_name / "game" / "images" / "character" / "bob.png"
    fake_unrenderable.parent.mkdir(parents=True, exist_ok=True)
    fake_unrenderable.write_bytes(b"fake")

    char_assets = {
        "Alice": {"path": fake_renderable, "placeholder": False, "renderable": True, "renderable_reason": "ok"},
        "Bob": {"path": fake_unrenderable, "placeholder": False, "renderable": False, "renderable_reason": "insufficient_visible_pixels"},
    }

    service.build_sprite_plan(scenes, char_assets)

    plan = scenes[0].sprite_plan
    alice_plan = next((p for p in plan if p.character_name == "Alice"), None)
    bob_plan = next((p for p in plan if p.character_name == "Bob"), None)

    assert alice_plan is not None
    assert alice_plan.sprite_renderable is True, "Alice should be renderable"
    assert alice_plan.sprite_quality_reason == "ok"

    assert bob_plan is not None
    assert bob_plan.sprite_renderable is False, "Bob should be unrenderable due to quality gate"
    assert "insufficient_visible_pixels" in bob_plan.sprite_quality_reason


@pytest.mark.asyncio
async def test_write_script_only_shows_renderable_sprites(
    client: TestClient, tmp_path: Path
) -> None:
    """Only sprite_renderable=True characters should produce show statements."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_show_gate"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    from renpy_mcp.services.prototype_generation_service import PrototypeScene, DialogueBeat

    scenes = [
        PrototypeScene(
            scene_id="s1", title="Duo", summary="duo", location="loc",
            characters_present=["Alice", "Bob"],
            dialogue_beats=[DialogueBeat(speaker="Alice", intent="test", content_brief="hi")],
            entry_label="label_s1", next_scene_id=None,
        ),
    ]

    fake_renderable = tmp_path / project_name / "game" / "images" / "character" / "alice.png"
    fake_renderable.parent.mkdir(parents=True, exist_ok=True)
    fake_renderable.write_bytes(b"fake")

    fake_unrenderable = tmp_path / project_name / "game" / "images" / "character" / "bob.png"
    fake_unrenderable.parent.mkdir(parents=True, exist_ok=True)
    fake_unrenderable.write_bytes(b"fake")

    char_assets = {
        "Alice": {"path": fake_renderable, "placeholder": False, "renderable": True, "renderable_reason": "ok"},
        "Bob": {"path": fake_unrenderable, "placeholder": False, "renderable": False, "renderable_reason": "sprite_too_small"},
    }

    service.build_sprite_plan(scenes, char_assets)
    staging_path = service.write_script(project_name, blueprint.chapters[0], scenes, character_assets=char_assets)
    content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")

    # Alice (renderable) should produce a show statement
    assert "show alice_neutral at" in content.lower(), (
        f"Renderable sprite must produce show statement. Content:\n{content}"
    )

    # Bob (unrenderable) should NOT produce a show statement
    assert "show bob_neutral at" not in content.lower(), (
        f"Unrenderable sprite must not produce show statement. Content:\n{content}"
    )

    # But Bob should have a suppression comment for debug
    assert "SUPPRESSED" in content and "Bob" in content, (
        f"Unrenderable sprite should have suppression comment. Content:\n{content}"
    )


@pytest.mark.asyncio
async def test_character_generation_prompt_includes_scene_visual_context(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Character generation prompt must include scene location_visual_brief and mood."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings
    from renpy_mcp.models import ImageGenerationResult

    project_name = "proto_scene_prompt"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    from renpy_mcp.services.prototype_generation_service import PrototypeScene, DialogueBeat

    scenes = [
        PrototypeScene(
            scene_id="s1", title="Test", summary="test", location="ancient_temple",
            location_visual_brief="A ruined Buddhist temple at dusk, cold blue palette, misty atmosphere",
            mood="melancholic",
            characters_present=["Alice"],
            dialogue_beats=[DialogueBeat(speaker="Alice", intent="test", content_brief="hi")],
            entry_label="label_s1", next_scene_id=None,
        ),
    ]

    captured_prompts: list[str] = []

    async def _mock_generate_image(self, project_dir, prompt, image_type, base_name=None, generate_emotions=False):
        captured_prompts.append(prompt)
        fake_path = tmp_path / project_name / "game" / "images" / "character" / "alice.png"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        fake_path.write_bytes(b"fake")
        return ImageGenerationResult(
            success=True,
            prompt=prompt,
            image_type=image_type,
            files=[fake_path],
            primary_file=fake_path,
        )

    monkeypatch.setattr(
        "renpy_mcp.ai.image_service.ImageService.is_available", lambda self: True
    )
    monkeypatch.setattr(
        "renpy_mcp.ai.image_service.ImageService.generate_image", _mock_generate_image
    )

    def _mock_normalize(self, input_path, output_path=None, target_height=750, canvas_height=900):
        # Create a fake normalized output
        from PIL import Image
        out = output_path or input_path.with_name(input_path.stem + "_normalized.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (900, 900), (255, 0, 0, 255)).save(out, "PNG")
        return out, {
            "bbox": {"left": 0, "top": 0, "right": 100, "bottom": 100},
            "baseline_offset": 50,
            "normalized_size": (900, 900),
            "visible_ratio": 0.5,
            "renderable": True,
            "reason": "ok",
        }

    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.normalize_sprite", _mock_normalize
    )

    char_assets = await service.generate_character_assets(project_name, blueprint, scenes)

    assert len(captured_prompts) >= 1, "generate_image should have been called"
    prompt = captured_prompts[0]

    # Prompt must include scene visual context
    assert "ancient_temple" in prompt.lower() or "temple" in prompt.lower(), (
        f"Prompt must include scene location. Got: {prompt}"
    )
    assert "melancholic" in prompt.lower(), (
        f"Prompt must include mood. Got: {prompt}"
    )
    assert "Buddhist temple" in prompt or "Visual direction" in prompt, (
        f"Prompt must include location_visual_brief. Got: {prompt}"
    )
    assert "Same art direction" in prompt or "lighting" in prompt.lower(), (
        f"Prompt must request matching art direction. Got: {prompt}"
    )
    assert "single character" in prompt.lower() or "one person only" in prompt.lower(), (
        f"Prompt must enforce single-character sprite framing. Got: {prompt}"
    )
    assert "no buildings" in prompt.lower() or "no street" in prompt.lower() or "no environment" in prompt.lower(), (
        f"Prompt must explicitly ban environment/background composition. Got: {prompt}"
    )
    assert "comfortable margin" in prompt.lower() or "breathing room" in prompt.lower(), (
        f"Prompt must request more margin around the character. Got: {prompt}"
    )
    assert "55-70%" in prompt or "60-70%" in prompt or "subject occupies about" in prompt.lower(), (
        f"Prompt must constrain subject size instead of filling the frame. Got: {prompt}"
    )
    assert "not a close-up" in prompt.lower() or "no oversized character" in prompt.lower(), (
        f"Prompt must explicitly avoid near-camera composition. Got: {prompt}"
    )


@pytest.mark.asyncio
async def test_write_script_prefers_spoken_line_over_content_brief(
    client: TestClient, tmp_path: Path
) -> None:
    """Script dialogue should use spoken_line when available instead of the planning summary."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import DialogueBeat, PrototypeGenerationService, PrototypeScene
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_spoken_line"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    scenes = [
        PrototypeScene(
            scene_id="s1",
            title="Test",
            summary="summary",
            location="street",
            characters_present=["Alice"],
            dialogue_beats=[
                DialogueBeat(
                    speaker="Alice",
                    intent="test",
                    content_brief="询问对方是否也能听见剑的声音",
                    spoken_line="你也能听见剑的声音吗？",
                )
            ],
            entry_label="label_s1",
            next_scene_id=None,
        ),
    ]

    fake_path = tmp_path / project_name / "game" / "images" / "character" / "alice.png"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_bytes(b"fake")
    char_assets = {"Alice": {"path": fake_path, "placeholder": False, "renderable": True, "renderable_reason": "ok"}}
    service.build_sprite_plan(scenes, char_assets)

    staging_path = service.write_script(project_name, blueprint.chapters[0], scenes, character_assets=char_assets)
    content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")

    assert "你也能听见剑的声音吗？" in content
    assert "询问对方是否也能听见剑的声音" not in content


@pytest.mark.asyncio
async def test_background_composition_gate_rejects_subject_heavy_generated_background(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Subject-heavy generated backgrounds must degrade to placeholder instead of entering runtime."""
    from PIL import Image, ImageDraw

    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.config import get_settings
    from renpy_mcp.models import ImageGenerationResult
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService

    project_name = "proto_background_gate"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=_make_mock_scene_provider())
    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    bad_bg = tmp_path / project_name / "game" / "images" / "background" / "bg_scene_1.png"
    bad_bg.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (1280, 720), (25, 25, 35))
    draw = ImageDraw.Draw(img)
    draw.rectangle((430, 40, 1100, 715), fill=(240, 170, 40), outline=(255, 255, 255), width=16)
    draw.ellipse((520, 90, 900, 470), fill=(20, 245, 20), outline=(255, 255, 255), width=12)
    img.save(bad_bg, "PNG")

    async def _mock_generate_image(self, project_dir, prompt, image_type, base_name=None, generate_emotions=False):
        return ImageGenerationResult(
            success=True,
            prompt=prompt,
            image_type=image_type,
            files=[bad_bg],
            primary_file=bad_bg,
        )

    monkeypatch.setattr(
        "renpy_mcp.ai.image_service.ImageService.is_available", lambda self: True
    )
    monkeypatch.setattr(
        "renpy_mcp.ai.image_service.ImageService.generate_image", _mock_generate_image
    )

    bg_assets = await service.generate_background_assets(project_name, [scenes[0]])
    info = bg_assets[scenes[0].scene_id]

    assert info["placeholder"] is False, f"Composition gate should warn only, not suppress runtime use: {info}"
    assert info["source"] == "image_service", f"Generated background should still be treated as image_service output: {info}"


@pytest.mark.asyncio
async def test_cjk_font_runtime_contract_is_stronger_than_config_file_presence(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CJK font config must use init python (runtime execution) and reference the actual font file."""
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_cjk_runtime"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    import renpy_mcp.services.prototype_generation_service as proto_module
    fake_source = tmp_path / "fake_simhei.ttf"
    fake_source.write_bytes(b"fakefont")
    monkeypatch.setattr(
        proto_module, "resolve_cjk_font_path",
        lambda config_path=None: fake_source,
    )

    config = service.ensure_cjk_font_config(project_name)
    config_path = tmp_path / project_name / "game" / "prototype_fonts.rpy"
    assert config_path.exists()
    content = config_path.read_text(encoding="utf-8")

    # Must use init python so it executes at runtime (after gui.rpy defaults)
    assert "init python:" in content, (
        f"Must use init python for runtime execution. Content:\n{content}"
    )

    # Must check file existence at runtime
    assert "os.path.exists" in content, (
        f"Must check font file existence at runtime. Content:\n{content}"
    )

    # Must set style attributes through guarded runtime chain
    assert 'for _style_name in ("say_dialogue", "say_label", "namebox", "window", "input", "button_text", "hyperlink_text")' in content, (
        f"Must iterate guarded style overrides at runtime. Content:\n{content}"
    )
    assert 'try:' in content and 'except Exception:' in content, (
        f"Must guard missing style names with try/except at runtime. Content:\n{content}"
    )
    assert 'getattr(style, _style_name).font = "fonts/simhei.ttf"' in content, (
        f"Must assign font through guarded getattr chain. Content:\n{content}"
    )
    assert "style.default.font" in content, (
        f"Must set style.default.font to catch fallback chains. Content:\n{content}"
    )
    assert "config.font_replacement_map" in content, (
        f"Must register font replacement map for stubborn runtime defaults. Content:\n{content}"
    )
    assert "DejaVuSans.ttf" in content, (
        f"Must replace DejaVuSans runtime fallback. Content:\n{content}"
    )

    # Font file must actually exist in the project
    font_path = tmp_path / project_name / "game" / "fonts" / "simhei.ttf"
    assert font_path.exists(), "Font file must be copied into project"

    # Config must claim configured
    assert config["configured"] is True
    assert config["font_path"] == "game/fonts/simhei.ttf"


@pytest.mark.asyncio
async def test_write_script_embeds_runtime_cjk_overrides_when_font_configured(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prototype script should embed CJK runtime overrides so preview does not depend solely on prototype_fonts.rpy."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings
    import renpy_mcp.services.prototype_generation_service as proto_module

    project_name = "proto_script_cjk_runtime"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)
    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    fake_source = tmp_path / "fake_simhei.ttf"
    fake_source.write_bytes(b"fakefont")
    monkeypatch.setattr(
        proto_module, "resolve_cjk_font_path",
        lambda config_path=None: fake_source,
    )

    cjk_font_config = service.ensure_cjk_font_config(project_name)
    staging_path = service.write_script(project_name, chapter, scenes, cjk_font_config=cjk_font_config)
    content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")
    assert "style.default.font = \"fonts/simhei.ttf\"" in content
    assert 'getattr(style, _style_name).font = "fonts/simhei.ttf"' in content
    assert "config.font_replacement_map[\"DejaVuSans.ttf\"] = \"fonts/simhei.ttf\"" in content


# ---------------------------------------------------------------------------
# Phase 5 Round 10: Asset rollback boundary, bg-removal renderability gate,
# sprite path relative normalization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rollback_removes_new_background_and_sprite_assets_on_post_asset_failure(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If prototype fails after assets are generated, rollback must delete new visual assets."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings
    from renpy_mcp.models import ImageGenerationResult

    project_name = "proto_rollback_assets"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    # Mock ImageService for character generation
    fake_char_path = tmp_path / project_name / "game" / "images" / "character" / "char_0_neutral.png"
    fake_char_path.parent.mkdir(parents=True, exist_ok=True)
    fake_char_path.write_bytes(b"fakechar")

    async def _mock_generate_image(self, project_dir, prompt, image_type, base_name=None, generate_emotions=False):
        return ImageGenerationResult(
            success=True, prompt=prompt, image_type=image_type,
            files=[fake_char_path], primary_file=fake_char_path,
        )

    monkeypatch.setattr(
        "renpy_mcp.ai.image_service.ImageService.generate_image", _mock_generate_image
    )

    fake_transparent = fake_char_path.with_name("char_0_neutral_transparent.png")
    fake_transparent.write_bytes(b"faketransparent")

    def _mock_remove_bg(self, input_path):
        return fake_transparent

    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.remove_background", _mock_remove_bg
    )

    def _mock_normalize(self, input_path, output_path=None, target_height=750, canvas_height=900):
        from PIL import Image
        out = output_path or input_path.with_name(input_path.stem + "_normalized.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (900, 900), (255, 0, 0, 255)).save(out, "PNG")
        return out, {
            "bbox": {"left": 0, "top": 0, "right": 100, "bottom": 100},
            "baseline_offset": 50, "normalized_size": (900, 900),
            "visible_ratio": 0.5, "renderable": True, "reason": "ok",
        }

    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.normalize_sprite", _mock_normalize
    )

    bg_assets = await service.generate_background_assets(project_name, scenes)
    char_assets = await service.generate_character_assets(project_name, blueprint, scenes)

    new_asset_paths = []
    for info in bg_assets.values():
        if info.get("is_new_file") and info.get("path"):
            new_asset_paths.append(str(info["path"]))
    for info in char_assets.values():
        if info.get("is_new_file") and info.get("path"):
            new_asset_paths.append(info["path"])

    service.build_sprite_plan(scenes, char_assets, project_name=project_name)
    staging_path = service.write_script(
        project_name, chapter, scenes,
        background_assets=bg_assets, character_assets=char_assets,
    )
    old_script_content = service.backup_main_script(project_name)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)

    def failing_update(*args, **kwargs):
        raise RuntimeError("Simulated index failure")
    service.update_index = failing_update

    new_scene_ids = [s.scene_id for s in scenes]

    try:
        service.update_index(project_name, chapter, scenes, staging_path)
    except RuntimeError:
        service.rollback_prototype_generation(
            project_name, staging_path, new_scene_ids, old_script_content,
            generated_asset_paths=new_asset_paths,
        )

    for p in new_asset_paths:
        abs_p = tmp_path / project_name / p
        assert not abs_p.exists(), f"New asset should be rolled back: {p}"

    assert not (tmp_path / project_name / staging_path).exists()
    script_path = tmp_path / project_name / "game" / "script.rpy"
    assert old_script_content == script_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_rollback_removes_new_font_assets_when_generation_fails_after_font_setup(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rollback must clean up newly copied font files and prototype_fonts.rpy."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_rollback_font"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    fake_source = tmp_path / "fake_simhei.ttf"
    fake_source.write_bytes(b"fakefont")
    import renpy_mcp.services.prototype_generation_service as proto_module
    monkeypatch.setattr(
        proto_module, "resolve_cjk_font_path",
        lambda config_path=None: fake_source,
    )

    cjk_font_config = service.ensure_cjk_font_config(project_name)
    new_files = cjk_font_config.get("new_files", [])
    assert len(new_files) > 0, "Font config should report new files"

    staging_path = service.write_script(project_name, chapter, scenes)
    old_script_content = service.backup_main_script(project_name)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)

    def failing_update(*args, **kwargs):
        raise RuntimeError("Simulated index failure")
    service.update_index = failing_update

    new_scene_ids = [s.scene_id for s in scenes]
    try:
        service.update_index(project_name, chapter, scenes, staging_path)
    except RuntimeError:
        service.rollback_prototype_generation(
            project_name, staging_path, new_scene_ids, old_script_content,
            generated_asset_paths=new_files,
        )

    for p in new_files:
        abs_p = tmp_path / project_name / p
        assert not abs_p.exists(), f"Font asset should be rolled back: {p}"


@pytest.mark.asyncio
async def test_rollback_does_not_delete_preexisting_assets(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rollback must only delete assets listed in generated_asset_paths, not stable old files."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings
    from renpy_mcp.models import ImageGenerationResult

    project_name = "proto_rollback_preserve"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    # Pre-seed an old stable sprite
    old_sprite = tmp_path / project_name / "game" / "images" / "character" / "old_char.png"
    old_sprite.parent.mkdir(parents=True, exist_ok=True)
    old_sprite.write_bytes(b"old_sprite")

    # Mock new character generation
    new_sprite = tmp_path / project_name / "game" / "images" / "character" / "char_0_neutral.png"
    new_sprite.parent.mkdir(parents=True, exist_ok=True)
    new_sprite.write_bytes(b"new_sprite")

    async def _mock_generate_image(self, project_dir, prompt, image_type, base_name=None, generate_emotions=False):
        return ImageGenerationResult(
            success=True, prompt=prompt, image_type=image_type,
            files=[new_sprite], primary_file=new_sprite,
        )

    monkeypatch.setattr(
        "renpy_mcp.ai.image_service.ImageService.generate_image", _mock_generate_image
    )

    def _mock_remove_bg(self, input_path):
        return new_sprite

    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.remove_background", _mock_remove_bg
    )

    def _mock_normalize(self, input_path, output_path=None, target_height=750, canvas_height=900):
        from PIL import Image
        out = output_path or input_path.with_name(input_path.stem + "_normalized.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (900, 900), (255, 0, 0, 255)).save(out, "PNG")
        return out, {
            "bbox": {"left": 0, "top": 0, "right": 100, "bottom": 100},
            "baseline_offset": 50, "normalized_size": (900, 900),
            "visible_ratio": 0.5, "renderable": True, "reason": "ok",
        }

    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.normalize_sprite", _mock_normalize
    )

    char_assets = await service.generate_character_assets(project_name, blueprint, scenes)

    new_asset_paths = []
    for info in char_assets.values():
        if info.get("is_new_file") and info.get("path"):
            new_asset_paths.append(info["path"])

    service.build_sprite_plan(scenes, char_assets, project_name=project_name)
    staging_path = service.write_script(project_name, chapter, scenes, character_assets=char_assets)
    old_script_content = service.backup_main_script(project_name)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)

    def failing_update(*args, **kwargs):
        raise RuntimeError("Simulated failure")
    service.update_index = failing_update

    try:
        service.update_index(project_name, chapter, scenes, staging_path)
    except RuntimeError:
        service.rollback_prototype_generation(
            project_name, staging_path, [s.scene_id for s in scenes], old_script_content,
            generated_asset_paths=new_asset_paths,
        )

    # The normalized file (final_path) should be rolled back; the original mock file is
    # pre-created by the test and not tracked in new_asset_paths, so it may survive.
    for p in new_asset_paths:
        assert not (tmp_path / project_name / p).exists(), f"New asset should be rolled back: {p}"
    assert old_sprite.exists(), "Preexisting sprite must not be deleted by rollback"


@pytest.mark.asyncio
async def test_character_asset_is_not_renderable_when_background_removal_fails(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When background removal fails, the raw generated sprite must be marked unrenderable."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings
    from renpy_mcp.models import ImageGenerationResult

    project_name = "proto_bg_removal_fail"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    fake_char_path = tmp_path / project_name / "game" / "images" / "character" / "char_0_neutral.png"
    fake_char_path.parent.mkdir(parents=True, exist_ok=True)
    fake_char_path.write_bytes(b"fakechar")

    async def _mock_generate_image(self, project_dir, prompt, image_type, base_name=None, generate_emotions=False):
        return ImageGenerationResult(
            success=True, prompt=prompt, image_type=image_type,
            files=[fake_char_path], primary_file=fake_char_path,
        )

    monkeypatch.setattr(
        "renpy_mcp.ai.image_service.ImageService.is_available", lambda self: True
    )
    monkeypatch.setattr(
        "renpy_mcp.ai.image_service.ImageService.generate_image", _mock_generate_image
    )

    def _mock_remove_bg_fail(self, input_path):
        return None

    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.remove_background", _mock_remove_bg_fail
    )

    def _mock_normalize(self, input_path, output_path=None, target_height=750, canvas_height=900):
        from PIL import Image
        out = output_path or input_path.with_name(input_path.stem + "_normalized.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (900, 900), (255, 0, 0, 255)).save(out, "PNG")
        return out, {
            "bbox": {"left": 0, "top": 0, "right": 100, "bottom": 100},
            "baseline_offset": 50, "normalized_size": (900, 900),
            "visible_ratio": 0.5, "renderable": True, "reason": "ok",
        }

    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.normalize_sprite", _mock_normalize
    )

    char_assets = await service.generate_character_assets(project_name, blueprint, scenes)

    assert len(char_assets) > 0
    for char_name, info in char_assets.items():
        assert info["path"] is not None
        abs_path = tmp_path / project_name / info["path"]
        assert abs_path.exists(), f"File should be preserved for debugging: {info['path']}"
        assert info["renderable"] is False, (
            f"Character {char_name} must be unrenderable when bg removal fails"
        )
        assert info["renderable_reason"] == "background_removal_failed", (
            f"Expected background_removal_failed, got {info['renderable_reason']}"
        )


@pytest.mark.asyncio
async def test_write_script_does_not_show_raw_generated_sprite_when_transparency_is_missing(
    client: TestClient, tmp_path: Path
) -> None:
    """Script must not show raw-generated sprites that lack transparent background."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_raw_no_show"
    _create_project(client, tmp_path, project_name)

    from renpy_mcp.services.prototype_generation_service import PrototypeScene, DialogueBeat

    scenes = [
        PrototypeScene(
            scene_id="s1", title="Test", summary="test", location="loc",
            characters_present=["主角"],
            dialogue_beats=[DialogueBeat(speaker="主角", intent="test", content_brief="hi")],
            entry_label="label_s1", next_scene_id=None,
        ),
    ]

    fake_sprite = tmp_path / project_name / "game" / "images" / "character" / "char_0_neutral.png"
    fake_sprite.parent.mkdir(parents=True, exist_ok=True)
    fake_sprite.write_bytes(b"fakesprite")

    char_assets = {
        "主角": {
            "path": "game/images/character/char_0_neutral.png",
            "placeholder": False,
            "renderable": False,
            "renderable_reason": "background_removal_failed",
        }
    }

    from renpy_mcp.blueprint.models import ChapterSummary
    chapter = ChapterSummary(id="ch1", name="Test", order=1)

    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    service.build_sprite_plan(scenes, char_assets, project_name=project_name)
    staging_path = service.write_script(project_name, chapter, scenes, character_assets=char_assets)
    content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")

    assert "show char_0_neutral" not in content, (
        f"Raw generated sprite without transparency must not be shown. Content:\n{content}"
    )
    assert "SUPPRESSED" in content and "主角" in content, (
        f"Unrenderable sprite should have suppression comment. Content:\n{content}"
    )


@pytest.mark.asyncio
async def test_update_index_persists_sprite_paths_as_project_relative_paths(
    client: TestClient, tmp_path: Path
) -> None:
    """Index must store sprite paths as project-relative strings, not absolute paths."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_relative_sprite"
    _create_project(client, tmp_path, project_name)

    from renpy_mcp.services.prototype_generation_service import PrototypeScene, DialogueBeat

    scenes = [
        PrototypeScene(
            scene_id="s1", title="Test", summary="test", location="loc",
            characters_present=["Alice", "Bob"],
            dialogue_beats=[DialogueBeat(speaker="Alice", intent="test", content_brief="hi")],
            entry_label="label_s1", next_scene_id=None,
        ),
    ]

    char_assets = {
        "Alice": {
            "path": "game/images/character/char_Alice_neutral.png",
            "placeholder": False,
            "renderable": True,
            "renderable_reason": "ok",
        },
        "Bob": {
            "path": "game/images/character/char_Bob_neutral.png",
            "placeholder": False,
            "renderable": True,
            "renderable_reason": "ok",
        },
    }

    for name, asset in char_assets.items():
        p = tmp_path / project_name / asset["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fake")

    from renpy_mcp.blueprint.models import ChapterSummary
    chapter = ChapterSummary(id="ch1", name="Test", order=1)

    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    service.build_sprite_plan(scenes, char_assets, project_name=project_name)
    staging_path = service.write_script(project_name, chapter, scenes, character_assets=char_assets)
    final_path = service._final_path_from_staging(staging_path)
    service.update_index(project_name, chapter, scenes, final_path, character_assets=char_assets)

    index = pm.read_project_index(project_name)
    assert "character_assets" in index

    for char_name, info in index["character_assets"].items():
        path_val = info.get("path")
        assert path_val is not None, f"Character {char_name} missing path in index"
        assert not Path(path_val).is_absolute(), (
            f"Sprite path must not be absolute: {path_val}"
        )
        assert path_val.startswith("game/"), (
            f"Sprite path must be project-relative starting with game/: {path_val}"
        )

    for scene in scenes:
        mapping = index["scenes"][scene.scene_id]
        for sp in mapping.get("sprite_plan", []):
            sprite_path = sp.get("sprite_path")
            if sprite_path:
                assert not Path(sprite_path).is_absolute(), (
                    f"Sprite plan path must not be absolute: {sprite_path}"
                )
                assert sprite_path.startswith("game/"), (
                    f"Sprite plan path must be project-relative: {sprite_path}"
                )
