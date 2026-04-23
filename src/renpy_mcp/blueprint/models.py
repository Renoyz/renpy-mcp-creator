"""Blueprint and project metadata models for the unified dashboard."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class ProjectStatus(StrEnum):
    """Lifecycle status of a Ren'Py project."""

    DRAFT = "draft"
    BLUEPRINTING = "blueprinting"
    BLUEPRINTED = "blueprinted"
    GENERATING = "generating"
    EDITING = "editing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class PipelineStage(StrEnum):
    """High-level pipeline stage exposed to the frontend."""

    IDLE = "idle"
    COLLECTING = "collecting"
    REVIEWING = "reviewing"
    GENERATING = "generating"
    EDITING = "editing"


class RefinementState(StrEnum):
    """Staged refinement states for the requirements funnel."""

    IDEA_COLLECTING = "idea_collecting"
    BRIEF_DRAFT = "brief_draft"
    BRIEF_REVIEWING = "brief_reviewing"
    BRIEF_CONFIRMED = "brief_confirmed"
    CHAPTER_OUTLINE_DRAFT = "chapter_outline_draft"
    CHAPTER_OUTLINE_REVIEWING = "chapter_outline_reviewing"
    CHAPTER_OUTLINE_CONFIRMED = "chapter_outline_confirmed"
    BLUEPRINT_READY = "blueprint_ready"


class BlueprintFreezeStatus(StrEnum):
    """Frozen-blueprint status layered on top of refinement readiness."""

    NOT_FROZEN = "not_frozen"
    FROZEN = "frozen"
    STALE = "stale"


class ProjectMeta(BaseModel):
    """Canonical project metadata persisted in meta/project.json."""

    name: str
    path: Path
    status: ProjectStatus = ProjectStatus.DRAFT
    pipeline_stage: PipelineStage = PipelineStage.IDLE
    refinement_state: RefinementState | None = None
    blueprint_freeze_status: BlueprintFreezeStatus | None = None
    chapter_count: int = 0
    scene_count: int = 0
    confirmed_scenes: int = 0
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    description: str | None = None
    genre: str | None = None


class BlueprintCharacter(BaseModel):
    """Character definition inside a blueprint."""

    name: str
    role: str
    personality: str
    appearance: str
    variants: list[str] | None = None


class ChoiceItem(BaseModel):
    """Branch choice inside a scene summary."""

    text: str
    next_scene_id: str
    condition: str | None = None


class SceneSummary(BaseModel):
    """Lightweight scene descriptor used in blueprints and APIs."""

    id: str
    name: str
    order: int
    characters: list[str] = Field(default_factory=list)
    backgrounds: list[str] = Field(default_factory=list)
    music: str | None = None
    choices: list[ChoiceItem] | None = None
    ending_name: str | None = None
    status: str = "pending"
    type: str = "normal"
    is_ending: bool | None = None


class ChapterSummary(BaseModel):
    """Chapter descriptor used in blueprints."""

    id: str
    name: str
    order: int
    scenes: list[SceneSummary] = Field(default_factory=list)


class ProjectBlueprint(BaseModel):
    """Complete project blueprint persisted in meta/blueprint.yaml."""

    title: str
    genre: str
    worldview: str
    themes: list[str] = Field(default_factory=list)
    target_audience: str = ""
    estimated_play_time: str = ""
    art_style: str = ""
    audio_style: str = ""
    characters: list[BlueprintCharacter] = Field(default_factory=list)
    chapters: list[ChapterSummary] = Field(default_factory=list)


class SceneScript(BaseModel):
    """Script payload for a single scene."""

    scene_id: str
    chapter_id: str
    label: str
    content: str
    file_path: str


class FlowNode(BaseModel):
    """Node in the story map graph."""

    id: str
    chapter_id: str
    scene_id: str
    type: str = "normal"
    label: str | None = None


class FlowEdge(BaseModel):
    """Edge in the story map graph."""

    from_chapter_id: str
    from_scene_id: str
    to_chapter_id: str
    to_scene_id: str
    type: str = "main"
    choice_id: str | None = None
    label: str | None = None


# ---------------------------------------------------------------------------
# Phase 6: Style consistency models
# ---------------------------------------------------------------------------


class VisualBible(BaseModel):
    """Project-wide visual constraints."""

    art_direction: str = ""
    palette_baseline: str = ""
    camera_language: str = ""
    background_complexity_budget: str = "medium"
    forbidden_visual_drift: list[str] = Field(default_factory=list)
    mood_target: str = ""
    temperature_bias: str = ""
    lighting_bias: str = ""
    location_motifs: list[str] = Field(default_factory=list)


