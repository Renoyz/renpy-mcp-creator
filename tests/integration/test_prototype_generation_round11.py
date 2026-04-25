"""Phase 5 Round 11: Streaming progress + round-scoped asset staging rollback."""

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
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")
    r = client.post("/api/projects", json={"name": name})
    assert r.status_code == 200


def _make_blueprint() -> dict:
    return {
        "title": "Test Prototype",
        "genre": "Test",
        "worldview": "Test world",
        "themes": ["test"],
        "target_audience": "test",
        "estimated_play_time": "1h",
        "art_style": "test",
        "audio_style": "test",
        "characters": [
            {"name": "Alice", "role": "Protagonist", "personality": "brave", "appearance": "tall"},
            {"name": "Bob", "role": "Companion", "personality": "smart", "appearance": "glasses"},
        ],
        "chapters": [
            {
                "id": "ch1",
                "name": "Chapter1",
                "order": 1,
                "scenes": [
                    {"id": "s1", "name": "Opening", "order": 1},
                    {"id": "s2", "name": "Development", "order": 2},
                ],
            }
        ],
    }


def _make_mock_scene_provider() -> object:
    scenes = [
        {
            "scene_id": "proto-ch1-s1",
            "title": "First Meeting",
            "summary": "Alice meets Bob.",
            "location": "library",
            "location_visual_brief": "Quiet library with warm lighting",
            "mood": "warm",
            "characters_present": ["Alice", "Bob"],
            "dialogue_beats": [
                {"speaker": "Alice", "intent": "greet", "content_brief": "Hello there"},
            ],
            "entry_label": "prototype_ch1_start",
            "next_scene_id": "proto-ch1-s2",
        },
        {
            "scene_id": "proto-ch1-s2",
            "title": "Departure",
            "summary": "They say goodbye.",
            "location": "station",
            "location_visual_brief": "Night train station",
            "mood": "sad",
            "characters_present": ["Alice", "Bob"],
            "dialogue_beats": [
                {"speaker": "Bob", "intent": "farewell", "content_brief": "See you"},
            ],
            "entry_label": "prototype_ch1_scene2",
            "next_scene_id": None,
        },
    ]

    class MockSceneProvider:
        tool_format = "anthropic"

        def chat(self, messages, tools=None, system=None, model=None, max_tokens=1024, temperature=None):
            from renpy_mcp.chat_engine.providers import LLMResponse
            return LLMResponse(
                content_blocks=[{"type": "text", "text": json.dumps(scenes, ensure_ascii=False)}],
                stop_reason="end_turn",
            )

    return MockSceneProvider()


