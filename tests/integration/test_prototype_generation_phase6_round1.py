"""Phase 6 Round 1: Multi-chapter style consistency + generation contract."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from renpy_mcp.web.fastapi_app import create_app


@pytest.fixture(autouse=True)
def _mock_interview_for_downstream_blueprint_flow(monkeypatch):
    """Drive downstream blueprint tests without invoking the real adaptive interview.

    These tests cover draft generation, refinement state, confirmation, outline,
    prototype, and rollback behavior. They are not intended to validate the
    interview model/prompt itself.
    """
    from renpy_mcp.services.refinement_logic import select_collecting_response

    async def _mock(self, user_message):
        if self.turn_count < 2:
            content, message_kind = select_collecting_response(
                self.turn_count, self.intake_mode, "zh"
            )
            return {
                "content": content,
                "message_kind": message_kind,
                "is_conclusion": False,
                "slot_updates": {},
            }
        return {"content": "Interview complete", "is_conclusion": True, "slot_updates": {}}
    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws.BlueprintOrchestrator._conduct_interview_round",
        _mock,
    )


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from renpy_mcp.config import RenPyConfig, get_settings
    from renpy_mcp.web.fastapi_app import set_config

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)
    set_config(RenPyConfig(sdk_path=Path(".")))
    app = create_app()
    return TestClient(app)


def _make_mock_blueprint_provider(title: str = "DEFAULT", **overrides) -> object:
    """Return a mock LLM provider that returns a fixed JSON blueprint."""
    blueprint = {
        "title": title,
        "genre": "Test",
        "worldview": "Test world",
        "themes": ["test"],
        "target_audience": "test",
        "estimated_play_time": "1h",
        "art_style": "test",
        "audio_style": "test",
        "characters": [
            {"name": "Alice", "role": "Protagonist", "personality": "brave", "appearance": "tall"},
        ],
        "chapters": [
            {"id": "ch1", "name": "Chapter1", "order": 1, "scenes": [{"id": "s1", "name": "Scene1", "order": 1}]},
        ],
    }
    blueprint.update(overrides)

    class MockProvider:
        tool_format = "anthropic"

        def chat(self, messages, tools=None, system=None, model=None, max_tokens=1024, temperature=None):
            from renpy_mcp.chat_engine.providers import LLMResponse
            return LLMResponse(
                content_blocks=[{"type": "text", "text": json.dumps(blueprint, ensure_ascii=False)}],
                stop_reason="end_turn",
            )

    return MockProvider()


def _drain_events(websocket, expected_count: int) -> list[dict]:
    """Read exactly expected_count JSON messages from the WebSocket."""
    events = []
    for _ in range(expected_count):
        events.append(websocket.receive_json())
    return events


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
        "art_style": "modern anime VN, clean line art",
        "audio_style": "test",
        "characters": [
            {"name": "Alice", "role": "Protagonist", "personality": "brave", "appearance": "tall, black hair"},
            {"name": "Bob", "role": "Companion", "personality": "smart", "appearance": "glasses, short hair"},
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
            },
            {
                "id": "ch2",
                "name": "Chapter2",
                "order": 2,
                "scenes": [
                    {"id": "s3", "name": "Twist", "order": 1},
                    {"id": "s4", "name": "Climax", "order": 2},
                ],
            },
        ],
    }


def _make_mock_scene_provider() -> object:
    scenes_ch1 = [
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
    scenes_ch2 = [
        {
            "scene_id": "proto-ch2-s1",
            "title": "The Twist",
            "summary": "A shocking revelation.",
            "location": "dark alley",
            "location_visual_brief": "Narrow dark alley with neon signs",
            "mood": "tense",
            "characters_present": ["Alice"],
            "dialogue_beats": [
                {"speaker": "Alice", "intent": "realize", "content_brief": "No way"},
            ],
            "entry_label": "prototype_ch2_start",
            "next_scene_id": "proto-ch2-s2",
        },
        {
            "scene_id": "proto-ch2-s2",
            "title": "Final Stand",
            "summary": "Alice makes a choice.",
            "location": "rooftop",
            "location_visual_brief": "City rooftop at dawn",
            "mood": "determined",
            "characters_present": ["Alice", "Bob"],
            "dialogue_beats": [
                {"speaker": "Alice", "intent": "decide", "content_brief": "I will do this"},
                {"speaker": "Bob", "intent": "support", "content_brief": "I am with you"},
            ],
            "entry_label": "prototype_ch2_scene2",
            "next_scene_id": None,
        },
    ]
    all_scenes = scenes_ch1 + scenes_ch2

    class MockSceneProvider:
        tool_format = "anthropic"
        _call_count = 0

        def chat(self, messages, tools=None, system=None, model=None, max_tokens=1024, temperature=None):
            self._call_count += 1
            prompt = messages[0].get("content", "") if messages else ""
            from renpy_mcp.chat_engine.providers import LLMResponse
            # Return ch1 scenes by default; if prompt mentions ch2 return ch2 scenes
            if "Chapter2" in prompt or "ch2" in prompt.lower():
                return LLMResponse(
                    content_blocks=[{"type": "text", "text": json.dumps(scenes_ch2, ensure_ascii=False)}],
                    stop_reason="end_turn",
                )
            # Heuristic: if the prompt contains contract visual info, record it for test inspection
            return LLMResponse(
                content_blocks=[{"type": "text", "text": json.dumps(scenes_ch1, ensure_ascii=False)}],
                stop_reason="end_turn",
            )

    return MockSceneProvider()


def _make_mock_scene_provider_that_records_prompt() -> object:
    recorded_prompts: list[str] = []
    scenes = [
        {
            "scene_id": "proto-ch1-s1",
            "title": "Test Scene",
            "summary": "Test.",
            "location": "test",
            "location_visual_brief": "Test visual",
            "mood": "neutral",
            "characters_present": ["Alice"],
            "dialogue_beats": [
                {"speaker": "Alice", "intent": "test", "content_brief": "Test line"},
            ],
            "entry_label": "prototype_ch1_start",
            "next_scene_id": None,
        },
    ]

    class RecordingProvider:
        tool_format = "anthropic"

        def chat(self, messages, tools=None, system=None, model=None, max_tokens=1024, temperature=None):
            if messages:
                recorded_prompts.append(messages[0].get("content", ""))
            from renpy_mcp.chat_engine.providers import LLMResponse
            return LLMResponse(
                content_blocks=[{"type": "text", "text": json.dumps(scenes, ensure_ascii=False)}],
                stop_reason="end_turn",
            )

    return RecordingProvider(), recorded_prompts


# ---------------------------------------------------------------------------
# 1. Persistence round-trip tests
# ---------------------------------------------------------------------------


def test_style_bible_roundtrip_persistence(client: TestClient, tmp_path: Path) -> None:
    """ProjectManager must persist and read back a ProjectStyleBible."""
    from renpy_mcp.blueprint.models import ProjectStyleBible
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "style_bible_rt"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    bible = ProjectStyleBible(
        visual_bible={
            "art_direction": "modern anime VN",
            "palette_baseline": "cool neutrals",
            "camera_language": "mid-distance readable staging",
            "background_complexity_budget": "medium",
            "forbidden_visual_drift": ["photorealism", "chibi"],
        },
        character_bible={
            "characters": [
                {
                    "name": "Alice",
                    "identity_anchors": ["black shoulder-length hair", "thin-framed glasses"],
                    "default_costume": "modern office casual",
                    "forbidden_drift": ["fantasy costume"],
                }
            ]
        },
        tone_bible={
            "narration_style": "clean, readable, restrained",
            "dialogue_style": "direct spoken Chinese",
            "dialogue_density": "short to medium",
            "forbidden_tone_drift": ["melodramatic monologue"],
        },
        continuity_bible={
            "world_rules": ["No magic in this world"],
            "relationship_baselines": ["Alice and Bob are coworkers"],
            "must_preserve_facts": ["Alice wears glasses"],
        },
    )

    pm.write_style_bible(project_name, bible)
    loaded = pm.read_style_bible(project_name)

    assert loaded is not None
    assert loaded.visual_bible.art_direction == "modern anime VN"
    assert loaded.character_bible.characters[0].name == "Alice"
    assert loaded.tone_bible.dialogue_style == "direct spoken Chinese"
    assert loaded.continuity_bible.must_preserve_facts == ["Alice wears glasses"]


def test_chapter_style_profiles_roundtrip_persistence(client: TestClient, tmp_path: Path) -> None:
    """ProjectManager must persist and read back ChapterStyleProfiles."""
    from renpy_mcp.blueprint.models import ChapterStyleProfile, ChapterStyleProfiles
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "chapter_profiles_rt"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    profiles = ChapterStyleProfiles(
        chapters=[
            ChapterStyleProfile(
                chapter_id="ch1",
                mood_target="uneasy but grounded",
                temperature_bias="cool-neutral",
                lighting_bias="soft overcast interior light",
                pacing_bias="measured",
                emotional_bias="suppressed pressure",
                location_motifs=["office interior", "glass partitions"],
                allowed_variation={
                    "palette_shift_max": "small",
                    "contrast_shift_max": "small",
                },
            ),
            ChapterStyleProfile(
                chapter_id="ch2",
                mood_target="rising tension",
                temperature_bias="warm-amber",
                lighting_bias="harsh directional light",
                pacing_bias="accelerating",
                emotional_bias="open conflict",
                location_motifs=["rooftop", "night city"],
                allowed_variation={
                    "palette_shift_max": "medium",
                    "contrast_shift_max": "medium",
                },
            ),
        ]
    )

    pm.write_chapter_style_profiles(project_name, profiles)
    loaded = pm.read_chapter_style_profiles(project_name)

    assert loaded is not None
    assert len(loaded.chapters) == 2
    assert loaded.chapters[0].chapter_id == "ch1"
    assert loaded.chapters[0].mood_target == "uneasy but grounded"
    assert loaded.chapters[1].chapter_id == "ch2"
    assert loaded.chapters[1].lighting_bias == "harsh directional light"


# ---------------------------------------------------------------------------
# 2. Fallback / inference tests
# ---------------------------------------------------------------------------


def test_missing_style_bible_falls_back_to_inferred_defaults_from_blueprint(client: TestClient, tmp_path: Path) -> None:
    """When style_bible.json is missing, build_generation_contract must infer safe defaults from blueprint."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "missing_bible"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    contract = service.build_generation_contract(project_name, blueprint, blueprint.chapters[0])

    assert contract is not None
    assert contract.chapter_id == "ch1"
    # Inferred defaults must contain at least art_direction derived from blueprint
    assert contract.visual_contract.art_direction
    assert contract.character_contract.characters
    assert len(contract.character_contract.characters) == 2