class CharacterStyleEntry(BaseModel):
    """Character identity anchors that must remain stable across chapters."""

    name: str
    identity_anchors: list[str] = Field(default_factory=list)
    default_costume: str = ""
    forbidden_drift: list[str] = Field(default_factory=list)


class CharacterBible(BaseModel):
    """Project-wide character constraints."""

    characters: list[CharacterStyleEntry] = Field(default_factory=list)


class ToneBible(BaseModel):
    """Project-wide tone and dialogue constraints."""

    narration_style: str = ""
    dialogue_style: str = ""
    dialogue_density: str = ""
    forbidden_tone_drift: list[str] = Field(default_factory=list)
    pacing_bias: str = ""
    emotional_bias: str = ""
    mood_target: str = ""


class ContinuityBible(BaseModel):
    """Project-wide continuity constraints."""

    world_rules: list[str] = Field(default_factory=list)
    relationship_baselines: list[str] = Field(default_factory=list)
    must_preserve_facts: list[str] = Field(default_factory=list)


class ProjectStyleBible(BaseModel):
    """Project-wide canonical style bible persisted in meta/style_bible.json."""

    visual_bible: VisualBible = Field(default_factory=VisualBible)
    character_bible: CharacterBible = Field(default_factory=CharacterBible)
    tone_bible: ToneBible = Field(default_factory=ToneBible)
    continuity_bible: ContinuityBible = Field(default_factory=ContinuityBible)


class ChapterStyleProfile(BaseModel):
    """Chapter-level controlled style profile."""

    chapter_id: str
    mood_target: str = ""
    temperature_bias: str = ""
    lighting_bias: str = ""
    pacing_bias: str = ""
    emotional_bias: str = ""
    location_motifs: list[str] = Field(default_factory=list)
    allowed_variation: dict = Field(default_factory=dict)


class ChapterStyleProfiles(BaseModel):
    """Wrapper for all chapter style profiles persisted in meta/chapter_style_profiles.json."""

    chapters: list[ChapterStyleProfile] = Field(default_factory=list)


class VisualContract(BaseModel):
    """Merged visual constraints for a single chapter generation."""

    art_direction: str = ""
    palette_baseline: str = ""
    camera_language: str = ""
    background_complexity_budget: str = "medium"
    forbidden_visual_drift: list[str] = Field(default_factory=list)
    mood_target: str = ""
    temperature_bias: str = ""
    lighting_bias: str = ""
    location_motifs: list[str] = Field(default_factory=list)


class CharacterContract(BaseModel):
    """Merged character constraints for a single chapter generation."""

    characters: list[CharacterStyleEntry] = Field(default_factory=list)


class ToneContract(BaseModel):
    """Merged tone constraints for a single chapter generation."""

    narration_style: str = ""
    dialogue_style: str = ""
    dialogue_density: str = ""
    forbidden_tone_drift: list[str] = Field(default_factory=list)
    pacing_bias: str = ""
    emotional_bias: str = ""
    mood_target: str = ""


class ContinuityContract(BaseModel):
    """Merged continuity constraints for a single chapter generation."""

    must_preserve_facts: list[str] = Field(default_factory=list)
    relationship_state: list[str] = Field(default_factory=list)
    world_rules: list[str] = Field(default_factory=list)


class GenerationContract(BaseModel):
    """Normalized runtime contract assembled from project bible + chapter profile.

    This is what generation code actually consumes.  It is not an authoring
    format; it is the deterministic, merged input for prompts.
    """

    chapter_id: str
    visual_contract: VisualContract = Field(default_factory=VisualContract)
    character_contract: CharacterContract = Field(default_factory=CharacterContract)
    tone_contract: ToneContract = Field(default_factory=ToneContract)
    continuity_contract: ContinuityContract = Field(default_factory=ContinuityContract)


# ---------------------------------------------------------------------------
# Phase 6: Scene package snapshot models
# ---------------------------------------------------------------------------


class DialogueBeat(BaseModel):
    """A single dialogue beat within a scene."""

    speaker: str
    intent: str
    content_brief: str
    spoken_line: str = ""