# ---------------------------------------------------------------------------
# Round 11: Round-scoped asset staging rollback tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_regeneration_preserves_previous_background_assets_when_same_paths_are_reused(
    client: TestClient, tmp_path: Path
) -> None:
    """When a second generation round reuses the same background paths and fails,
    the previous stable background assets must remain intact."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_bg_preserve"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    # --- Round 1: successful generation + commit ---
    round1_id = "r1"
    bg_assets_r1 = await service.generate_background_assets(project_name, scenes, round_id=round1_id)
    staging_path_r1 = service.write_script(project_name, chapter, scenes, background_assets=bg_assets_r1)
    final_path_r1 = service._final_path_from_staging(staging_path_r1)
    new_scene_ids = [s.scene_id for s in scenes]
    old_script = service.backup_main_script(project_name)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)
    service.update_index(project_name, chapter, scenes, final_path_r1, background_assets=bg_assets_r1)
    service.commit_prototype_replacement(project_name, new_scene_ids, staging_path_r1, round_id=round1_id)

    # Verify round-1 backgrounds are at final paths
    final_bg_paths = []
    for sid, info in bg_assets_r1.items():
        final_rel = info["path"]
        final_abs = tmp_path / project_name / final_rel
        assert final_abs.exists(), f"Round-1 background missing: {final_rel}"
        final_bg_paths.append(final_abs)

    # Snapshot content
    round1_contents = {p: p.read_bytes() for p in final_bg_paths}

    # --- Round 2: reuse same paths, fail after asset generation ---
    round2_id = "r2"
    bg_assets_r2 = await service.generate_background_assets(project_name, scenes, round_id=round2_id)
    staging_path_r2 = service.write_script(project_name, chapter, scenes, background_assets=bg_assets_r2)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)

    def failing_update(*args, **kwargs):
        raise RuntimeError("Simulated index failure")
    service.update_index = failing_update

    try:
        service.update_index(project_name, chapter, scenes, service._final_path_from_staging(staging_path_r2), background_assets=bg_assets_r2)
    except RuntimeError:
        service.rollback_prototype_generation(
            project_name, staging_path_r2, new_scene_ids, old_script, round_id=round2_id,
        )

    # Round-1 backgrounds must still exist with original content
    for p, content in round1_contents.items():
        assert p.exists(), f"Round-1 background was deleted: {p}"
        assert p.read_bytes() == content, f"Round-1 background was overwritten: {p}"

    # Round-2 staging must be gone
    staging_dir_r2 = tmp_path / project_name / "game" / "__staging__" / round2_id
    assert not staging_dir_r2.exists(), "Round-2 staging dir should be removed by rollback"


@pytest.mark.asyncio
async def test_failed_regeneration_preserves_previous_character_assets_when_same_paths_are_reused(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a second generation round reuses the same character paths and fails,
    the previous stable character assets must remain intact."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings
    from renpy_mcp.models import ImageGenerationResult

    project_name = "proto_char_preserve"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    async def _mock_generate_image(self, project_dir, prompt, image_type, base_name=None, generate_emotions=False):
        file_name = f"{base_name or 'char'}-mock.png"
        fake_char_path = project_dir / "game" / "images" / "character" / file_name
        fake_char_path.parent.mkdir(parents=True, exist_ok=True)
        fake_char_path.write_bytes(b"alice_v1")
        return ImageGenerationResult(
            success=True, prompt=prompt, image_type=image_type,
            files=[fake_char_path], primary_file=fake_char_path,
        )

    monkeypatch.setattr(
        "renpy_mcp.ai.image_service.ImageService.generate_image", _mock_generate_image
    )

    def _mock_remove_bg(self, input_path):
        return input_path

    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.remove_background", _mock_remove_bg
    )

    def _mock_normalize(self, input_path, output_path=None, target_height=750, canvas_height=900):
        from PIL import Image
        out = output_path or input_path.with_name(input_path.stem + "_normalized.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (400, 750), (255, 0, 0, 255)).save(out, "PNG")
        return out, {
            "bbox": {"left": 0, "top": 0, "right": 100, "bottom": 100},
            "baseline_offset": 50, "normalized_size": (400, 750),
            "visible_ratio": 0.5, "renderable": True, "reason": "ok",
        }

    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.normalize_sprite", _mock_normalize
    )

    # --- Round 1: successful generation + commit ---
    round1_id = "r1"
    char_assets_r1 = await service.generate_character_assets(project_name, blueprint, scenes, round_id=round1_id)
    staging_path_r1 = service.write_script(project_name, chapter, scenes, character_assets=char_assets_r1)
    final_path_r1 = service._final_path_from_staging(staging_path_r1)
    new_scene_ids = [s.scene_id for s in scenes]
    old_script = service.backup_main_script(project_name)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)
    service.build_sprite_plan(scenes, char_assets_r1, project_name=project_name)
    service.update_index(project_name, chapter, scenes, final_path_r1, character_assets=char_assets_r1)
    service.commit_prototype_replacement(project_name, new_scene_ids, staging_path_r1, round_id=round1_id)

    # Find final character files from round 1
    final_char_paths = []
    for name, info in char_assets_r1.items():
        final_rel = info["path"]
        final_abs = tmp_path / project_name / final_rel
        if final_abs.exists():
            final_char_paths.append(final_abs)

    assert len(final_char_paths) > 0, "Round-1 character files should exist"
    assert all(p.name.endswith("_normalized.png") for p in final_char_paths), (
        f"Round-1 runtime sprite paths should point to normalized files, got {final_char_paths}"
    )
    round1_contents = {p: p.read_bytes() for p in final_char_paths}

    # --- Round 2: change mock content, fail after asset generation ---
    round2_id = "r2"
    char_assets_r2 = await service.generate_character_assets(project_name, blueprint, scenes, round_id=round2_id)
    staging_path_r2 = service.write_script(project_name, chapter, scenes, character_assets=char_assets_r2)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)

    def failing_update(*args, **kwargs):
        raise RuntimeError("Simulated index failure")
    service.update_index = failing_update

    try:
        service.update_index(project_name, chapter, scenes, service._final_path_from_staging(staging_path_r2), character_assets=char_assets_r2)
    except RuntimeError:
        service.rollback_prototype_generation(
            project_name, staging_path_r2, new_scene_ids, old_script, round_id=round2_id,
        )

    # Round-1 character files must survive
    for p, content in round1_contents.items():
        assert p.exists(), f"Round-1 character asset was deleted: {p}"
        assert p.read_bytes() == content, f"Round-1 character asset was overwritten: {p}"

    # Round-2 staging must be gone
    staging_dir_r2 = tmp_path / project_name / "game" / "__staging__" / round2_id
    assert not staging_dir_r2.exists(), "Round-2 staging dir should be removed by rollback"


@pytest.mark.asyncio
async def test_rollback_removes_intermediate_character_artifacts(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rollback must clean up raw, transparent, and normalized intermediate sprite files."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings
    from renpy_mcp.models import ImageGenerationResult

    project_name = "proto_intermediate_cleanup"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    fake_char_path = tmp_path / project_name / "game" / "images" / "character" / "char_Alice_neutral.png"
    fake_char_path.parent.mkdir(parents=True, exist_ok=True)
    fake_char_path.write_bytes(b"raw")

    async def _mock_generate_image(self, project_dir, prompt, image_type, base_name=None, generate_emotions=False):
        return ImageGenerationResult(
            success=True, prompt=prompt, image_type=image_type,
            files=[fake_char_path], primary_file=fake_char_path,
        )

    monkeypatch.setattr(
        "renpy_mcp.ai.image_service.ImageService.generate_image", _mock_generate_image
    )

    fake_transparent = fake_char_path.with_name("char_Alice_neutral_transparent.png")
    fake_transparent.write_bytes(b"transparent")

    def _mock_remove_bg(self, input_path):
        return fake_transparent

    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.remove_background", _mock_remove_bg
    )

    fake_normalized = fake_char_path.with_name("char_Alice_neutral_normalized.png")
    fake_normalized.write_bytes(b"normalized")

    def _mock_normalize(self, input_path, output_path=None, target_height=750, canvas_height=900):
        from PIL import Image
        out = output_path or fake_normalized
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (400, 750), (255, 0, 0, 255)).save(out, "PNG")
        return out, {
            "bbox": {"left": 0, "top": 0, "right": 100, "bottom": 100},
            "baseline_offset": 50, "normalized_size": (400, 750),
            "visible_ratio": 0.5, "renderable": True, "reason": "ok",
        }

    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.normalize_sprite", _mock_normalize
    )

    round_id = "r1"
    char_assets = await service.generate_character_assets(project_name, blueprint, scenes, round_id=round_id)

    # Track all intermediate files created in staging
    staging_dir = tmp_path / project_name / "game" / "__staging__" / round_id
    all_staging_files = list(staging_dir.rglob("*")) if staging_dir.exists() else []
    all_staging_files = [p for p in all_staging_files if p.is_file()]
    assert len(all_staging_files) > 0, "Staging should contain character files"

    staging_path = service.write_script(project_name, chapter, scenes, character_assets=char_assets)
    old_script = service.backup_main_script(project_name)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)

    def failing_update(*args, **kwargs):
        raise RuntimeError("Simulated index failure")
    service.update_index = failing_update

    new_scene_ids = [s.scene_id for s in scenes]
    try:
        service.update_index(project_name, chapter, scenes, service._final_path_from_staging(staging_path), character_assets=char_assets)
    except RuntimeError:
        service.rollback_prototype_generation(
            project_name, staging_path, new_scene_ids, old_script, round_id=round_id,
        )

    # All staging files (including intermediates) must be gone
    for p in all_staging_files:
        assert not p.exists(), f"Intermediate artifact should be removed: {p}"

    # Staging directory itself should be gone
    assert not staging_dir.exists(), "Staging directory should be removed by rollback"


@pytest.mark.asyncio
async def test_rollback_keeps_old_font_assets_but_removes_new_font_assets(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rollback must preserve pre-existing font files while removing newly created ones."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_font_rollback"
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
    monkeypatch.setattr(proto_module, "resolve_cjk_font_path", lambda: fake_source)

    # Round 1: generate font config successfully
    round1_id = "r1"
    cjk_config_r1 = service.ensure_cjk_font_config(project_name)
    staging_path_r1 = service.write_script(project_name, chapter, scenes)
    final_path_r1 = service._final_path_from_staging(staging_path_r1)
    new_scene_ids = [s.scene_id for s in scenes]
    old_script = service.backup_main_script(project_name)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)
    service.update_index(project_name, chapter, scenes, final_path_r1, cjk_font_config=cjk_config_r1)
    service.commit_prototype_replacement(project_name, new_scene_ids, staging_path_r1, round_id=round1_id)

    font_path = tmp_path / project_name / "game" / "fonts" / "simhei.ttf"
    assert font_path.exists(), "Font file should exist after round 1"
    font_content = font_path.read_bytes()

    # Round 2: fail after font setup
    round2_id = "r2"
    cjk_config_r2 = service.ensure_cjk_font_config(project_name)
    staging_path_r2 = service.write_script(project_name, chapter, scenes)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)

    def failing_update(*args, **kwargs):
        raise RuntimeError("Simulated index failure")
    service.update_index = failing_update

    try:
        service.update_index(project_name, chapter, scenes, service._final_path_from_staging(staging_path_r2), cjk_font_config=cjk_config_r2)
    except RuntimeError:
        service.rollback_prototype_generation(
            project_name, staging_path_r2, new_scene_ids, old_script,
            generated_asset_paths=cjk_config_r2.get("new_files", []),
            round_id=round2_id,
        )

    # Old font file must survive
    assert font_path.exists(), "Pre-existing font file must survive rollback"
    assert font_path.read_bytes() == font_content, "Font file must not be altered"

    # New round-2 staging font config must be gone
    staging_dir_r2 = tmp_path / project_name / "game" / "__staging__" / round2_id
    assert not staging_dir_r2.exists(), "Round-2 staging dir should be removed"


@pytest.mark.asyncio
async def test_rollback_leaves_index_and_assets_consistent_after_post_asset_failure(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After rollback, index must not reference assets that no longer exist."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings
    from renpy_mcp.models import ImageGenerationResult

    project_name = "proto_consistent_rollback"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    fake_char_path = tmp_path / project_name / "game" / "images" / "character" / "char_Alice_neutral.png"
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

    def _mock_remove_bg(self, input_path):
        return fake_char_path

    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.remove_background", _mock_remove_bg
    )

    def _mock_normalize(self, input_path, output_path=None, target_height=750, canvas_height=900):
        from PIL import Image
        out = output_path or input_path.with_name(input_path.stem + "_normalized.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (400, 750), (255, 0, 0, 255)).save(out, "PNG")
        return out, {
            "bbox": {"left": 0, "top": 0, "right": 100, "bottom": 100},
            "baseline_offset": 50, "normalized_size": (400, 750),
            "visible_ratio": 0.5, "renderable": True, "reason": "ok",
        }

    monkeypatch.setattr(
        "renpy_mcp.ai.background_remover.BackgroundRemover.normalize_sprite", _mock_normalize
    )

    round_id = "r1"
    bg_assets = await service.generate_background_assets(project_name, scenes, round_id=round_id)
    char_assets = await service.generate_character_assets(project_name, blueprint, scenes, round_id=round_id)
    service.build_sprite_plan(scenes, char_assets, project_name=project_name)
    staging_path = service.write_script(
        project_name, chapter, scenes,
        background_assets=bg_assets, character_assets=char_assets,
    )
    old_script = service.backup_main_script(project_name)
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)

    def failing_update(*args, **kwargs):
        raise RuntimeError("Simulated index failure")
    service.update_index = failing_update

    new_scene_ids = [s.scene_id for s in scenes]
    try:
        service.update_index(
            project_name, chapter, scenes, service._final_path_from_staging(staging_path),
            background_assets=bg_assets, character_assets=char_assets,
        )
    except RuntimeError:
        service.rollback_prototype_generation(
            project_name, staging_path, new_scene_ids, old_script, round_id=round_id,
        )

    # Index should not contain new scene entries
    index = pm.read_project_index(project_name)
    scene_map = index.get("scenes", {}) if index else {}
    for sid in new_scene_ids:
        assert sid not in scene_map, f"Scene {sid} should not be in index after rollback"

    # No staging assets should exist
    staging_dir = tmp_path / project_name / "game" / "__staging__" / round_id
    assert not staging_dir.exists(), "Staging dir should be gone"


@pytest.mark.asyncio
async def test_write_script_shows_renderable_sprite_when_asset_exists_only_in_staging(
    client: TestClient, tmp_path: Path
) -> None:
    """Pre-commit script generation must still emit show statements for staging-only sprites."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_stage_show"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    staging_sprite = tmp_path / project_name / "game" / "__staging__" / "rshow" / "images" / "character" / "bob_normalized.png"
    staging_sprite.parent.mkdir(parents=True, exist_ok=True)
    staging_sprite.write_bytes(b"fake")

    char_assets = {
        "Bob": {
            "path": "game/images/character/bob_normalized.png",
            "staging_path": "game/__staging__/rshow/images/character/bob_normalized.png",
            "placeholder": False,
            "renderable": True,
            "renderable_reason": "ok",
        }
    }
    service.build_sprite_plan(scenes, char_assets, project_name=project_name)

    staging_script_path = service.write_script(
        project_name,
        chapter,
        scenes,
        character_assets=char_assets,
    )

    script_path = tmp_path / project_name / staging_script_path
    script_text = script_path.read_text(encoding="utf-8")
    assert "show Bob_neutral at proto_right_duo" in script_text