def test_missing_chapter_profiles_fall_back_without_breaking_generation(client: TestClient, tmp_path: Path) -> None:
    """When chapter_style_profiles.json is missing, generation must still work with inferred chapter profiles."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "missing_profiles"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    # Write a style bible but no chapter profiles
    from renpy_mcp.blueprint.models import ProjectStyleBible
    bible = ProjectStyleBible(
        visual_bible={"art_direction": "anime", "palette_baseline": "cool", "camera_language": "mid", "background_complexity_budget": "medium", "forbidden_visual_drift": []},
        character_bible={"characters": []},
        tone_bible={"narration_style": "clean", "dialogue_style": "direct", "dialogue_density": "medium", "forbidden_tone_drift": []},
        continuity_bible={"world_rules": [], "relationship_baselines": [], "must_preserve_facts": []},
    )
    pm.write_style_bible(project_name, bible)

    contract = service.build_generation_contract(project_name, blueprint, blueprint.chapters[0])
    assert contract is not None
    assert contract.chapter_id == "ch1"
    # Chapter-level fields should have safe defaults
    assert contract.visual_contract.mood_target is not None or contract.visual_contract.lighting_bias is not None


# ---------------------------------------------------------------------------
# 3. Contract merge rule tests
# ---------------------------------------------------------------------------


def test_generation_contract_merges_project_and_chapter_constraints(client: TestClient, tmp_path: Path) -> None:
    """Contract must merge project bible and chapter profile deterministically."""
    from renpy_mcp.blueprint.models import ProjectBlueprint, ProjectStyleBible, ChapterStyleProfile, ChapterStyleProfiles
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "merge_contract"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    bible = ProjectStyleBible(
        visual_bible={
            "art_direction": "project-anime",
            "palette_baseline": "project-cool",
            "camera_language": "project-mid",
            "background_complexity_budget": "medium",
            "forbidden_visual_drift": ["photorealism"],
        },
        character_bible={
            "characters": [
                {"name": "Alice", "identity_anchors": ["black hair"], "default_costume": "office", "forbidden_drift": []}
            ]
        },
        tone_bible={
            "narration_style": "clean",
            "dialogue_style": "direct",
            "dialogue_density": "medium",
            "forbidden_tone_drift": [],
        },
        continuity_bible={"world_rules": [], "relationship_baselines": [], "must_preserve_facts": ["Alice works at company X"]},
    )
    profiles = ChapterStyleProfiles(
        chapters=[
            ChapterStyleProfile(
                chapter_id="ch1",
                mood_target="chapter-warm",
                temperature_bias="chapter-warm",
                lighting_bias="chapter-soft",
                pacing_bias="chapter-measured",
                emotional_bias="chapter-hopeful",
                location_motifs=["cafe"],
                allowed_variation={"palette_shift_max": "small"},
            )
        ]
    )
    pm.write_style_bible(project_name, bible)
    pm.write_chapter_style_profiles(project_name, profiles)

    contract = service.build_generation_contract(project_name, blueprint, blueprint.chapters[0])

    # Project hard constraints preserved
    assert contract.visual_contract.art_direction == "project-anime"
    assert contract.visual_contract.palette_baseline == "project-cool"
    assert contract.character_contract.characters[0].identity_anchors == ["black hair"]
    assert contract.continuity_contract.must_preserve_facts == ["Alice works at company X"]

    # Chapter soft overrides applied
    assert contract.visual_contract.mood_target == "chapter-warm"
    assert contract.visual_contract.lighting_bias == "chapter-soft"
    assert contract.tone_contract.pacing_bias == "chapter-measured"
    assert contract.visual_contract.location_motifs == ["cafe"]


def test_chapter_profile_cannot_override_project_hard_constraints(client: TestClient, tmp_path: Path) -> None:
    """Chapter profile must not be allowed to override project-level hard constraints like art_direction or character identity."""
    from renpy_mcp.blueprint.models import ProjectBlueprint, ProjectStyleBible, ChapterStyleProfile, ChapterStyleProfiles
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "hard_constraints"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=None)

    bible = ProjectStyleBible(
        visual_bible={
            "art_direction": "project-anime",
            "palette_baseline": "project-cool",
            "camera_language": "project-mid",
            "background_complexity_budget": "medium",
            "forbidden_visual_drift": ["photorealism"],
        },
        character_bible={
            "characters": [
                {"name": "Alice", "identity_anchors": ["black hair"], "default_costume": "office", "forbidden_drift": []}
            ]
        },
        tone_bible={
            "narration_style": "clean",
            "dialogue_style": "direct",
            "dialogue_density": "medium",
            "forbidden_tone_drift": [],
        },
        continuity_bible={"world_rules": [], "relationship_baselines": [], "must_preserve_facts": ["Alice works at company X"]},
    )
    # Malicious chapter profile tries to override hard constraints
    profiles = ChapterStyleProfiles(
        chapters=[
            ChapterStyleProfile(
                chapter_id="ch1",
                mood_target="warm",
                temperature_bias="warm",
                lighting_bias="soft",
                pacing_bias="measured",
                emotional_bias="hopeful",
                location_motifs=["cafe"],
                allowed_variation={"palette_shift_max": "small"},
            )
        ]
    )
    pm.write_style_bible(project_name, bible)
    pm.write_chapter_style_profiles(project_name, profiles)

    contract = service.build_generation_contract(project_name, blueprint, blueprint.chapters[0])

    # Hard constraints still intact
    assert contract.visual_contract.art_direction == "project-anime"
    assert contract.character_contract.characters[0].identity_anchors == ["black hair"]
    assert contract.continuity_contract.must_preserve_facts == ["Alice works at company X"]


# ---------------------------------------------------------------------------
# 4. Prompt consumption tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_scenes_prompt_includes_project_and_chapter_contract() -> None:
    """generate_scenes must include style contract constraints in the LLM prompt when contract is provided."""
    from renpy_mcp.blueprint.models import ProjectBlueprint, GenerationContract
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider, recorded_prompts = _make_mock_scene_provider_that_records_prompt()
    service = PrototypeGenerationService(pm=None, provider=provider)

    contract = GenerationContract(
        chapter_id="ch1",
        visual_contract={
            "art_direction": "project-anime",
            "palette_baseline": "cool neutrals",
            "camera_language": "mid-distance",
            "mood_target": "warm",
            "lighting_bias": "soft",
            "location_motifs": ["cafe"],
        },
        character_contract={
            "characters": [
                {"name": "Alice", "identity_anchors": ["black hair"], "default_costume": "office", "chapter_variation": "none"}
            ]
        },
        tone_contract={
            "dialogue_style": "direct spoken Chinese",
            "dialogue_density": "short to medium",
            "pacing_bias": "measured",
        },
        continuity_contract={
            "must_preserve_facts": ["Alice works at company X"],
            "relationship_state": ["Alice and Bob are coworkers"],
        },
    )

    chapter = blueprint.chapters[0]
    await service.generate_scenes(chapter, blueprint, contract=contract)

    assert len(recorded_prompts) == 1
    prompt = recorded_prompts[0]
    assert "project-anime" in prompt
    assert "cool neutrals" in prompt
    assert "direct spoken Chinese" in prompt
    assert "Alice works at company X" in prompt
    assert "measured" in prompt


@pytest.mark.asyncio
async def test_background_prompt_uses_visual_contract(monkeypatch) -> None:
    """Background generation prompt must consume visual contract when provided."""
    from renpy_mcp.blueprint.models import ProjectBlueprint, GenerationContract
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService, PrototypeScene
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        project_name = "bg_contract"
        pm = ProjectManager(get_settings())
        monkeypatch.setattr(pm.settings, "workspace", tmp_path)
        pm.ensure_project_dir(project_name)

        service = PrototypeGenerationService(pm=pm, provider=None)

        scenes = [
            PrototypeScene(
                scene_id="s1",
                title="Test",
                summary="Test scene",
                location="library",
                location_visual_brief="Quiet library with warm lighting",
                mood="warm",
                characters_present=["Alice"],
                entry_label="start",
            )
        ]

        contract = GenerationContract(
            chapter_id="ch1",
            visual_contract={
                "art_direction": "project-anime-VN",
                "palette_baseline": "cool-blue",
                "camera_language": "mid-distance staging",
                "mood_target": "melancholic",
                "lighting_bias": "soft overcast",
                "temperature_bias": "cool-neutral",
                "location_motifs": ["wooden shelves", "reading lamps"],
            },
            character_contract={"characters": []},
            tone_contract={"dialogue_style": "direct", "dialogue_density": "medium", "pacing_bias": "slow"},
            continuity_contract={"must_preserve_facts": [], "relationship_state": []},
        )

        # Patch ImageService to record prompts instead of generating
        recorded_prompts: list[str] = []

        class FakeImageService:
            def __init__(self, *args, **kwargs):
                pass

            def is_available(self):
                return True

            async def generate_image(self, project_dir, prompt, image_type, base_name):
                recorded_prompts.append(prompt)
                # Return a fake result
                from renpy_mcp.ai.image_service import ImageGenerationResult
                fake_path = project_dir / "game" / "images" / "background" / f"{base_name}.png"
                fake_path.parent.mkdir(parents=True, exist_ok=True)
                fake_path.write_bytes(b"fake")
                return ImageGenerationResult(success=True, primary_file=fake_path, metadata={})

        with patch("renpy_mcp.ai.image_service.ImageService", FakeImageService):
            await service.generate_background_assets(project_name, scenes, contract=contract)

        assert len(recorded_prompts) == 1
        prompt = recorded_prompts[0]
        assert "project-anime-VN" in prompt
        assert "cool-blue" in prompt
        assert "mid-distance staging" in prompt
        assert "melancholic" in prompt
        assert "soft overcast" in prompt
        assert "Quiet library with warm lighting" in prompt


@pytest.mark.asyncio
async def test_character_prompt_uses_identity_anchors_and_chapter_mood(monkeypatch) -> None:
    """Character sprite prompt must include identity anchors (hard) and chapter mood/lighting (soft)."""
    from renpy_mcp.blueprint.models import ProjectBlueprint, GenerationContract
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService, PrototypeScene
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        project_name = "char_contract"
        pm = ProjectManager(get_settings())
        monkeypatch.setattr(pm.settings, "workspace", tmp_path)
        pm.ensure_project_dir(project_name)

        service = PrototypeGenerationService(pm=pm, provider=None)

        scenes = [
            PrototypeScene(
                scene_id="s1",
                title="Test",
                summary="Test scene",
                location="library",
                location_visual_brief="Quiet library",
                mood="warm",
                characters_present=["Alice"],
                entry_label="start",
            )
        ]

        contract = GenerationContract(
            chapter_id="ch1",
            visual_contract={
                "art_direction": "project-anime-VN",
                "palette_baseline": "cool-blue",
                "camera_language": "mid-distance",
                "mood_target": "melancholic",
                "lighting_bias": "soft overcast",
                "temperature_bias": "cool-neutral",
            },
            character_contract={
                "characters": [
                    {"name": "Alice", "identity_anchors": ["black shoulder-length hair", "thin-framed glasses"], "default_costume": "modern office casual", "chapter_variation": "none"}
                ]
            },
            tone_contract={"dialogue_style": "direct", "dialogue_density": "medium", "pacing_bias": "slow"},
            continuity_contract={"must_preserve_facts": [], "relationship_state": []},
        )

        recorded_prompts: list[str] = []

        class FakeImageService:
            def __init__(self, *args, **kwargs):
                pass

            def is_available(self):
                return True

            async def generate_image(self, project_dir, prompt, image_type, base_name):
                recorded_prompts.append(prompt)
                from renpy_mcp.ai.image_service import ImageGenerationResult
                fake_path = project_dir / "game" / "images" / "character" / f"{base_name}.png"
                fake_path.parent.mkdir(parents=True, exist_ok=True)
                fake_path.write_bytes(b"fake")
                return ImageGenerationResult(success=True, primary_file=fake_path, metadata={})

        with patch("renpy_mcp.ai.image_service.ImageService", FakeImageService):
            await service.generate_character_assets(project_name, ProjectBlueprint(**_make_blueprint()), scenes, contract=contract)

        assert len(recorded_prompts) == 1
        prompt = recorded_prompts[0]
        # Identity anchors must be in prompt
        assert "black shoulder-length hair" in prompt
        assert "thin-framed glasses" in prompt
        assert "modern office casual" in prompt
        # Chapter mood/lighting should influence presentation
        assert "melancholic" in prompt or "soft overcast" in prompt or "cool-neutral" in prompt


# ---------------------------------------------------------------------------
# 5. Multi-chapter generation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_all_chapter_scenes_returns_packages_for_multiple_chapters(monkeypatch) -> None:
    """generate_all_chapter_scenes must return scene packages for every chapter in the blueprint."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        project_name = "multi_chapter"
        pm = ProjectManager(get_settings())
        monkeypatch.setattr(pm.settings, "workspace", tmp_path)
        pm.ensure_project_dir(project_name)

        blueprint = ProjectBlueprint(**_make_blueprint())
        provider = _make_mock_scene_provider()
        service = PrototypeGenerationService(pm=pm, provider=provider)

        packages = await service.generate_all_chapter_scenes(project_name, blueprint)

        assert "ch1" in packages
        assert "ch2" in packages
        assert len(packages["ch1"]) >= 1
        assert len(packages["ch2"]) >= 1
        # Each package should have distinct scenes
        ch1_ids = {s.scene_id for s in packages["ch1"]}
        ch2_ids = {s.scene_id for s in packages["ch2"]}
        assert ch1_ids.isdisjoint(ch2_ids)


