"""Blueprint and project metadata models for the unified dashboard."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

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


class ProjectMeta(BaseModel):
    """Canonical project metadata persisted in meta/project.json."""

    name: str
    path: Path
    status: ProjectStatus = ProjectStatus.DRAFT
    pipeline_stage: PipelineStage = PipelineStage.IDLE
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