class SpritePlanItem(BaseModel):
    """A single character sprite placement within a scene (runtime internal model).

    Carries internal fields such as ``sprite_check_path`` that are useful for
    the generation pipeline but must not be persisted to the canonical snapshot
    or exposed through the API.
    """

    character_name: str
    character_id: str = ""
    sprite_path: str | None = None
    sprite_check_path: str | None = None
    sprite_placeholder: bool = True
    sprite_renderable: bool = False
    sprite_quality_reason: str = ""
    position: str = "center"
    expression: str = "neutral"
    layout_mode: str = "solo"
    transform_name: str = "proto_center_solo"


class ScenePackageSpritePlanItem(BaseModel):
    """A narrow sprite plan item used in the canonical scene package snapshot.

    Excludes internal staging fields (e.g. ``sprite_check_path``) so that the
    persisted snapshot and API surface remain clean.
    """

    character_name: str
    character_id: str = ""
    sprite_path: str | None = None
    sprite_placeholder: bool = True
    sprite_renderable: bool = False
    sprite_quality_reason: str = ""
    position: str = "center"
    expression: str = "neutral"
    layout_mode: str = "solo"
    transform_name: str = "proto_center_solo"


class ScenePackageScene(BaseModel):
    """A single scene inside a scene package snapshot."""

    scene_id: str
    title: str
    summary: str
    location: str
    location_visual_brief: str = ""
    mood: str = ""
    characters_present: list[str] = Field(default_factory=list)
    dialogue_beats: list[DialogueBeat] = Field(default_factory=list)
    sprite_plan: list[ScenePackageSpritePlanItem] = Field(default_factory=list)
    entry_label: str = ""
    next_scene_id: str | None = None
    scene_order: int = 1


class ScenePackageChapter(BaseModel):
    """A single chapter inside a scene package snapshot."""

    chapter_id: str
    chapter_name: str = ""
    chapter_order: int = 1
    scenes: list[ScenePackageScene] = Field(default_factory=list)


class ScenePackagesSnapshot(BaseModel):
    """Canonical multi-chapter scene package snapshot persisted in meta/scene_packages.json."""

    chapters: list[ScenePackageChapter] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 6 Round 3: Prototype manifest
# ---------------------------------------------------------------------------


class PrototypeManifest(BaseModel):
    """Canonical prototype activation state persisted in meta/prototype_manifest.json.

    This is the single source of truth for the project's active prototype mode
    and runtime entry metadata.  It is distinct from scene_packages.json (content
    snapshot) and index.json (scene-to-file mapping).
    """

    mode: Literal["single_chapter", "multi_chapter"] | None = None
    entry_label: str | None = None
    entry_file: str | None = None
    chapter_ids: list[str] = Field(default_factory=list)
    script_files: list[str] = Field(default_factory=list)
    source: str = "prototype"
    generated_from: str | None = None
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Phase 7 Round 1: Requirements refinement
# ---------------------------------------------------------------------------


class CharacterIdentityEntry(BaseModel):
    """Major character identity anchors that must be locked before brief confirmation."""

    character_id: str
    name: str
    story_role: str = ""
    core_motivation: str = ""
    personality_anchors: list[str] = Field(default_factory=list)
    visual_identity_anchors: list[str] = Field(default_factory=list)
    forbidden_drift: list[str] = Field(default_factory=list)


class RelationshipBaselineEntry(BaseModel):
    """Relationship baseline between two characters."""

    pair: list[str] = Field(default_factory=list)
    baseline: str = ""
    must_preserve: list[str] = Field(default_factory=list)


class BriefCard(BaseModel):
    """A single card inside the Project Brief."""

    content: str | dict = ""
    confirmed: bool = False


class ProjectBrief(BaseModel):
    """Canonical project brief persisted in meta/project_brief.json."""

    cards: dict[str, BriefCard] = Field(default_factory=dict)
    updated_at: str = ""


class ChapterOutlineEntry(BaseModel):
    """A single chapter inside the Chapter Outline."""

    chapter_id: str
    order: int = 1
    chapter_name: str = ""
    chapter_goal: str = ""
    key_conflict: str = ""
    emotional_arc: str = ""
    reveals: str = ""
    end_state: str = ""
    mood_or_pacing_bias: str = ""
    character_focus: list[str] = Field(default_factory=list)
    relationship_shift: str = ""
    character_presentation_notes: str = ""
    confirmed: bool = False


class ChapterOutline(BaseModel):
    """Canonical chapter outline persisted in meta/chapter_outline.json."""

    chapters: list[ChapterOutlineEntry] = Field(default_factory=list)
    updated_at: str = ""