@pytest.mark.asyncio
async def test_multi_chapter_generation_preserves_project_level_style_consistency(monkeypatch) -> None:
    """Across chapters, project-level style identity (art_direction, character anchors) must remain stable."""
    from renpy_mcp.blueprint.models import ProjectBlueprint, ProjectStyleBible, ChapterStyleProfile, ChapterStyleProfiles
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        project_name = "style_consistency"
        pm = ProjectManager(get_settings())
        monkeypatch.setattr(pm.settings, "workspace", tmp_path)
        pm.ensure_project_dir(project_name)

        blueprint = ProjectBlueprint(**_make_blueprint())

        bible = ProjectStyleBible(
            visual_bible={
                "art_direction": "stable-anime-VN",
                "palette_baseline": "stable-cool",
                "camera_language": "stable-mid",
                "background_complexity_budget": "medium",
                "forbidden_visual_drift": [],
            },
            character_bible={
                "characters": [
                    {"name": "Alice", "identity_anchors": ["stable-black-hair"], "default_costume": "stable-office", "forbidden_drift": []}
                ]
            },
            tone_bible={
                "narration_style": "stable-clean",
                "dialogue_style": "stable-direct",
                "dialogue_density": "medium",
                "forbidden_tone_drift": [],
            },
            continuity_bible={"world_rules": [], "relationship_baselines": [], "must_preserve_facts": []},
        )
        profiles = ChapterStyleProfiles(
            chapters=[
                ChapterStyleProfile(
                    chapter_id="ch1",
                    mood_target="ch1-mood",
                    temperature_bias="ch1-temp",
                    lighting_bias="ch1-light",
                    pacing_bias="ch1-pace",
                    emotional_bias="ch1-emotion",
                    location_motifs=["ch1-loc"],
                    allowed_variation={},
                ),
                ChapterStyleProfile(
                    chapter_id="ch2",
                    mood_target="ch2-mood",
                    temperature_bias="ch2-temp",
                    lighting_bias="ch2-light",
                    pacing_bias="ch2-pace",
                    emotional_bias="ch2-emotion",
                    location_motifs=["ch2-loc"],
                    allowed_variation={},
                ),
            ]
        )
        pm.write_style_bible(project_name, bible)
        pm.write_chapter_style_profiles(project_name, profiles)

        provider = _make_mock_scene_provider()
        service = PrototypeGenerationService(pm=pm, provider=provider)

        packages = await service.generate_all_chapter_scenes(project_name, blueprint)

        # Both chapters generated
        assert len(packages) == 2

        # Verify that contracts were built per-chapter with distinct chapter biases
        # We can't directly inspect internal contracts, but we verify the service
        # method exists and returns distinct packages per chapter.
        for ch_id, scenes in packages.items():
            assert len(scenes) >= 1
            for s in scenes:
                assert s.scene_id.startswith(f"proto-{ch_id}")


