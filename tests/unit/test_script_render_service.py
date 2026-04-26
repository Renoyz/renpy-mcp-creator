"""Unit tests for ScriptRenderService — extracted from PrototypeGenerationService.

These tests verify the Ren'Py .rpy script rendering logic in isolation,
without needing a full FastAPI client or real LLM provider.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from renpy_mcp.blueprint.models import ChapterSummary
from renpy_mcp.services.prototype_generation_service import PrototypeScene


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chapter() -> ChapterSummary:
    return ChapterSummary(
        id="ch1",
        name="Chapter One",
        order=1,
        scenes=[{"id": "s1", "name": "Opening", "order": 1}],
    )


def _make_scenes() -> list[PrototypeScene]:
    return [
        PrototypeScene(
            scene_id="proto-ch1-s1",
            title="First Meeting",
            summary="Hero meets friend at the library.",
            location="library",
            location_visual_brief="quiet university library, warm light",
            mood="warm",
            characters_present=["Hero", "Friend"],
            dialogue_beats=[
                {"speaker": "Hero", "intent": "greeting", "content_brief": "Hello there!"},
                {"speaker": "Friend", "intent": "response", "content_brief": "Nice to meet you."},
            ],
            entry_label="prototype_ch1_start",
            next_scene_id="proto-ch1-s2",
        ),
        PrototypeScene(
            scene_id="proto-ch1-s2",
            title="Late Talk",
            summary="They talk late into the night.",
            location="cafe",
            location_visual_brief="cozy night cafe, dim lights",
            mood="reflective",
            characters_present=["Hero", "Friend"],
            dialogue_beats=[
                {"speaker": "Hero", "intent": "question", "content_brief": "What do you think about this?"},
                {"speaker": "Friend", "intent": "explain", "content_brief": "I think we should try."},
            ],
            entry_label="prototype_ch1_scene2",
            next_scene_id=None,
        ),
    ]


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------

class TestScriptRenderServiceImport:
    def test_can_import_class(self):
        from renpy_mcp.services.script_render_service import ScriptRenderService
        assert ScriptRenderService is not None

    def test_can_instantiate_with_project_manager(self, tmp_path: Path, monkeypatch):
        from renpy_mcp.services.script_render_service import ScriptRenderService
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "workspace", tmp_path)
        pm = ProjectManager(settings)
        service = ScriptRenderService(pm)
        assert service.pm is pm


# ---------------------------------------------------------------------------
# Character registry
# ---------------------------------------------------------------------------

class TestBuildCharacterRegistry:
    def test_maps_display_names_to_safe_ids(self):
        from renpy_mcp.services.script_render_service import ScriptRenderService

        service = ScriptRenderService(pm=None)
        scenes = _make_scenes()
        registry = service.build_character_registry(scenes)
        assert "Hero" in registry
        assert "Friend" in registry
        assert registry["Hero"].isidentifier()
        assert registry["Friend"].isidentifier()

    def test_handles_cjk_character_names(self):
        from renpy_mcp.services.script_render_service import ScriptRenderService

        service = ScriptRenderService(pm=None)
        scenes = [
            PrototypeScene(
                scene_id="s1",
                title="Test",
                summary="Test",
                location="room",
                location_visual_brief="a room",
                mood="neutral",
                characters_present=["主角", "配角"],
                dialogue_beats=[],
                entry_label="test_start",
                next_scene_id=None,
            ),
        ]
        registry = service.build_character_registry(scenes)
        assert len(registry) == 2
        for safe_id in registry.values():
            assert safe_id.isidentifier()

    def test_deduplicates_across_scenes(self):
        from renpy_mcp.services.script_render_service import ScriptRenderService

        service = ScriptRenderService(pm=None)
        scenes = _make_scenes()  # Hero and Friend appear in both scenes
        registry = service.build_character_registry(scenes)
        assert len(registry) == 2


# ---------------------------------------------------------------------------
# CJK runtime override lines
# ---------------------------------------------------------------------------

class TestCjkRuntimeOverrideLines:
    def test_returns_non_empty_lines(self):
        from renpy_mcp.services.script_render_service import ScriptRenderService

        service = ScriptRenderService(pm=None)
        lines = service.cjk_runtime_override_lines()
        assert isinstance(lines, list)
        assert len(lines) > 0

    def test_includes_init_python(self):
        from renpy_mcp.services.script_render_service import ScriptRenderService

        service = ScriptRenderService(pm=None)
        lines = service.cjk_runtime_override_lines()
        assert any("init python" in line for line in lines)

    def test_includes_font_replacement_map(self):
        from renpy_mcp.services.script_render_service import ScriptRenderService

        service = ScriptRenderService(pm=None)
        lines = service.cjk_runtime_override_lines()
        assert any("font_replacement_map" in line for line in lines)


# ---------------------------------------------------------------------------
# write_script — core rendering
# ---------------------------------------------------------------------------

class TestWriteScript:
    @pytest.fixture
    def project_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Set up a minimal project environment for write_script tests."""
        from renpy_mcp.config import get_settings
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.services.script_render_service import ScriptRenderService

        settings = get_settings()
        monkeypatch.setattr(settings, "workspace", tmp_path)
        pm = ProjectManager(settings)

        project_name = "test_project"
        game_dir = tmp_path / project_name / "game"
        game_dir.mkdir(parents=True)
        (game_dir / "script.rpy").write_text(
            'label start:\n    "Hello."\n    return\n', encoding="utf-8"
        )

        service = ScriptRenderService(pm)
        return service, project_name, tmp_path

    def test_returns_staging_path(self, project_env):
        service, project_name, tmp_path = project_env
        chapter = _make_chapter()
        scenes = _make_scenes()
        service.build_sprite_plan(scenes, {})

        result = service.write_script(project_name, chapter, scenes)
        assert "__staging__" in result
        assert result.endswith(".rpy")

    def test_staging_file_is_created_on_disk(self, project_env):
        service, project_name, tmp_path = project_env
        chapter = _make_chapter()
        scenes = _make_scenes()
        service.build_sprite_plan(scenes, {})

        staging_path = service.write_script(project_name, chapter, scenes)
        staging_file = tmp_path / project_name / staging_path
        assert staging_file.exists()

    def test_script_contains_character_definitions(self, project_env):
        service, project_name, tmp_path = project_env
        chapter = _make_chapter()
        scenes = _make_scenes()
        service.build_sprite_plan(scenes, {})

        staging_path = service.write_script(project_name, chapter, scenes)
        content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")
        assert "define " in content
        assert 'Character("' in content

    def test_script_contains_scene_labels(self, project_env):
        service, project_name, tmp_path = project_env
        chapter = _make_chapter()
        scenes = _make_scenes()
        service.build_sprite_plan(scenes, {})

        staging_path = service.write_script(project_name, chapter, scenes)
        content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")
        assert "label prototype_ch1_start:" in content
        assert "label prototype_ch1_scene2:" in content

    def test_script_contains_dialogue_lines(self, project_env):
        service, project_name, tmp_path = project_env
        chapter = _make_chapter()
        scenes = _make_scenes()
        service.build_sprite_plan(scenes, {})

        staging_path = service.write_script(project_name, chapter, scenes)
        content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")
        assert "Hello there!" in content
        assert "Nice to meet you." in content

    def test_script_uses_safe_ids_not_display_names_for_say(self, project_env):
        service, project_name, tmp_path = project_env
        chapter = _make_chapter()
        scenes = _make_scenes()
        service.build_sprite_plan(scenes, {})

        staging_path = service.write_script(project_name, chapter, scenes)
        content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")
        # The dialogue lines should use safe ids, not raw names like 'Hero "Hello"'
        lines = content.splitlines()
        say_lines = [l.strip() for l in lines if '"Hello there!"' in l]
        assert len(say_lines) == 1
        # Should NOT start with raw display name
        assert not say_lines[0].startswith('"')

    def test_last_scene_ends_with_return(self, project_env):
        service, project_name, tmp_path = project_env
        chapter = _make_chapter()
        scenes = _make_scenes()
        service.build_sprite_plan(scenes, {})

        staging_path = service.write_script(project_name, chapter, scenes)
        content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")
        assert "return" in content

    def test_scene_uses_placeholder_when_no_background_assets(self, project_env):
        service, project_name, tmp_path = project_env
        chapter = _make_chapter()
        scenes = _make_scenes()
        service.build_sprite_plan(scenes, {})

        staging_path = service.write_script(project_name, chapter, scenes)
        content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")
        assert "scene black" in content

    def test_does_not_define_label_start(self, project_env):
        """write_script must NOT define label start — main script owns it."""
        service, project_name, tmp_path = project_env
        chapter = _make_chapter()
        scenes = _make_scenes()
        service.build_sprite_plan(scenes, {})

        staging_path = service.write_script(project_name, chapter, scenes)
        content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")
        assert "label start:" not in content

    def test_jump_chains_between_scenes(self, project_env):
        service, project_name, tmp_path = project_env
        chapter = _make_chapter()
        scenes = _make_scenes()
        service.build_sprite_plan(scenes, {})

        staging_path = service.write_script(project_name, chapter, scenes)
        content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")
        assert "jump prototype_ch1_scene2" in content

    def test_script_escapes_special_characters(self, project_env):
        service, project_name, tmp_path = project_env
        chapter = _make_chapter()
        scenes = [
            PrototypeScene(
                scene_id="s1",
                title="Test",
                summary='He said "hello" and left.',
                location="room",
                location_visual_brief="a room",
                mood="neutral",
                characters_present=[],
                dialogue_beats=[],
                entry_label="test_start",
                next_scene_id=None,
            ),
        ]
        scenes[0].sprite_plan = []

        staging_path = service.write_script(project_name, chapter, scenes)
        content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")
        # Quotes inside strings must be escaped
        assert '\\"hello\\"' in content

    def test_next_chapter_start_label_chains_chapters(self, project_env):
        service, project_name, tmp_path = project_env
        chapter = _make_chapter()
        scenes = _make_scenes()
        service.build_sprite_plan(scenes, {})

        staging_path = service.write_script(
            project_name, chapter, scenes,
            next_chapter_start_label="prototype_ch2_start",
        )
        content = (tmp_path / project_name / staging_path).read_text(encoding="utf-8")
        assert "jump prototype_ch2_start" in content