@pytest.mark.asyncio
async def test_update_index_uses_final_paths_when_assets_exist_only_in_staging(
    client: TestClient, tmp_path: Path
) -> None:
    """Index should persist final project-relative paths even before staged assets are promoted."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "proto_stage_index"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = blueprint.chapters[0]
    scenes = await service.generate_scenes(chapter, blueprint)

    staging_bg = tmp_path / project_name / "game" / "__staging__" / "rindex" / "images" / "background" / "bg_proto-ch1-s1.png"
    staging_bg.parent.mkdir(parents=True, exist_ok=True)
    staging_bg.write_bytes(b"fakebg")

    staging_sprite = tmp_path / project_name / "game" / "__staging__" / "rindex" / "images" / "character" / "bob_normalized.png"
    staging_sprite.parent.mkdir(parents=True, exist_ok=True)
    staging_sprite.write_bytes(b"fakesprite")

    bg_assets = {
        "proto-ch1-s1": {
            "path": "game/images/background/bg_proto-ch1-s1.png",
            "staging_path": "game/__staging__/rindex/images/background/bg_proto-ch1-s1.png",
            "placeholder": False,
            "source": "image_service",
        }
    }
    char_assets = {
        "Bob": {
            "path": "game/images/character/bob_normalized.png",
            "staging_path": "game/__staging__/rindex/images/character/bob_normalized.png",
            "placeholder": False,
            "renderable": True,
            "renderable_reason": "ok",
        }
    }
    service.build_sprite_plan(scenes, char_assets, project_name=project_name)

    service.update_index(
        project_name,
        chapter,
        scenes,
        "game/prototype_ch1_Chapter1.rpy",
        background_assets=bg_assets,
        character_assets=char_assets,
    )

    index = pm.read_project_index(project_name)
    assert index["scenes"]["proto-ch1-s1"]["background_asset_path"] == "game/images/background/bg_proto-ch1-s1.png"
    assert index["character_assets"]["Bob"]["path"] == "game/images/character/bob_normalized.png"
    sprite_plan_item = next(
        sp for sp in index["scenes"]["proto-ch1-s1"]["sprite_plan"] if sp["character_name"] == "Bob"
    )
    assert sprite_plan_item["sprite_path"] == "game/images/character/bob_normalized.png"
    assert "sprite_check_path" not in sprite_plan_item