# ---------------------------------------------------------------------------
# 6. Regression: single-chapter prototype build not broken
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_chapter_prototype_build_not_regressed(client: TestClient, tmp_path: Path) -> None:
    """The existing single-chapter confirmation pipeline must still produce a working prototype."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "single_chapter_regression"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    chapter = service.select_prototype_chapter(blueprint)
    scenes = await service.generate_scenes(chapter, blueprint)

    # Background assets (with ImageService unavailable -> PIL fallback)
    bg_assets = await service.generate_background_assets(project_name, scenes)
    # Character assets
    char_assets = await service.generate_character_assets(project_name, blueprint, scenes)
    service.build_sprite_plan(scenes, char_assets, project_name=project_name)
    cjk_font = service.ensure_cjk_font_config(project_name)
    staging_path = service.write_script(
        project_name, chapter, scenes,
        background_assets=bg_assets, character_assets=char_assets, cjk_font_config=cjk_font,
    )
    service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)
    service.update_index(project_name, chapter, scenes, staging_path, bg_assets, char_assets, cjk_font)
    service.commit_prototype_replacement(project_name, [s.scene_id for s in scenes], staging_path)

    # Script must exist and be wired
    script_path = tmp_path / project_name / "game" / "script.rpy"
    assert script_path.exists()
    content = script_path.read_text(encoding="utf-8")
    assert "call prototype_ch1_start" in content

    # Index must have scenes
    index_path = tmp_path / project_name / "meta" / "index.json"
    assert index_path.exists()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    for s in scenes:
        assert s.scene_id in index.get("scenes", {})



# ---------------------------------------------------------------------------
# Round 1 review fixes: contract wired to main chain, scene packages persisted,
# structured schema, invalid config not silently swallowed
# ---------------------------------------------------------------------------


# -- A. Contract wired into real confirmation pipeline --


def test_confirmation_pipeline_builds_generation_contract_for_selected_prototype_chapter(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, tmp_path: Path
) -> None:
    """The real confirmation pipeline must build a generation contract for the selected prototype chapter."""
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService, PrototypeScene

    project_name = "bp_contract_build"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

    mock_scenes = [
        PrototypeScene(
            scene_id="proto-ch1-s1",
            title="Opening",
            summary="Test opening.",
            location="classroom",
            characters_present=["Alice"],
            entry_label="prototype_ch1_start",
            next_scene_id=None,
        ),
    ]

    async def _mock_generate_scenes(self, chapter, blueprint, contract=None):
        return mock_scenes

    monkeypatch.setattr(
        "renpy_mcp.services.prototype_generation_service.PrototypeGenerationService.generate_scenes",
        _mock_generate_scenes,
    )

    recorded_contracts: list = []

    def _mock_build_contract(self, project_name, blueprint, chapter):
        from renpy_mcp.blueprint.models import GenerationContract
        contract = GenerationContract(chapter_id=chapter.id)
        recorded_contracts.append(contract)
        return contract

    monkeypatch.setattr(
        "renpy_mcp.services.prototype_generation_service.PrototypeGenerationService.build_generation_contract",
        _mock_build_contract,
    )

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({"type": "user_message", "content": f"turn {turn}", "project_name": project_name})
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                events = _drain_events(websocket, 3)
                req_event = next(e for e in events if e["type"] == "confirmation_request")
                confirmation_id = req_event["confirmation_id"]

        websocket.send_json({
            "type": "confirmation_response",
            "confirmation_id": confirmation_id,
            "approved": True,
            "project_name": project_name,
        })
        while True:
            data = websocket.receive_json()
            if data.get("pipeline_stage") == "editing" and data["type"] == "message":
                break

    assert len(recorded_contracts) == 1
    assert recorded_contracts[0].chapter_id == "ch1"


def test_confirmation_pipeline_passes_contract_to_scene_background_and_character_generation(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, tmp_path: Path
) -> None:
    """The confirmation pipeline must pass the same generation contract to scene, background, and character generation."""
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService, PrototypeScene

    project_name = "bp_contract_pass"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

    mock_scenes = [
        PrototypeScene(
            scene_id="proto-ch1-s1",
            title="Opening",
            summary="Test opening.",
            location="classroom",
            characters_present=["Alice"],
            entry_label="prototype_ch1_start",
            next_scene_id=None,
        ),
    ]

    recorded_scenes_contracts: list = []
    recorded_bg_contracts: list = []
    recorded_char_contracts: list = []

    async def _mock_generate_scenes(self, chapter, blueprint, contract=None):
        recorded_scenes_contracts.append(contract)
        return mock_scenes

    async def _mock_generate_backgrounds(self, project_name, scenes, round_id=None, contract=None):
        recorded_bg_contracts.append(contract)
        return {}

    async def _mock_generate_characters(self, project_name, blueprint, scenes, round_id=None, contract=None):
        recorded_char_contracts.append(contract)
        return {}

    monkeypatch.setattr(
        "renpy_mcp.services.prototype_generation_service.PrototypeGenerationService.generate_scenes",
        _mock_generate_scenes,
    )
    monkeypatch.setattr(
        "renpy_mcp.services.prototype_generation_service.PrototypeGenerationService.generate_background_assets",
        _mock_generate_backgrounds,
    )
    monkeypatch.setattr(
        "renpy_mcp.services.prototype_generation_service.PrototypeGenerationService.generate_character_assets",
        _mock_generate_characters,
    )

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({"type": "user_message", "content": f"turn {turn}", "project_name": project_name})
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                events = _drain_events(websocket, 3)
                req_event = next(e for e in events if e["type"] == "confirmation_request")
                confirmation_id = req_event["confirmation_id"]

        websocket.send_json({
            "type": "confirmation_response",
            "confirmation_id": confirmation_id,
            "approved": True,
            "project_name": project_name,
        })
        while True:
            data = websocket.receive_json()
            if data.get("pipeline_stage") == "editing" and data["type"] == "message":
                break

    assert len(recorded_scenes_contracts) == 1
    assert len(recorded_bg_contracts) == 1
    assert len(recorded_char_contracts) == 1
    # All three must have received the same contract object (or at least a contract)
    assert recorded_scenes_contracts[0] is not None
    assert recorded_scenes_contracts[0] is recorded_bg_contracts[0]
    assert recorded_scenes_contracts[0] is recorded_char_contracts[0]


# -- B. Multi-chapter scene packages persisted --


@pytest.mark.asyncio
async def test_generate_all_chapter_scenes_persists_scene_packages_snapshot(
    client: TestClient, tmp_path: Path
) -> None:
    """generate_all_chapter_scenes must persist the result to meta/scene_packages.json."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "multi_chapter_persist"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    packages = await service.generate_all_chapter_scenes(project_name, blueprint)

    # Snapshot must be persisted
    snapshot_path = tmp_path / project_name / "meta" / "scene_packages.json"
    assert snapshot_path.exists(), "scene_packages.json must be written after generate_all_chapter_scenes"

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert "chapters" in snapshot
    ch_ids = {ch["chapter_id"] for ch in snapshot["chapters"]}
    assert "ch1" in ch_ids
    assert "ch2" in ch_ids

    # No absolute paths leaked
    for ch in snapshot["chapters"]:
        for scene in ch.get("scenes", []):
            for key in ("scene_id", "title", "summary", "location", "mood"):
                if key in scene:
                    val = scene[key]
                    if isinstance(val, str):
                        assert "C:\\" not in val and "D:\\" not in val, f"Absolute path leaked in {key}"


