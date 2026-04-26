"""Unit tests for AssetGenerationService (TDD Red -> Green).

Tests cover:
- Import / instantiation
- _runtime_asset_relpath: staging path rewriting
- _assess_background_composition: PIL edge detection quality gate
- _generate_placeholder_background / _generate_placeholder_character: PIL fallbacks
- generate_background_assets: placeholder path when ImageService unavailable
- generate_character_assets: placeholder path when ImageService unavailable
- ensure_cjk_font_config: font copy + config file writeback
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_workspace(tmp_path: Path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture()
def pm(tmp_workspace: Path, monkeypatch):
    from renpy_mcp.config import get_settings
    from renpy_mcp.services.project_manager import ProjectManager

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_workspace)
    return ProjectManager(settings)


@pytest.fixture()
def project_env(pm, tmp_workspace: Path):
    project_name = "test_proj"
    project_dir = tmp_workspace / project_name
    game_dir = project_dir / "game"
    game_dir.mkdir(parents=True)
    (project_dir / "meta").mkdir(parents=True)
    (game_dir / "script.rpy").write_text(
        'label start:\n    "Hello from the Ren\'Py MCP server!"\n    return\n',
        encoding="utf-8",
    )
    return project_name, project_dir


def _make_scene(scene_id: str = "ch1-s1", **overrides):
    from renpy_mcp.services.prototype_generation_service import PrototypeScene
    from renpy_mcp.blueprint.models import DialogueBeat

    defaults = dict(
        scene_id=scene_id,
        title="Opening",
        summary="Alice meets Bob.",
        location="library",
        location_visual_brief="a quiet library with tall shelves",
        mood="calm",
        characters_present=["Alice", "Bob"],
        dialogue_beats=[
            DialogueBeat(
                speaker="Alice",
                intent="greet",
                content_brief="says hello",
                spoken_line="Hello, Bob!",
            ),
        ],
        sprite_plan=[],
        entry_label="prototype_ch1_start",
        next_scene_id=None,
    )
    defaults.update(overrides)
    return PrototypeScene(**defaults)


def _make_blueprint():
    from renpy_mcp.blueprint.models import (
        BlueprintCharacter,
        ChapterSummary,
        ProjectBlueprint,
    )
    return ProjectBlueprint(
        title="Test VN",
        genre="Fantasy",
        worldview="Magical realm",
        themes=["adventure"],
        characters=[
            BlueprintCharacter(
                name="Alice",
                role="protagonist",
                personality="brave",
                appearance="blue hair",
            ),
        ],
        chapters=[
            ChapterSummary(id="ch1", name="Chapter 1", order=1, scenes=[]),
        ],
        art_style="anime visual novel style",
    )


# ===========================================================================
# Tests
# ===========================================================================


class TestImport:
    def test_can_import(self):
        from renpy_mcp.services.asset_generation_service import AssetGenerationService
        assert AssetGenerationService is not None

    def test_can_instantiate(self, pm):
        from renpy_mcp.services.asset_generation_service import AssetGenerationService
        svc = AssetGenerationService(pm=pm)
        assert svc.pm is pm

    def test_accepts_script_renderer(self, pm):
        from renpy_mcp.services.asset_generation_service import AssetGenerationService
        from renpy_mcp.services.script_render_service import ScriptRenderService

        renderer = ScriptRenderService(pm)
        svc = AssetGenerationService(pm=pm, script_renderer=renderer)
        assert svc._script_renderer is renderer


class TestRuntimeAssetRelpath:
    def test_simple_path(self, pm, project_env):
        from renpy_mcp.services.asset_generation_service import AssetGenerationService

        svc = AssetGenerationService(pm=pm)
        project_dir = project_env[1]
        asset_path = project_dir / "game" / "images" / "background" / "bg_s1.png"
        result = svc._runtime_asset_relpath(project_dir, asset_path)
        assert result == "game/images/background/bg_s1.png"

    def test_staging_path_rewritten(self, pm, project_env):
        from renpy_mcp.services.asset_generation_service import AssetGenerationService

        svc = AssetGenerationService(pm=pm)
        project_dir = project_env[1]
        asset_path = project_dir / "game" / "__staging__" / "round1" / "images" / "background" / "bg_s1.png"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        result = svc._runtime_asset_relpath(project_dir, asset_path, round_id="round1")
        assert result == "game/images/background/bg_s1.png"


class TestAssessBackgroundComposition:
    def test_returns_ok_for_simple_image(self, pm, tmp_path):
        """A plain-color image should pass the composition gate."""
        from PIL import Image
        from renpy_mcp.services.asset_generation_service import AssetGenerationService

        svc = AssetGenerationService(pm=pm)
        img = Image.new("RGB", (1280, 720), color=(30, 30, 50))
        img_path = tmp_path / "bg_test.png"
        img.save(img_path, "PNG")

        passes, reason = svc._assess_background_composition(img_path)
        assert passes is True
        assert reason == "ok"

    def test_returns_ok_on_missing_file(self, pm, tmp_path):
        """Missing file should still pass (fail-safe)."""
        from renpy_mcp.services.asset_generation_service import AssetGenerationService

        svc = AssetGenerationService(pm=pm)
        passes, reason = svc._assess_background_composition(tmp_path / "nope.png")
        assert passes is True
        assert reason == "ok"


class TestPlaceholderGeneration:
    def test_placeholder_background_creates_file(self, pm, tmp_path):
        from renpy_mcp.services.asset_generation_service import AssetGenerationService

        svc = AssetGenerationService(pm=pm)
        scene = _make_scene()
        out = tmp_path / "bg_placeholder.png"
        svc._generate_placeholder_background(out, scene)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_placeholder_character_creates_file(self, pm, tmp_path):
        from renpy_mcp.services.asset_generation_service import AssetGenerationService

        svc = AssetGenerationService(pm=pm)
        out = tmp_path / "char_placeholder.png"
        svc._generate_placeholder_character(out, "Alice")
        assert out.exists()
        assert out.stat().st_size > 0


class TestGenerateBackgroundAssets:
    """generate_background_assets falls back to PIL placeholder when ImageService is unavailable."""

    def test_requires_pm(self):
        from renpy_mcp.services.asset_generation_service import AssetGenerationService

        svc = AssetGenerationService(pm=None)
        scene = _make_scene()
        with pytest.raises(RuntimeError, match="ProjectManager"):
            asyncio.get_event_loop().run_until_complete(
                svc.generate_background_assets("proj", [scene])
            )

    def test_produces_placeholder_without_image_service(self, pm, project_env):
        from renpy_mcp.services.asset_generation_service import AssetGenerationService

        svc = AssetGenerationService(pm=pm)
        scene = _make_scene()
        result = asyncio.get_event_loop().run_until_complete(
            svc.generate_background_assets(project_env[0], [scene])
        )
        assert scene.scene_id in result
        entry = result[scene.scene_id]
        assert entry["placeholder"] is True
        assert entry["source"] in ("pil_fallback", "none")

    def test_background_file_created(self, pm, project_env):
        from renpy_mcp.services.asset_generation_service import AssetGenerationService

        svc = AssetGenerationService(pm=pm)
        scene = _make_scene()
        result = asyncio.get_event_loop().run_until_complete(
            svc.generate_background_assets(project_env[0], [scene])
        )
        entry = result[scene.scene_id]
        if entry["source"] == "pil_fallback":
            # Check file was actually written
            project_dir = project_env[1]
            bg_dir = project_dir / "game" / "images" / "background"
            assert (bg_dir / f"bg_{scene.scene_id}.png").exists()


class TestGenerateCharacterAssets:
    def test_requires_pm(self):
        from renpy_mcp.services.asset_generation_service import AssetGenerationService

        svc = AssetGenerationService(pm=None)
        bp = _make_blueprint()
        scene = _make_scene(characters_present=["Alice"])
        with pytest.raises(RuntimeError, match="ProjectManager"):
            asyncio.get_event_loop().run_until_complete(
                svc.generate_character_assets("proj", bp, [scene])
            )

    def test_produces_placeholder_without_image_service(self, pm, project_env):
        from renpy_mcp.services.asset_generation_service import AssetGenerationService
        from renpy_mcp.services.script_render_service import ScriptRenderService

        renderer = ScriptRenderService(pm)
        svc = AssetGenerationService(pm=pm, script_renderer=renderer)
        bp = _make_blueprint()
        scene = _make_scene(characters_present=["Alice"])
        result = asyncio.get_event_loop().run_until_complete(
            svc.generate_character_assets(project_env[0], bp, [scene])
        )
        assert "Alice" in result
        entry = result["Alice"]
        assert entry["placeholder"] is True
        assert entry["renderable"] is False


class TestEnsureCjkFontConfig:
    def test_requires_pm(self):
        from renpy_mcp.services.asset_generation_service import AssetGenerationService

        svc = AssetGenerationService(pm=None)
        with pytest.raises(RuntimeError, match="ProjectManager"):
            svc.ensure_cjk_font_config("proj")

    def test_writes_config_file(self, pm, project_env):
        from renpy_mcp.services.asset_generation_service import AssetGenerationService
        from renpy_mcp.services.script_render_service import ScriptRenderService

        renderer = ScriptRenderService(pm)
        svc = AssetGenerationService(pm=pm, script_renderer=renderer)
        result = svc.ensure_cjk_font_config(project_env[0])
        assert "config_path" in result
        assert "configured" in result
        # Config file should exist regardless of font availability
        config_file = project_env[1] / result["config_path"]
        assert config_file.exists()

    def test_returns_configured_status(self, pm, project_env):
        from renpy_mcp.services.asset_generation_service import AssetGenerationService
        from renpy_mcp.services.script_render_service import ScriptRenderService

        renderer = ScriptRenderService(pm)
        svc = AssetGenerationService(pm=pm, script_renderer=renderer)
        result = svc.ensure_cjk_font_config(project_env[0])
        assert isinstance(result["configured"], bool)
        # font_path is str when font found, None otherwise
        assert result["font_path"] is None or isinstance(result["font_path"], str)