# ---------------------------------------------------------------------------
# build_sprite_plan
# ---------------------------------------------------------------------------

class TestBuildSpritePlan:
    def test_assigns_sprite_plan_to_scenes(self):
        from renpy_mcp.services.script_render_service import ScriptRenderService

        service = ScriptRenderService(pm=None)
        scenes = _make_scenes()
        service.build_sprite_plan(scenes, {})

        for scene in scenes:
            assert hasattr(scene, "sprite_plan")
            assert isinstance(scene.sprite_plan, list)

    def test_solo_layout_for_single_character(self):
        from renpy_mcp.services.script_render_service import ScriptRenderService

        service = ScriptRenderService(pm=None)
        scenes = [
            PrototypeScene(
                scene_id="s1",
                title="Solo",
                summary="Solo scene",
                location="room",
                location_visual_brief="a room",
                mood="neutral",
                characters_present=["Hero"],
                dialogue_beats=[],
                entry_label="test_start",
                next_scene_id=None,
            ),
        ]
        service.build_sprite_plan(scenes, {})
        assert len(scenes[0].sprite_plan) == 1
        assert scenes[0].sprite_plan[0].layout_mode == "solo"

    def test_duo_layout_for_two_characters(self):
        from renpy_mcp.services.script_render_service import ScriptRenderService

        service = ScriptRenderService(pm=None)
        scenes = _make_scenes()  # 2 characters
        service.build_sprite_plan(scenes, {})
        assert scenes[0].sprite_plan[0].layout_mode == "duo"

    def test_trio_layout_for_three_plus_characters(self):
        from renpy_mcp.services.script_render_service import ScriptRenderService

        service = ScriptRenderService(pm=None)
        scenes = [
            PrototypeScene(
                scene_id="s1",
                title="Trio",
                summary="Trio scene",
                location="room",
                location_visual_brief="a room",
                mood="neutral",
                characters_present=["A", "B", "C"],
                dialogue_beats=[],
                entry_label="test_start",
                next_scene_id=None,
            ),
        ]
        service.build_sprite_plan(scenes, {})
        assert scenes[0].sprite_plan[0].layout_mode == "trio"

    def test_placeholder_sprites_are_not_renderable(self):
        from renpy_mcp.services.script_render_service import ScriptRenderService

        service = ScriptRenderService(pm=None)
        scenes = _make_scenes()
        service.build_sprite_plan(scenes, {})  # no real assets
        for sp in scenes[0].sprite_plan:
            assert sp.sprite_renderable is False