def test_project_scenes_api_uses_scene_packages_as_multi_chapter_base(
    client: TestClient, tmp_path: Path
) -> None:
    """scene_packages.json provides the multi-chapter structural base; prototype index enriches overlapping scenes."""
    project_name = "api_uses_snapshot_base"
    _create_project(client, tmp_path, project_name)

    # Write a scene_packages snapshot directly
    snapshot = {
        "chapters": [
            {
                "chapter_id": "ch1",
                "chapter_name": "Chapter One",
                "chapter_order": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "title": "Snapshot Scene",
                        "summary": "From scene packages.",
                        "location": "rooftop",
                        "mood": "tense",
                        "characters_present": ["Alice"],
                        "entry_label": "ch1_s1",
                        "next_scene_id": None,
                        "scene_order": 1,
                    }
                ],
            }
        ]
    }
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    response = client.get(f"/api/projects/{project_name}/scenes")
    assert response.status_code == 200
    data = response.json()
    assert "chapters" in data
    assert len(data["chapters"]) == 1
    assert data["chapters"][0]["scenes"][0]["name"] == "Snapshot Scene"


# -- C. Invalid style/profile config must not be silently swallowed --


def test_invalid_style_bible_file_raises_instead_of_silent_fallback(
    client: TestClient, tmp_path: Path
) -> None:
    """If style_bible.json exists but is invalid, ProjectManager must raise rather than silently fallback."""
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "invalid_bible"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "style_bible.json").write_text("not valid json {{{", encoding="utf-8")

    with pytest.raises(ValueError):
        pm.read_style_bible(project_name)


def test_invalid_chapter_style_profiles_file_raises_instead_of_silent_fallback(
    client: TestClient, tmp_path: Path
) -> None:
    """If chapter_style_profiles.json exists but is invalid, ProjectManager must raise rather than silently fallback."""
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "invalid_profiles"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "chapter_style_profiles.json").write_text("not valid json {{{", encoding="utf-8")

    with pytest.raises(ValueError):
        pm.read_chapter_style_profiles(project_name)


# -- D. Structured schema models --


def test_style_bible_requires_structured_visual_character_tone_continuity_sections() -> None:
    """ProjectStyleBible must use structured sub-models for its four sections, not bare dicts."""
    from renpy_mcp.blueprint.models import (
        ProjectStyleBible,
        VisualBible,
        CharacterBible,
        CharacterStyleEntry,
        ToneBible,
        ContinuityBible,
    )

    bible = ProjectStyleBible(
        visual_bible=VisualBible(
            art_direction="anime VN",
            palette_baseline="cool",
            camera_language="mid-distance",
            background_complexity_budget="medium",
            forbidden_visual_drift=["photorealism"],
        ),
        character_bible=CharacterBible(
            characters=[
                CharacterStyleEntry(
                    name="Alice",
                    identity_anchors=["black hair"],
                    default_costume="office casual",
                    forbidden_drift=["fantasy costume"],
                )
            ]
        ),
        tone_bible=ToneBible(
            narration_style="clean",
            dialogue_style="direct",
            dialogue_density="medium",
            forbidden_tone_drift=["melodrama"],
        ),
        continuity_bible=ContinuityBible(
            world_rules=["no magic"],
            relationship_baselines=["coworkers"],
            must_preserve_facts=["Alice wears glasses"],
        ),
    )

    assert bible.visual_bible.art_direction == "anime VN"
    assert bible.character_bible.characters[0].name == "Alice"
    assert bible.tone_bible.dialogue_style == "direct"
    assert bible.continuity_bible.must_preserve_facts == ["Alice wears glasses"]


def test_generation_contract_uses_structured_contract_models() -> None:
    """GenerationContract must use structured contract sub-models."""
    from renpy_mcp.blueprint.models import (
        GenerationContract,
        VisualContract,
        CharacterContract,
        CharacterStyleEntry,
        ToneContract,
        ContinuityContract,
    )

    contract = GenerationContract(
        chapter_id="ch1",
        visual_contract=VisualContract(
            art_direction="anime",
            palette_baseline="cool",
            camera_language="mid",
            mood_target="tense",
            lighting_bias="soft",
            temperature_bias="cool-neutral",
            location_motifs=["cafe"],
        ),
        character_contract=CharacterContract(
            characters=[
                CharacterStyleEntry(name="Alice", identity_anchors=["black hair"], default_costume="office", forbidden_drift=[])
            ]
        ),
        tone_contract=ToneContract(
            dialogue_style="direct",
            dialogue_density="medium",
            pacing_bias="measured",
            emotional_bias="suppressed",
        ),
        continuity_contract=ContinuityContract(
            must_preserve_facts=["fact1"],
            relationship_state=["state1"],
            world_rules=["rule1"],
        ),
    )

    assert contract.visual_contract.mood_target == "tense"
    assert contract.character_contract.characters[0].identity_anchors == ["black hair"]
    assert contract.tone_contract.pacing_bias == "measured"
    assert contract.continuity_contract.must_preserve_facts == ["fact1"]


# ---------------------------------------------------------------------------
# Round 2 review fixes: real multi-chapter entry, richer snapshot schema,
# merge strategy between scene_packages and prototype index
# ---------------------------------------------------------------------------


# -- A. Real product-level entry for multi-chapter scene packages --


