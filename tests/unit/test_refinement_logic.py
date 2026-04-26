"""Unit tests for refinement domain logic extracted from create_app().

These functions were previously closures inside the God Function create_app()
and could only be tested through HTTP integration tests. After extraction to
services/refinement_logic.py, they can be unit-tested directly.
"""

from datetime import datetime
from pathlib import Path

import pytest

from renpy_mcp.blueprint.models import (
    BlueprintCharacter,
    BlueprintFreezeStatus,
    BriefCard,
    ChapterIntakeEntry,
    ChapterOutline,
    ChapterOutlineEntry,
    ChapterSummary,
    IntakePhase,
    IntakeSlot,
    PipelineStage,
    ProjectBlueprint,
    ProjectBrief,
    ProjectMeta,
    ProjectStatus,
    RefinementIntake,
    RefinementState,
)

# Import from the new module location (will fail until implementation)
from renpy_mcp.services.refinement_logic import (
    assemble_frozen_blueprint,
    brief_card_text,
    build_chapter_intake_entries_from_blueprint,
    compute_blueprint_freeze_status,
    compute_refinement_state,
    freeze_status_after_upstream_change,
    intake_slot_content,
    is_brief_fully_confirmed,
    is_character_identity_card_valid,
    is_outline_fully_confirmed,
    materialize_brief_from_intake,
    materialize_outline_from_intake,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_brief(cards: dict[str, BriefCard] | None = None) -> ProjectBrief:
    """Create a ProjectBrief with optional card overrides."""
    default_cards = {
        "core_premise": BriefCard(content="A story", confirmed=True),
        "audience_genre": BriefCard(content="Fantasy", confirmed=True),
        "tone_themes": BriefCard(content="dark, gritty", confirmed=True),
        "visual_style": BriefCard(content="anime", confirmed=True),
        "world_rules": BriefCard(content="magic exists", confirmed=True),
        "core_cast": BriefCard(content="hero, villain", confirmed=True),
        "character_identity": BriefCard(
            content={"characters": [{"name": "Alice", "story_role": "protagonist"}]},
            confirmed=True,
        ),
        "relationship_baselines": BriefCard(
            content={"relationships": []},
            confirmed=True,
        ),
        "constraints": BriefCard(content="none", confirmed=True),
    }
    if cards:
        default_cards.update(cards)
    return ProjectBrief(cards=default_cards, updated_at=datetime.utcnow().isoformat())


def _make_confirmed_outline(n_chapters: int = 2) -> ChapterOutline:
    """Create a fully-confirmed ChapterOutline."""
    return ChapterOutline(
        chapters=[
            ChapterOutlineEntry(
                chapter_id=f"ch{i+1}",
                order=i + 1,
                chapter_name=f"Chapter {i+1}",
                confirmed=True,
            )
            for i in range(n_chapters)
        ],
        updated_at=datetime.utcnow().isoformat(),
    )


def _make_meta(**overrides) -> ProjectMeta:
    defaults = dict(
        name="test",
        path=Path("."),
        status=ProjectStatus.DRAFT,
        pipeline_stage=PipelineStage.IDLE,
    )
    defaults.update(overrides)
    return ProjectMeta(**defaults)


# ---------------------------------------------------------------------------
# is_brief_fully_confirmed
# ---------------------------------------------------------------------------

class TestIsBriefFullyConfirmed:
    def test_empty_cards_returns_false(self):
        brief = ProjectBrief(cards={})
        assert is_brief_fully_confirmed(brief) is False

    def test_all_confirmed_returns_true(self):
        brief = _make_brief()
        assert is_brief_fully_confirmed(brief) is True

    def test_one_unconfirmed_returns_false(self):
        brief = _make_brief({"core_premise": BriefCard(content="A story", confirmed=False)})
        assert is_brief_fully_confirmed(brief) is False

    def test_empty_character_identity_returns_false(self):
        brief = _make_brief({
            "character_identity": BriefCard(
                content={"characters": []},
                confirmed=True,
            ),
        })
        assert is_brief_fully_confirmed(brief) is False

    def test_character_without_substance_returns_false(self):
        brief = _make_brief({
            "character_identity": BriefCard(
                content={"characters": [{"name": "", "story_role": ""}]},
                confirmed=True,
            ),
        })
        assert is_brief_fully_confirmed(brief) is False


# ---------------------------------------------------------------------------
# is_character_identity_card_valid
# ---------------------------------------------------------------------------

class TestIsCharacterIdentityCardValid:
    def test_non_dict_content(self):
        card = BriefCard(content="just a string", confirmed=True)
        assert is_character_identity_card_valid(card) is False

    def test_empty_characters_list(self):
        card = BriefCard(content={"characters": []}, confirmed=True)
        assert is_character_identity_card_valid(card) is False

    def test_name_only_character_is_not_valid(self):
        card = BriefCard(content={"characters": [{"name": "Alice"}]}, confirmed=True)
        assert is_character_identity_card_valid(card) is False

    def test_valid_character_by_role(self):
        card = BriefCard(
            content={"characters": [{"name": "", "story_role": "hero"}]},
            confirmed=True,
        )
        assert is_character_identity_card_valid(card) is True

    def test_valid_character_by_personality_anchors(self):
        card = BriefCard(
            content={"characters": [{"personality_anchors": ["brave"]}]},
            confirmed=True,
        )
        assert is_character_identity_card_valid(card) is True


# ---------------------------------------------------------------------------
# is_outline_fully_confirmed
# ---------------------------------------------------------------------------

class TestIsOutlineFullyConfirmed:
    def test_empty_chapters(self):
        outline = ChapterOutline(chapters=[])
        assert is_outline_fully_confirmed(outline) is False

    def test_all_confirmed(self):
        outline = _make_confirmed_outline()
        assert is_outline_fully_confirmed(outline) is True

    def test_one_unconfirmed(self):
        outline = ChapterOutline(chapters=[
            ChapterOutlineEntry(chapter_id="ch1", confirmed=True),
            ChapterOutlineEntry(chapter_id="ch2", confirmed=False),
        ])
        assert is_outline_fully_confirmed(outline) is False


# ---------------------------------------------------------------------------
# compute_refinement_state
# ---------------------------------------------------------------------------

class TestComputeRefinementState:
    def test_both_none_returns_none(self):
        assert compute_refinement_state(None, None) is None

    def test_brief_not_confirmed(self):
        brief = ProjectBrief(cards={"x": BriefCard(content="y", confirmed=False)})
        assert compute_refinement_state(brief, None) == RefinementState.BRIEF_REVIEWING

    def test_brief_confirmed_no_outline(self):
        brief = _make_brief()
        assert compute_refinement_state(brief, None) == RefinementState.BRIEF_CONFIRMED

    def test_brief_confirmed_empty_outline(self):
        brief = _make_brief()
        outline = ChapterOutline(chapters=[])
        assert compute_refinement_state(brief, outline) == RefinementState.BRIEF_CONFIRMED

    def test_brief_confirmed_outline_reviewing(self):
        brief = _make_brief()
        outline = ChapterOutline(chapters=[
            ChapterOutlineEntry(chapter_id="ch1", confirmed=False),
        ])
        assert compute_refinement_state(brief, outline) == RefinementState.CHAPTER_OUTLINE_REVIEWING

    def test_both_confirmed_blueprint_ready(self):
        brief = _make_brief()
        outline = _make_confirmed_outline()
        assert compute_refinement_state(brief, outline) == RefinementState.BLUEPRINT_READY

    def test_outline_without_brief_returns_idea_collecting(self):
        outline = _make_confirmed_outline()
        assert compute_refinement_state(None, outline) == RefinementState.IDEA_COLLECTING


# ---------------------------------------------------------------------------
# compute_blueprint_freeze_status
# ---------------------------------------------------------------------------

class TestComputeBlueprintFreezeStatus:
    def test_no_brief_no_outline_returns_meta_status(self):
        meta = _make_meta(blueprint_freeze_status=BlueprintFreezeStatus.FROZEN)
        assert compute_blueprint_freeze_status(meta, None, None) == BlueprintFreezeStatus.FROZEN

    def test_no_brief_no_outline_no_meta(self):
        assert compute_blueprint_freeze_status(None, None, None) is None

    def test_frozen_preserves_frozen(self):
        meta = _make_meta(blueprint_freeze_status=BlueprintFreezeStatus.FROZEN)
        brief = _make_brief()
        outline = _make_confirmed_outline()
        assert compute_blueprint_freeze_status(meta, brief, outline) == BlueprintFreezeStatus.FROZEN

    def test_stale_preserves_stale(self):
        meta = _make_meta(blueprint_freeze_status=BlueprintFreezeStatus.STALE)
        brief = _make_brief()
        outline = _make_confirmed_outline()
        assert compute_blueprint_freeze_status(meta, brief, outline) == BlueprintFreezeStatus.STALE

    def test_not_frozen_returns_not_frozen(self):
        meta = _make_meta(blueprint_freeze_status=BlueprintFreezeStatus.NOT_FROZEN)
        brief = _make_brief()
        outline = _make_confirmed_outline()
        assert compute_blueprint_freeze_status(meta, brief, outline) == BlueprintFreezeStatus.NOT_FROZEN

    def test_no_meta_returns_not_frozen(self):
        brief = _make_brief()
        outline = _make_confirmed_outline()
        assert compute_blueprint_freeze_status(None, brief, outline) == BlueprintFreezeStatus.NOT_FROZEN


# ---------------------------------------------------------------------------
# freeze_status_after_upstream_change
# ---------------------------------------------------------------------------

class TestFreezeStatusAfterUpstreamChange:
    def test_frozen_becomes_stale(self):
        assert freeze_status_after_upstream_change(BlueprintFreezeStatus.FROZEN) == BlueprintFreezeStatus.STALE

    def test_stale_stays_stale(self):
        assert freeze_status_after_upstream_change(BlueprintFreezeStatus.STALE) == BlueprintFreezeStatus.STALE

    def test_not_frozen_stays_not_frozen(self):
        assert freeze_status_after_upstream_change(BlueprintFreezeStatus.NOT_FROZEN) == BlueprintFreezeStatus.NOT_FROZEN

    def test_none_becomes_not_frozen(self):
        assert freeze_status_after_upstream_change(None) == BlueprintFreezeStatus.NOT_FROZEN


# ---------------------------------------------------------------------------
# brief_card_text / intake_slot_content
# ---------------------------------------------------------------------------

class TestBriefCardText:
    def test_existing_string_card(self):
        brief = _make_brief()
        assert brief_card_text(brief, "core_premise") == "A story"

    def test_missing_card_returns_empty(self):
        brief = _make_brief()
        assert brief_card_text(brief, "nonexistent") == ""

    def test_dict_content_returns_empty(self):
        brief = _make_brief()
        # character_identity has dict content
        assert brief_card_text(brief, "character_identity") == ""


class TestIntakeSlotContent:
    def test_existing_slot(self):
        intake = RefinementIntake(
            slots={"premise": IntakeSlot(value="A great story")}
        )
        assert intake_slot_content(intake, "premise", "") == "A great story"

    def test_missing_slot_returns_default(self):
        intake = RefinementIntake(slots={})
        assert intake_slot_content(intake, "premise", "fallback") == "fallback"

    def test_null_value_returns_default(self):
        intake = RefinementIntake(
            slots={"premise": IntakeSlot(value=None)}
        )
        assert intake_slot_content(intake, "premise", "fallback") == "fallback"


# ---------------------------------------------------------------------------
# materialize_brief_from_intake
# ---------------------------------------------------------------------------

class TestMaterializeBriefFromIntake:
    def test_produces_all_expected_cards(self):
        intake = RefinementIntake(
            slots={
                "core_premise": IntakeSlot(value="A dark fantasy"),
                "audience_genre": IntakeSlot(value="YA Fantasy"),
                "tone_themes": IntakeSlot(value="grim, hopeful"),
                "visual_style": IntakeSlot(value="watercolor"),
                "world_rules": IntakeSlot(value="magic costs memory"),
                "core_cast": IntakeSlot(value="Alice and Bob"),
                "character_identity": IntakeSlot(value={"characters": [{"name": "Alice"}]}),
                "relationship_baselines": IntakeSlot(value={"relationships": []}),
                "constraints": IntakeSlot(value="PG-13"),
            }
        )
        brief = materialize_brief_from_intake(intake)
        assert set(brief.cards.keys()) == {
            "core_premise", "audience_genre", "tone_themes", "visual_style",
            "world_rules", "core_cast", "character_identity",
            "relationship_baselines", "constraints",
        }
        assert brief.cards["core_premise"].content == "A dark fantasy"
        assert brief.cards["character_identity"].content == {"characters": [{"name": "Alice"}]}


# ---------------------------------------------------------------------------
# materialize_outline_from_intake
# ---------------------------------------------------------------------------

class TestMaterializeOutlineFromIntake:
    def test_creates_unconfirmed_chapters(self):
        intake = RefinementIntake(
            chapter_draft=[
                ChapterIntakeEntry(
                    chapter_id="ch1", order=1, chapter_name="Prologue",
                    chapter_goal="Set the scene",
                ),
                ChapterIntakeEntry(
                    chapter_id="ch2", order=2, chapter_name="Journey",
                    chapter_goal="Begin the quest",
                ),
            ]
        )
        outline = materialize_outline_from_intake(intake)
        assert len(outline.chapters) == 2
        assert outline.chapters[0].chapter_id == "ch1"
        assert outline.chapters[0].chapter_name == "Prologue"
        assert outline.chapters[0].confirmed is False
        assert outline.chapters[1].chapter_goal == "Begin the quest"


# ---------------------------------------------------------------------------
# assemble_frozen_blueprint
# ---------------------------------------------------------------------------

class TestAssembleFrozenBlueprint:
    def test_assembles_valid_blueprint(self):
        brief = _make_brief()
        outline = _make_confirmed_outline()
        bp = assemble_frozen_blueprint("test_project", brief, outline)
        assert bp.title == "test_project"
        assert bp.genre == "Fantasy"
        assert len(bp.characters) == 1
        assert bp.characters[0].name == "Alice"
        assert len(bp.chapters) == 2
        assert bp.chapters[0].name == "Chapter 1"

    def test_raises_if_brief_not_confirmed(self):
        brief = ProjectBrief(cards={"x": BriefCard(content="y", confirmed=False)})
        outline = _make_confirmed_outline()
        with pytest.raises(ValueError, match="Cannot freeze"):
            assemble_frozen_blueprint("test", brief, outline)

    def test_raises_if_outline_not_confirmed(self):
        brief = _make_brief()
        outline = ChapterOutline(chapters=[
            ChapterOutlineEntry(chapter_id="ch1", confirmed=False),
        ])
        with pytest.raises(ValueError, match="Cannot freeze"):
            assemble_frozen_blueprint("test", brief, outline)

    def test_themes_split_from_tone_themes(self):
        brief = _make_brief({"tone_themes": BriefCard(content="dark, mystery\nhope", confirmed=True)})
        outline = _make_confirmed_outline()
        bp = assemble_frozen_blueprint("test", brief, outline)
        assert "dark" in bp.themes
        assert "mystery" in bp.themes
        assert "hope" in bp.themes


# ---------------------------------------------------------------------------
# INTAKE_SLOT_KEYS constant
# ---------------------------------------------------------------------------

class TestIntakeSlotKeys:
    def test_slot_keys_is_list(self):
        from renpy_mcp.services.refinement_logic import INTAKE_SLOT_KEYS
        assert isinstance(INTAKE_SLOT_KEYS, list)

    def test_slot_keys_contains_expected_keys(self):
        from renpy_mcp.services.refinement_logic import INTAKE_SLOT_KEYS
        expected = {
            "core_premise", "audience_genre", "tone_themes",
            "visual_style", "world_rules", "core_cast",
            "character_identity", "relationship_baselines", "constraints",
        }
        assert set(INTAKE_SLOT_KEYS) == expected

    def test_slot_keys_has_nine_entries(self):
        from renpy_mcp.services.refinement_logic import INTAKE_SLOT_KEYS
        assert len(INTAKE_SLOT_KEYS) == 9


class TestCollectingResponse:
    def test_refinement_intake_opening_is_short_and_not_legacy_questionnaire(self):
        from renpy_mcp.services.refinement_logic import select_collecting_response

        content, message_kind = select_collecting_response(
            turn_count=0,
            intake_mode=True,
            lang="en",
        )

        assert message_kind == "intake_text"
        assert "Project Brief" in content
        assert "dynamically" in content
        assert "roughly how many chapters" not in content
        assert "who are the main characters" not in content


# ---------------------------------------------------------------------------
# compute_refinement_intake
# ---------------------------------------------------------------------------

def _make_draft_blueprint() -> ProjectBlueprint:
    return ProjectBlueprint(
        title="Test",
        genre="Fantasy",
        worldview="Medieval",
        themes=["adventure"],
        target_audience="YA",
        estimated_play_time="1hr",
        art_style="Anime",
        audio_style="Orchestral",
        characters=[
            {"name": "Alice", "role": "protagonist", "personality": "brave", "appearance": "tall"},
            {"name": "Bob", "role": "antagonist", "personality": "cunning", "appearance": "dark"},
        ],
        chapters=[
            {
                "id": "ch1", "name": "Beginning", "order": 1,
                "scenes": [{"id": "s1", "name": "Intro", "order": 1}],
            },
            {
                "id": "ch2", "name": "End", "order": 2,
                "scenes": [{"id": "s2", "name": "Finale", "order": 1}],
            },
        ],
    )


class TestComputeRefinementIntake:
    def test_collecting_project_level_no_brief(self):
        """COLLECTING phase, brief not confirmed → IntakePhase.PROJECT."""
        from renpy_mcp.services.refinement_logic import compute_refinement_intake

        intake = compute_refinement_intake(
            orchestrator_phase=PipelineStage.COLLECTING,
            draft=None,
            brief_confirmed=False,
        )
        assert intake.phase == IntakePhase.PROJECT
        assert intake.brief_draft_ready is False
        assert intake.outline_draft_ready is False
        assert len(intake.slots) == 9

    def test_collecting_project_level_populates_core_premise(self):
        """latest_user_content should populate core_premise slot."""
        from renpy_mcp.services.refinement_logic import compute_refinement_intake

        intake = compute_refinement_intake(
            orchestrator_phase=PipelineStage.COLLECTING,
            draft=None,
            brief_confirmed=False,
            latest_user_content="A romance story in modern Tokyo",
        )
        assert intake.phase == IntakePhase.PROJECT
        assert intake.slots["core_premise"].value == "A romance story in modern Tokyo"
        assert intake.slots["core_premise"].complete is True

    def test_collecting_chapter_level_when_brief_confirmed(self):
        """COLLECTING phase, brief confirmed → IntakePhase.CHAPTER."""
        from renpy_mcp.services.refinement_logic import compute_refinement_intake

        intake = compute_refinement_intake(
            orchestrator_phase=PipelineStage.COLLECTING,
            draft=None,
            brief_confirmed=True,
        )
        assert intake.phase == IntakePhase.CHAPTER
        assert intake.brief_draft_ready is True
        assert intake.outline_draft_ready is False

    def test_reviewing_brief_ready_when_brief_not_confirmed(self):
        """REVIEWING with draft but brief not confirmed → IntakePhase.BRIEF_READY."""
        from renpy_mcp.services.refinement_logic import compute_refinement_intake

        draft = _make_draft_blueprint()
        intake = compute_refinement_intake(
            orchestrator_phase=PipelineStage.REVIEWING,
            draft=draft,
            brief_confirmed=False,
        )
        assert intake.phase == IntakePhase.BRIEF_READY
        assert intake.brief_draft_ready is True
        assert intake.outline_draft_ready is False
        assert "core_premise" in intake.slots
        assert intake.slots["character_identity"].complete is True

    def test_reviewing_outline_ready_when_brief_confirmed(self):
        """REVIEWING with draft and brief confirmed → IntakePhase.OUTLINE_READY."""
        from renpy_mcp.services.refinement_logic import compute_refinement_intake

        draft = _make_draft_blueprint()
        intake = compute_refinement_intake(
            orchestrator_phase=PipelineStage.REVIEWING,
            draft=draft,
            brief_confirmed=True,
        )
        assert intake.phase == IntakePhase.OUTLINE_READY
        assert intake.brief_draft_ready is True
        assert intake.outline_draft_ready is True
        assert len(intake.chapter_draft) == 2
        assert intake.chapter_draft[0].chapter_id == "ch1"
        assert intake.chapter_draft[1].chapter_id == "ch2"

    def test_reviewing_character_slots_built_from_draft(self):
        """REVIEWING extracts character details from draft into character_identity slot."""
        from renpy_mcp.services.refinement_logic import compute_refinement_intake

        draft = _make_draft_blueprint()
        intake = compute_refinement_intake(
            orchestrator_phase=PipelineStage.REVIEWING,
            draft=draft,
            brief_confirmed=False,
        )
        char_slot = intake.slots["character_identity"]
        assert isinstance(char_slot.value, dict)
        chars = char_slot.value["characters"]
        assert len(chars) == 2
        assert chars[0]["name"] == "Alice"
        assert chars[0]["story_role"] == "protagonist"

    def test_idle_phase_treated_as_collecting(self):
        """IDLE phase behaves the same as COLLECTING."""
        from renpy_mcp.services.refinement_logic import compute_refinement_intake

        intake = compute_refinement_intake(
            orchestrator_phase=PipelineStage.IDLE,
            draft=None,
            brief_confirmed=False,
            latest_user_content="Hello",
        )
        assert intake.phase == IntakePhase.PROJECT


# ---------------------------------------------------------------------------
# Structural tests for P2-3 split
# ---------------------------------------------------------------------------

class TestOrchestratorSplitStructure:
    def test_blueprint_generation_service_importable(self):
        from renpy_mcp.services.blueprint_generation import BlueprintGenerationService
        assert BlueprintGenerationService is not None

    def test_prototype_orchestration_service_importable(self):
        from renpy_mcp.services.prototype_orchestration import PrototypeOrchestrationService
        assert PrototypeOrchestrationService is not None

    def test_orchestrator_line_count_reduced(self):
        """BlueprintOrchestrator class should be significantly smaller after extraction."""
        import inspect
        from renpy_mcp.web.chat_ws import BlueprintOrchestrator
        source = inspect.getsource(BlueprintOrchestrator)
        line_count = len(source.splitlines())
        # Original: ~1089 lines. Target: < 650 lines (at least 40% reduction)
        assert line_count < 650, f"BlueprintOrchestrator is still {line_count} lines"
