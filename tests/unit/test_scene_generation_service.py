"""Unit tests for SceneGenerationService (TDD Red → Green).

Tests cover:
- Import / instantiation
- _validate_scene_consistency: speaker filtering, fallbacks
- generate_scenes: LLM call + retry + JSON parse
- generate_all_chapter_scenes: multi-chapter orchestration
- build_generation_contract: contract assembly
- infer helpers: style bible + chapter profiles
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

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
def pm(tmp_workspace: Path):
    from renpy_mcp.config import get_settings
    from renpy_mcp.services.project_manager import ProjectManager

    settings = get_settings()
    settings.workspace = tmp_workspace
    return ProjectManager(settings)


@pytest.fixture()
def project_env(pm, tmp_workspace: Path):
    """Create a minimal project directory for tests."""
    project_name = "test_proj"
    project_dir = tmp_workspace / project_name
    game_dir = project_dir / "game"
    game_dir.mkdir(parents=True)
    meta_dir = project_dir / "meta"
    meta_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text(
        'label start:\n    "Hello from the Ren\'Py MCP server!"\n    return\n',
        encoding="utf-8",
    )
    return project_name, project_dir


def _make_blueprint(chapter_count: int = 1):
    """Return a minimal ProjectBlueprint for testing."""
    from renpy_mcp.blueprint.models import (
        BlueprintCharacter,
        ChapterSummary,
        ProjectBlueprint,
    )

    chapters = [
        ChapterSummary(
            id=f"ch{i+1}",
            name=f"Chapter {i+1}",
            order=i + 1,
            scenes=[],
        )
        for i in range(chapter_count)
    ]
    return ProjectBlueprint(
        title="Test VN",
        genre="Fantasy",
        worldview="Magical realm",
        themes=["adventure", "friendship"],
        characters=[
            BlueprintCharacter(
                name="Alice",
                role="protagonist",
                personality="brave",
                appearance="blue hair",
            ),
            BlueprintCharacter(
                name="Bob",
                role="antagonist",
                personality="cunning",
                appearance="black cloak",
            ),
        ],
        chapters=chapters,
        art_style="anime visual novel style",
    )


def _make_scene(scene_id: str = "ch1-s1", **overrides):
    """Build a PrototypeScene with sensible defaults."""
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
            DialogueBeat(
                speaker="Bob",
                intent="respond",
                content_brief="greets back",
                spoken_line="Hi Alice.",
            ),
        ],
        sprite_plan=[],
        entry_label="prototype_ch1_start",
        next_scene_id=None,
    )
    defaults.update(overrides)
    return PrototypeScene(**defaults)


def _fake_llm_response(scenes_data: list[dict]):
    """Create a fake LLM response object with .text attribute."""
    resp = MagicMock()
    resp.text = json.dumps(scenes_data)
    return resp


# ===========================================================================
# Tests
# ===========================================================================


class TestImport:
    def test_can_import_scene_generation_service(self):
        from renpy_mcp.services.scene_generation_service import SceneGenerationService
        assert SceneGenerationService is not None

    def test_can_instantiate(self, pm):
        from renpy_mcp.services.scene_generation_service import SceneGenerationService
        svc = SceneGenerationService(pm=pm, provider=None)
        assert svc.pm is pm
        assert svc.provider is None


class TestValidateSceneConsistency:
    """_validate_scene_consistency auto-corrects scenes in-place."""

    def test_filters_invalid_speakers(self):
        from renpy_mcp.services.scene_generation_service import SceneGenerationService
        from renpy_mcp.blueprint.models import DialogueBeat

        svc = SceneGenerationService(pm=None, provider=None)
        scene = _make_scene(
            characters_present=["Alice"],
            dialogue_beats=[
                DialogueBeat(speaker="Alice", intent="x", content_brief="x", spoken_line="Hi"),
                DialogueBeat(speaker="Eve", intent="x", content_brief="x", spoken_line="Bye"),
            ],
        )
        svc._validate_scene_consistency([scene])
        assert len(scene.dialogue_beats) == 1
        assert scene.dialogue_beats[0].speaker == "Alice"

    def test_location_visual_brief_fallback(self):
        from renpy_mcp.services.scene_generation_service import SceneGenerationService

        svc = SceneGenerationService(pm=None, provider=None)
        scene = _make_scene(location="cafe", location_visual_brief="  ")
        svc._validate_scene_consistency([scene])
        assert scene.location_visual_brief == "cafe"

    def test_mood_fallback(self):
        from renpy_mcp.services.scene_generation_service import SceneGenerationService

        svc = SceneGenerationService(pm=None, provider=None)
        scene = _make_scene(mood="  ")
        svc._validate_scene_consistency([scene])
        assert scene.mood == "neutral"


class TestGenerateScenes:
    """generate_scenes makes LLM call, parses JSON, validates."""

    def test_raises_without_provider(self):
        from renpy_mcp.services.scene_generation_service import SceneGenerationService

        svc = SceneGenerationService(pm=None, provider=None)
        blueprint = _make_blueprint()
        chapter = blueprint.chapters[0]
        with pytest.raises(RuntimeError, match="No LLM provider"):
            asyncio.get_event_loop().run_until_complete(
                svc.generate_scenes(chapter, blueprint)
            )

    def test_returns_scenes_on_valid_response(self):
        from renpy_mcp.services.scene_generation_service import SceneGenerationService

        provider = MagicMock()
        scene_data = [
            {
                "scene_id": "ch1-s1",
                "title": "Opening",
                "summary": "Introduction",
                "location": "library",
                "location_visual_brief": "quiet library",
                "mood": "calm",
                "characters_present": ["Alice"],
                "dialogue_beats": [
                    {
                        "speaker": "Alice",
                        "intent": "greet",
                        "content_brief": "says hello",
                        "spoken_line": "Hello!",
                    }
                ],
                "entry_label": "prototype_ch1_start",
                "next_scene_id": None,
            },
        ]
        provider.chat.return_value = _fake_llm_response(scene_data)

        svc = SceneGenerationService(pm=None, provider=provider)
        blueprint = _make_blueprint()
        chapter = blueprint.chapters[0]

        scenes = asyncio.get_event_loop().run_until_complete(
            svc.generate_scenes(chapter, blueprint)
        )
        assert len(scenes) == 1
        assert scenes[0].scene_id == "ch1-s1"
        # entry_label should be overridden by post-processing
        assert scenes[0].entry_label == "prototype_ch1_start"

    def test_retries_on_json_error(self):
        from renpy_mcp.services.scene_generation_service import SceneGenerationService

        provider = MagicMock()
        bad_resp = MagicMock()
        bad_resp.text = "NOT JSON"

        good_data = [
            {
                "scene_id": "ch1-s1",
                "title": "T",
                "summary": "S",
                "location": "L",
                "location_visual_brief": "V",
                "mood": "calm",
                "characters_present": [],
                "dialogue_beats": [],
                "entry_label": "prototype_ch1_start",
                "next_scene_id": None,
            },
        ]
        good_resp = _fake_llm_response(good_data)
        provider.chat.side_effect = [bad_resp, good_resp]

        svc = SceneGenerationService(pm=None, provider=provider)
        blueprint = _make_blueprint()
        chapter = blueprint.chapters[0]

        scenes = asyncio.get_event_loop().run_until_complete(
            svc.generate_scenes(chapter, blueprint)
        )
        assert len(scenes) == 1
        assert provider.chat.call_count == 2

    def test_raises_after_max_retries(self):
        from renpy_mcp.services.scene_generation_service import SceneGenerationService

        provider = MagicMock()
        bad_resp = MagicMock()
        bad_resp.text = "NOT JSON"
        provider.chat.return_value = bad_resp

        svc = SceneGenerationService(pm=None, provider=provider)
        blueprint = _make_blueprint()
        chapter = blueprint.chapters[0]

        with pytest.raises(RuntimeError, match="failed after"):
            asyncio.get_event_loop().run_until_complete(
                svc.generate_scenes(chapter, blueprint)
            )
        assert provider.chat.call_count == 3  # initial + 2 retries

    def test_entry_labels_overridden_to_chapter_id(self):
        """Even if LLM returns wrong labels, they get corrected."""
        from renpy_mcp.services.scene_generation_service import SceneGenerationService

        provider = MagicMock()
        scene_data = [
            {
                "scene_id": "ch2-s1",
                "title": "T1",
                "summary": "S1",
                "location": "L",
                "location_visual_brief": "V",
                "mood": "m",
                "characters_present": [],
                "dialogue_beats": [],
                "entry_label": "prototype_ch1_start",  # Wrong label!
                "next_scene_id": "ch2-s2",
            },
            {
                "scene_id": "ch2-s2",
                "title": "T2",
                "summary": "S2",
                "location": "L",
                "location_visual_brief": "V",
                "mood": "m",
                "characters_present": [],
                "dialogue_beats": [],
                "entry_label": "prototype_ch1_scene_2",  # Wrong label!
                "next_scene_id": None,
            },
        ]
        provider.chat.return_value = _fake_llm_response(scene_data)

        svc = SceneGenerationService(pm=None, provider=provider)
        blueprint = _make_blueprint(chapter_count=2)
        chapter = blueprint.chapters[1]  # ch2

        scenes = asyncio.get_event_loop().run_until_complete(
            svc.generate_scenes(chapter, blueprint)
        )
        assert scenes[0].entry_label == "prototype_ch2_start"
        assert scenes[1].entry_label == "prototype_ch2_scene_2"

    def test_markdown_code_block_stripped(self):
        """LLM response wrapped in ```json ... ``` still parses."""
        from renpy_mcp.services.scene_generation_service import SceneGenerationService

        provider = MagicMock()
        scene_data = [
            {
                "scene_id": "ch1-s1",
                "title": "T",
                "summary": "S",
                "location": "L",
                "location_visual_brief": "V",
                "mood": "m",
                "characters_present": [],
                "dialogue_beats": [],
                "entry_label": "x",
                "next_scene_id": None,
            },
        ]
        wrapped = "```json\n" + json.dumps(scene_data) + "\n```"
        resp = MagicMock()
        resp.text = wrapped
        provider.chat.return_value = resp

        svc = SceneGenerationService(pm=None, provider=provider)
        bp = _make_blueprint()
        scenes = asyncio.get_event_loop().run_until_complete(
            svc.generate_scenes(bp.chapters[0], bp)
        )
        assert len(scenes) == 1


class TestGenerateAllChapterScenes:
    """generate_all_chapter_scenes orchestrates per-chapter generation."""

    def test_raises_without_provider(self, pm, project_env):
        from renpy_mcp.services.scene_generation_service import SceneGenerationService

        svc = SceneGenerationService(pm=pm, provider=None)
        bp = _make_blueprint()

        with pytest.raises(RuntimeError, match="No LLM provider"):
            asyncio.get_event_loop().run_until_complete(
                svc.generate_all_chapter_scenes(project_env[0], bp)
            )

    def test_returns_scenes_per_chapter(self, pm, project_env):
        from renpy_mcp.services.scene_generation_service import SceneGenerationService

        provider = MagicMock()

        def fake_chat(**kwargs):
            return _fake_llm_response([
                {
                    "scene_id": "s1",
                    "title": "T",
                    "summary": "S",
                    "location": "L",
                    "location_visual_brief": "V",
                    "mood": "m",
                    "characters_present": [],
                    "dialogue_beats": [],
                    "entry_label": "x",
                    "next_scene_id": None,
                }
            ])

        provider.chat.side_effect = fake_chat

        svc = SceneGenerationService(pm=pm, provider=provider)
        bp = _make_blueprint(chapter_count=2)

        result = asyncio.get_event_loop().run_until_complete(
            svc.generate_all_chapter_scenes(project_env[0], bp)
        )
        assert "ch1" in result
        assert "ch2" in result
        assert len(result["ch1"]) == 1
        assert len(result["ch2"]) == 1

    def test_persists_scene_packages(self, pm, project_env):
        """Scene packages are written to meta/scene_packages.json."""
        from renpy_mcp.services.scene_generation_service import SceneGenerationService

        provider = MagicMock()
        provider.chat.return_value = _fake_llm_response([
            {
                "scene_id": "ch1-s1",
                "title": "T",
                "summary": "S",
                "location": "L",
                "location_visual_brief": "V",
                "mood": "m",
                "characters_present": [],
                "dialogue_beats": [],
                "entry_label": "x",
                "next_scene_id": None,
            }
        ])

        svc = SceneGenerationService(pm=pm, provider=provider)
        bp = _make_blueprint(chapter_count=1)
        asyncio.get_event_loop().run_until_complete(
            svc.generate_all_chapter_scenes(project_env[0], bp)
        )

        snapshot = pm.read_scene_packages(project_env[0])
        assert snapshot is not None
        assert len(snapshot.chapters) == 1
        assert snapshot.chapters[0].chapter_id == "ch1"


class TestBuildGenerationContract:
    """build_generation_contract assembles style contracts."""

    def test_returns_generation_contract(self, pm, project_env):
        from renpy_mcp.services.scene_generation_service import SceneGenerationService
        from renpy_mcp.blueprint.models import GenerationContract

        svc = SceneGenerationService(pm=pm, provider=None)
        bp = _make_blueprint()
        chapter = bp.chapters[0]

        contract = svc.build_generation_contract(project_env[0], bp, chapter)
        assert isinstance(contract, GenerationContract)
        assert contract.visual_contract is not None
        assert contract.tone_contract is not None

    def test_uses_inferred_defaults_when_no_bible(self, pm, project_env):
        from renpy_mcp.services.scene_generation_service import SceneGenerationService

        svc = SceneGenerationService(pm=pm, provider=None)
        bp = _make_blueprint()
        chapter = bp.chapters[0]

        contract = svc.build_generation_contract(project_env[0], bp, chapter)
        # Should not raise and should have sensible defaults
        assert contract.visual_contract.art_direction != ""


class TestInferStyleBible:
    def test_infer_style_bible(self):
        from renpy_mcp.services.scene_generation_service import SceneGenerationService
        from renpy_mcp.blueprint.models import ProjectStyleBible

        bp = _make_blueprint()
        bible = SceneGenerationService.infer_style_bible_from_blueprint(bp)
        assert isinstance(bible, ProjectStyleBible)
        assert "anime" in bible.visual_bible.art_direction.lower()


class TestInferChapterProfiles:
    def test_infer_profiles(self):
        from renpy_mcp.services.scene_generation_service import SceneGenerationService
        from renpy_mcp.blueprint.models import ChapterStyleProfiles

        bp = _make_blueprint(chapter_count=2)
        profiles = SceneGenerationService.infer_chapter_profiles_from_blueprint(bp)
        assert isinstance(profiles, ChapterStyleProfiles)
        assert len(profiles.chapters) == 2