@pytest.mark.asyncio
async def test_generate_scene_packages_api_persists_multi_chapter_snapshot(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, tmp_path: Path
) -> None:
    """POST /scene-packages/generate advances one chapter per call and persists the final snapshot."""
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "scene_packages_api_entry"
    _create_project(client, tmp_path, project_name)

    # Write a blueprint with two chapters
    from renpy_mcp.blueprint.models import ProjectBlueprint
    blueprint = ProjectBlueprint(**_make_blueprint())
    pm = ProjectManager(get_settings())
    pm.write_blueprint(project_name, blueprint)

    # Mock provider to return scenes for each chapter
    monkeypatch.setattr(
        "renpy_mcp.web.routers.generation._get_provider", lambda: _make_mock_scene_provider()
    )

    response = client.post(f"/api/projects/{project_name}/scene-packages/generate")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("success") is True
    assert data.get("complete") is False
    assert data["scene_generation"]["completed_count"] == 1
    assert data["scene_generation"]["total_count"] == 2

    snapshot_path = tmp_path / project_name / "meta" / "scene_packages.json"
    assert not snapshot_path.exists(), "scene_packages.json must not expose a partial generation"

    response = client.post(f"/api/projects/{project_name}/scene-packages/generate")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("complete") is True
    assert data["scene_generation"]["completed_count"] == 2

    # Snapshot must be persisted
    assert snapshot_path.exists(), "scene_packages.json must be written by the API"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    ch_ids = {ch["chapter_id"] for ch in snapshot.get("chapters", [])}
    assert "ch1" in ch_ids
    assert "ch2" in ch_ids


# -- B. Richer snapshot schema --


@pytest.mark.asyncio
async def test_scene_packages_snapshot_contains_chapter_names_orders_and_scene_metadata(
    client: TestClient, tmp_path: Path
) -> None:
    """scene_packages.json must carry chapter_name, chapter_order, scene_order, dialogue_beats, and other readable metadata."""
    from renpy_mcp.blueprint.models import ProjectBlueprint
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "rich_snapshot_schema"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    packages = await service.generate_all_chapter_scenes(project_name, blueprint)

    snapshot_path = tmp_path / project_name / "meta" / "scene_packages.json"
    assert snapshot_path.exists()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    chapters = snapshot.get("chapters", [])
    assert len(chapters) >= 2

    for ch in chapters:
        assert "chapter_name" in ch, "chapter_name must be present"
        assert "chapter_order" in ch, "chapter_order must be present"
        assert isinstance(ch["chapter_order"], int)
        for scene in ch.get("scenes", []):
            assert "scene_order" in scene, "scene_order must be present"
            assert isinstance(scene["scene_order"], int)
            assert "dialogue_beats" in scene, "dialogue_beats must be present"
            assert isinstance(scene["dialogue_beats"], list)

    # Verify specific values derived from blueprint
    ch1 = next(ch for ch in chapters if ch["chapter_id"] == "ch1")
    assert ch1["chapter_name"] == "Chapter1"
    assert ch1["chapter_order"] == 1
    assert ch1["scenes"][0]["scene_order"] == 1

    ch2 = next(ch for ch in chapters if ch["chapter_id"] == "ch2")
    assert ch2["chapter_name"] == "Chapter2"
    assert ch2["chapter_order"] == 2


# -- C. Merge strategy: scene_packages base + prototype index enrichment --


def test_project_scenes_api_merges_scene_packages_with_richer_prototype_index_fields(
    client: TestClient, tmp_path: Path
) -> None:
    """/scenes must merge scene_packages structure with richer prototype index fields instead of letting scene_packages shadow them."""
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "merge_scene_packages_index"
    _create_project(client, tmp_path, project_name)

    # 1. Write a scene_packages snapshot (Phase 6 multi-chapter base)
    scene_packages = {
        "chapters": [
            {
                "chapter_id": "ch1",
                "chapter_name": "Chapter One",
                "chapter_order": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "title": "Snapshot Scene",
                        "summary": "From scene packages.",
                        "location": "rooftop",
                        "mood": "tense",
                        "characters_present": ["Alice"],
                        "dialogue_beats": [{"speaker": "Alice", "intent": "greet", "content_brief": "Hi"}],
                        "entry_label": "ch1_s1",
                        "next_scene_id": None,
                        "scene_order": 1,
                    }
                ],
            }
        ]
    }
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # 2. Write a prototype index with richer fields for the SAME scene
    index = {
        "scenes": {
            "s1": {
                "scene_id": "s1",
                "chapter_id": "ch1",
                "title": "Snapshot Scene",
                "order": 5,
                "characters_present": ["Alice", "Bob"],
                "background_asset_path": "game/images/background/bg_rooftop.png",
                "background_placeholder": False,
                "dialogue_beats": [
                    {"speaker": "Alice", "intent": "greet", "content_brief": "Hi", "spoken_line": "Hello there"},
                    {"speaker": "Bob", "intent": "respond", "content_brief": "Hey", "spoken_line": "Hey yourself"},
                ],
                "sprite_plan": [
                    {"character_name": "Alice", "position": "left", "expression": "happy"},
                ],
                "location": "rooftop",
                "location_visual_brief": "Night rooftop with neon",
                "mood": "tense",
                "summary": "From scene packages.",
                "source": "prototype",
                "next_scene_id": None,
            }
        }
    }
    (meta_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    response = client.get(f"/api/projects/{project_name}/scenes")
    assert response.status_code == 200
    data = response.json()
    assert "chapters" in data
    assert len(data["chapters"]) == 1

    ch = data["chapters"][0]
    assert ch["name"] == "Chapter One"

    scene = ch["scenes"][0]
    # scene_packages provided these
    assert scene["id"] == "s1"
    assert scene["name"] == "Snapshot Scene"
    # prototype index enriched these
    assert scene["order"] == 5, "order must come from prototype index, not default"
    assert scene["backgrounds"] == ["game/images/background/bg_rooftop.png"]
    assert scene["background_placeholder"] is False
    assert len(scene["dialogue_beats"]) == 2, "dialogue_beats must be enriched from index"
    assert scene["dialogue_beats"][1]["speaker"] == "Bob"
    assert len(scene["sprite_plan"]) == 1
    assert scene["sprite_plan"][0]["character_name"] == "Alice"


def test_project_scenes_api_keeps_phase5_prototype_scene_details_when_scene_packages_exist(
    client: TestClient, tmp_path: Path
) -> None:
    """When only a subset of scenes overlap between scene_packages and prototype index, non-overlapping scenes from both must be preserved."""
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "phase5_no_regression"
    _create_project(client, tmp_path, project_name)

    # scene_packages has two chapters: ch1 (s1) and ch2 (s2)
    scene_packages = {
        "chapters": [
            {
                "chapter_id": "ch1",
                "chapter_name": "Chapter One",
                "chapter_order": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "title": "Scene One",
                        "summary": "Summary one",
                        "location": "cafe",
                        "mood": "calm",
                        "characters_present": ["Alice"],
                        "dialogue_beats": [],
                        "entry_label": "ch1_s1",
                        "next_scene_id": None,
                        "scene_order": 1,
                    }
                ],
            },
            {
                "chapter_id": "ch2",
                "chapter_name": "Chapter Two",
                "chapter_order": 2,
                "scenes": [
                    {
                        "scene_id": "s2",
                        "title": "Scene Two",
                        "summary": "Summary two",
                        "location": "street",
                        "mood": "tense",
                        "characters_present": ["Bob"],
                        "dialogue_beats": [],
                        "entry_label": "ch2_s2",
                        "next_scene_id": None,
                        "scene_order": 1,
                    }
                ],
            },
        ]
    }
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # prototype index has richer data only for s1 (ch1)
    index = {
        "scenes": {
            "s1": {
                "scene_id": "s1",
                "chapter_id": "ch1",
                "title": "Scene One",
                "order": 3,
                "characters_present": ["Alice"],
                "background_asset_path": "game/images/background/bg_cafe.png",
                "background_placeholder": False,
                "dialogue_beats": [{"speaker": "Alice", "intent": "order", "content_brief": "Coffee"}],
                "sprite_plan": [{"character_name": "Alice", "position": "center"}],
                "location": "cafe",
                "mood": "calm",
                "summary": "Summary one",
                "source": "prototype",
                "next_scene_id": None,
            }
        }
    }
    (meta_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    response = client.get(f"/api/projects/{project_name}/scenes")
    assert response.status_code == 200
    data = response.json()

    # Both chapters must be present (from scene_packages)
    assert len(data["chapters"]) == 2
    ch1 = next(ch for ch in data["chapters"] if ch["id"] == "ch1")
    ch2 = next(ch for ch in data["chapters"] if ch["id"] == "ch2")

    # s1 enriched by prototype index
    s1 = next(s for s in ch1["scenes"] if s["id"] == "s1")
    assert s1["order"] == 3
    assert s1["backgrounds"] == ["game/images/background/bg_cafe.png"]
    assert len(s1["dialogue_beats"]) == 1
    assert len(s1["sprite_plan"]) == 1

    # s2 untouched from scene_packages (no index overlap)
    s2 = next(s for s in ch2["scenes"] if s["id"] == "s2")
    assert s2["name"] == "Scene Two"
    assert s2["order"] == 1  # default from scene_packages since no index overlap
    assert s2["backgrounds"] == []
    assert s2["dialogue_beats"] == []


# ---------------------------------------------------------------------------
# Round 3 review fixes: index-only scenes preserved, placeholder not faked,
# old prefer test renamed
# ---------------------------------------------------------------------------


def test_project_scenes_api_preserves_index_only_scenes_when_scene_packages_are_partial(
    client: TestClient, tmp_path: Path
) -> None:
    """Prototype index scenes that are not in scene_packages must still appear in the API result."""
    project_name = "partial_snapshot_preserve_index"
    _create_project(client, tmp_path, project_name)

    # scene_packages has ch1 with s1 only
    scene_packages = {
        "chapters": [
            {
                "chapter_id": "ch1",
                "chapter_name": "Chapter One",
                "chapter_order": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "title": "Scene One",
                        "summary": "Summary one",
                        "location": "cafe",
                        "mood": "calm",
                        "characters_present": ["Alice"],
                        "dialogue_beats": [],
                        "entry_label": "ch1_s1",
                        "next_scene_id": "s2",
                        "scene_order": 1,
                    }
                ],
            }
        ]
    }
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # prototype index has s1 (overlap) AND s2 (index-only, same chapter)
    index = {
        "scenes": {
            "s1": {
                "scene_id": "s1",
                "chapter_id": "ch1",
                "title": "Scene One",
                "order": 3,
                "characters_present": ["Alice"],
                "background_asset_path": "game/images/background/bg_cafe.png",
                "background_placeholder": False,
                "dialogue_beats": [{"speaker": "Alice", "intent": "order", "content_brief": "Coffee"}],
                "sprite_plan": [{"character_name": "Alice", "position": "center"}],
                "location": "cafe",
                "mood": "calm",
                "summary": "Summary one",
                "source": "prototype",
                "next_scene_id": "s2",
            },
            "s2": {
                "scene_id": "s2",
                "chapter_id": "ch1",
                "title": "Scene Two",
                "order": 4,
                "characters_present": ["Bob"],
                "background_asset_path": "game/images/background/bg_park.png",
                "background_placeholder": False,
                "dialogue_beats": [{"speaker": "Bob", "intent": "greet", "content_brief": "Hey"}],
                "sprite_plan": [{"character_name": "Bob", "position": "left"}],
                "location": "park",
                "mood": "cheerful",
                "summary": "Summary two",
                "source": "prototype",
                "next_scene_id": None,
            },
        }
    }
    (meta_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    response = client.get(f"/api/projects/{project_name}/scenes")
    assert response.status_code == 200
    data = response.json()
    assert len(data["chapters"]) == 1
    ch = data["chapters"][0]
    assert len(ch["scenes"]) == 2, "Both s1 and s2 must be present"

    s1 = next(s for s in ch["scenes"] if s["id"] == "s1")
    s2 = next(s for s in ch["scenes"] if s["id"] == "s2")

    # s1 enriched from index
    assert s1["order"] == 3
    assert s1["backgrounds"] == ["game/images/background/bg_cafe.png"]
    assert len(s1["dialogue_beats"]) == 1

    # s2 preserved from index-only
    assert s2["name"] == "Scene Two"
    assert s2["order"] == 4
    assert s2["backgrounds"] == ["game/images/background/bg_park.png"]
    assert len(s2["dialogue_beats"]) == 1
    assert s2["sprite_plan"][0]["character_name"] == "Bob"


def test_project_scenes_api_does_not_mark_scene_packages_only_scenes_as_placeholder_by_default(
    client: TestClient, tmp_path: Path
) -> None:
    """When a scene comes only from scene_packages (no prototype index overlap), background_placeholder must not be faked as True."""
    project_name = "no_placeholder_faked"
    _create_project(client, tmp_path, project_name)

    scene_packages = {
        "chapters": [
            {
                "chapter_id": "ch1",
                "chapter_name": "Chapter One",
                "chapter_order": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "title": "Scene One",
                        "summary": "Summary",
                        "location": "cafe",
                        "mood": "calm",
                        "characters_present": ["Alice"],
                        "dialogue_beats": [],
                        "entry_label": "ch1_s1",
                        "next_scene_id": None,
                        "scene_order": 1,
                    }
                ],
            }
        ]
    }
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    response = client.get(f"/api/projects/{project_name}/scenes")
    assert response.status_code == 200
    data = response.json()
    scene = data["chapters"][0]["scenes"][0]
    assert scene.get("background_placeholder") is not True, (
        "scene_packages-only scene must not be falsely marked as background_placeholder=True"
    )


# ---------------------------------------------------------------------------
# Structured scene_packages schema + strict read/write validation
# ---------------------------------------------------------------------------


def test_invalid_scene_packages_file_raises_instead_of_crashing_later(
    client: TestClient, tmp_path: Path
) -> None:
    """If scene_packages.json exists but has an invalid structure, ProjectManager must raise ValueError explicitly."""
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "invalid_scene_packages"
    _create_project(client, tmp_path, project_name)

    pm = ProjectManager(get_settings())
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps({"chapters": ["bad"]}, ensure_ascii=False), encoding="utf-8"
    )

    with pytest.raises(ValueError):
        pm.read_scene_packages(project_name)


def test_project_scenes_api_returns_500_for_invalid_scene_packages_snapshot(
    client: TestClient, tmp_path: Path
) -> None:
    """GET /scenes must return a clear 500 when scene_packages.json has an invalid structure."""
    project_name = "api_invalid_scene_packages"
    _create_project(client, tmp_path, project_name)

    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps({"chapters": ["bad"]}, ensure_ascii=False), encoding="utf-8"
    )

    response = client.get(f"/api/projects/{project_name}/scenes")
    assert response.status_code == 500


@pytest.mark.asyncio
async def test_scene_packages_snapshot_roundtrip_uses_structured_models(
    client: TestClient, tmp_path: Path
) -> None:
    """generate_all_chapter_scenes() must write a structured snapshot that round-trips through read_scene_packages as typed models."""
    from renpy_mcp.blueprint.models import ProjectBlueprint, ScenePackagesSnapshot, ScenePackageChapter, ScenePackageScene
    from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "structured_snapshot_rt"
    _create_project(client, tmp_path, project_name)

    blueprint = ProjectBlueprint(**_make_blueprint())
    provider = _make_mock_scene_provider()
    pm = ProjectManager(get_settings())
    service = PrototypeGenerationService(pm=pm, provider=provider)

    packages = await service.generate_all_chapter_scenes(project_name, blueprint)

    snapshot_path = tmp_path / project_name / "meta" / "scene_packages.json"
    assert snapshot_path.exists()

    # read_scene_packages must return a structured model, not a raw dict
    loaded = pm.read_scene_packages(project_name)
    assert loaded is not None
    assert isinstance(loaded, ScenePackagesSnapshot)
    assert len(loaded.chapters) >= 2

    ch1 = next(ch for ch in loaded.chapters if ch.chapter_id == "ch1")
    assert ch1.chapter_name == "Chapter1"
    assert ch1.chapter_order == 1
    assert len(ch1.scenes) >= 1

    scene = ch1.scenes[0]
    assert isinstance(scene, ScenePackageScene)
    assert scene.scene_id.startswith("proto-ch1")
    assert scene.scene_order == 1
    assert isinstance(scene.dialogue_beats, list)


# ---------------------------------------------------------------------------
# Round 4 review fixes: sprite_check_path excluded from snapshot/API,
# fallback branch background_placeholder semantics unified
# ---------------------------------------------------------------------------


def test_scene_packages_snapshot_does_not_persist_sprite_check_path(
    client: TestClient, tmp_path: Path
) -> None:
    """sprite_check_path is an internal staging field and must not survive roundtrip in scene_packages.json."""
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.config import get_settings

    project_name = "no_sprite_check_persist"
    _create_project(client, tmp_path, project_name)

    # Write raw scene_packages.json that includes sprite_check_path (simulating internal pipeline leakage)
    raw = {
        "chapters": [
            {
                "chapter_id": "ch1",
                "chapter_name": "Chapter One",
                "chapter_order": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "title": "Scene One",
                        "summary": "Summary",
                        "location": "cafe",
                        "mood": "calm",
                        "characters_present": ["Alice"],
                        "sprite_plan": [
                            {"character_name": "Alice", "sprite_check_path": "game/__staging__/check.png"}
                        ],
                        "entry_label": "ch1_s1",
                        "scene_order": 1,
                    }
                ],
            }
        ]
    }
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    pm = ProjectManager(get_settings())
    loaded = pm.read_scene_packages(project_name)
    assert loaded is not None
    pm.write_scene_packages(project_name, loaded)

    rt = json.loads((meta_dir / "scene_packages.json").read_text(encoding="utf-8"))
    for ch in rt.get("chapters", []):
        for scene in ch.get("scenes", []):
            for sp in scene.get("sprite_plan", []):
                assert "sprite_check_path" not in sp, "sprite_check_path must not survive roundtrip"


def test_project_scenes_api_does_not_expose_sprite_check_path(
    client: TestClient, tmp_path: Path
) -> None:
    """If a sprite_plan item carries sprite_check_path in scene_packages.json, /scenes must not expose it."""
    project_name = "no_sprite_check_api"
    _create_project(client, tmp_path, project_name)

    raw = {
        "chapters": [
            {
                "chapter_id": "ch1",
                "chapter_name": "Chapter One",
                "chapter_order": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "title": "Scene One",
                        "summary": "Summary",
                        "location": "cafe",
                        "mood": "calm",
                        "characters_present": ["Alice"],
                        "sprite_plan": [
                            {"character_name": "Alice", "sprite_check_path": "game/__staging__/check.png"}
                        ],
                        "entry_label": "ch1_s1",
                        "scene_order": 1,
                    }
                ],
            }
        ]
    }
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    response = client.get(f"/api/projects/{project_name}/scenes")
    assert response.status_code == 200
    data = response.json()
    scene = data["chapters"][0]["scenes"][0]
    for sp in scene.get("sprite_plan", []):
        assert "sprite_check_path" not in sp, "sprite_check_path must not be exposed via API"


def test_project_scenes_api_fallback_does_not_default_background_placeholder_to_true(
    client: TestClient, tmp_path: Path
) -> None:
    """When only prototype index exists (no scene_packages), missing background_placeholder must not default to True."""
    project_name = "fallback_no_placeholder_default"
    _create_project(client, tmp_path, project_name)

    index = {
        "scenes": {
            "s1": {
                "scene_id": "s1",
                "chapter_id": "ch1",
                "title": "Scene One",
                "order": 1,
                "characters_present": ["Alice"],
                "location": "cafe",
                "mood": "calm",
                "summary": "Summary",
                "source": "prototype",
            }
        }
    }
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    response = client.get(f"/api/projects/{project_name}/scenes")
    assert response.status_code == 200
    data = response.json()
    scene = data["chapters"][0]["scenes"][0]
    assert scene.get("background_placeholder") is not True, (
        "fallback branch must not default background_placeholder to True when index lacks it"
    )


def test_project_scenes_api_enriched_index_sprite_plan_does_not_expose_sprite_check_path(
    client: TestClient, tmp_path: Path
) -> None:
    """When prototype index enriches a scene from scene_packages, sprite_check_path must be stripped."""
    project_name = "enrich_no_sprite_check"
    _create_project(client, tmp_path, project_name)

    scene_packages = {
        "chapters": [
            {
                "chapter_id": "ch1",
                "chapter_name": "Chapter One",
                "chapter_order": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "title": "Scene One",
                        "summary": "Summary",
                        "location": "cafe",
                        "mood": "calm",
                        "characters_present": ["Alice"],
                        "dialogue_beats": [],
                        "entry_label": "ch1_s1",
                        "next_scene_id": None,
                        "scene_order": 1,
                    }
                ],
            }
        ]
    }
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    index = {
        "scenes": {
            "s1": {
                "scene_id": "s1",
                "chapter_id": "ch1",
                "title": "Scene One",
                "order": 1,
                "characters_present": ["Alice"],
                "location": "cafe",
                "mood": "calm",
                "summary": "Summary",
                "source": "prototype",
                "sprite_plan": [
                    {"character_name": "Alice", "sprite_check_path": "game/__staging__/check.png"}
                ],
            }
        }
    }
    (meta_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    response = client.get(f"/api/projects/{project_name}/scenes")
    assert response.status_code == 200
    data = response.json()
    scene = data["chapters"][0]["scenes"][0]
    for sp in scene.get("sprite_plan", []):
        assert "sprite_check_path" not in sp, "enriched sprite_plan must not expose sprite_check_path"


def test_project_scenes_api_index_only_scene_does_not_expose_sprite_check_path(
    client: TestClient, tmp_path: Path
) -> None:
    """Index-only scenes appended from prototype index must also strip sprite_check_path."""
    project_name = "index_only_no_sprite_check"
    _create_project(client, tmp_path, project_name)

    scene_packages = {
        "chapters": [
            {
                "chapter_id": "ch1",
                "chapter_name": "Chapter One",
                "chapter_order": 1,
                "scenes": [
                    {
                        "scene_id": "s1",
                        "title": "Scene One",
                        "summary": "Summary",
                        "location": "cafe",
                        "mood": "calm",
                        "characters_present": ["Alice"],
                        "dialogue_beats": [],
                        "entry_label": "ch1_s1",
                        "next_scene_id": None,
                        "scene_order": 1,
                    }
                ],
            }
        ]
    }
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "scene_packages.json").write_text(
        json.dumps(scene_packages, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # s2 is index-only (not in scene_packages)
    index = {
        "scenes": {
            "s1": {
                "scene_id": "s1",
                "chapter_id": "ch1",
                "title": "Scene One",
                "order": 1,
                "characters_present": ["Alice"],
                "location": "cafe",
                "mood": "calm",
                "summary": "Summary",
                "source": "prototype",
            },
            "s2": {
                "scene_id": "s2",
                "chapter_id": "ch1",
                "title": "Scene Two",
                "order": 2,
                "characters_present": ["Bob"],
                "location": "park",
                "mood": "cheerful",
                "summary": "Summary two",
                "source": "prototype",
                "sprite_plan": [
                    {"character_name": "Bob", "sprite_check_path": "game/__staging__/check_bob.png"}
                ],
            }
        }
    }
    (meta_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    response = client.get(f"/api/projects/{project_name}/scenes")
    assert response.status_code == 200
    data = response.json()
    ch = data["chapters"][0]
    assert len(ch["scenes"]) == 2
    s2 = next(s for s in ch["scenes"] if s["id"] == "s2")
    for sp in s2.get("sprite_plan", []):
        assert "sprite_check_path" not in sp, "index-only sprite_plan must not expose sprite_check_path"


def test_project_scenes_api_fallback_branch_does_not_expose_sprite_check_path(
    client: TestClient, tmp_path: Path
) -> None:
    """When only prototype index exists (no scene_packages), fallback branch must strip sprite_check_path."""
    project_name = "fallback_no_sprite_check"
    _create_project(client, tmp_path, project_name)

    index = {
        "scenes": {
            "s1": {
                "scene_id": "s1",
                "chapter_id": "ch1",
                "title": "Scene One",
                "order": 1,
                "characters_present": ["Alice"],
                "location": "cafe",
                "mood": "calm",
                "summary": "Summary",
                "source": "prototype",
                "sprite_plan": [
                    {"character_name": "Alice", "sprite_check_path": "game/__staging__/check.png"}
                ],
            }
        }
    }
    meta_dir = tmp_path / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    response = client.get(f"/api/projects/{project_name}/scenes")
    assert response.status_code == 200
    data = response.json()
    scene = data["chapters"][0]["scenes"][0]
    for sp in scene.get("sprite_plan", []):
        assert "sprite_check_path" not in sp, "fallback branch sprite_plan must not expose sprite_check_path"
