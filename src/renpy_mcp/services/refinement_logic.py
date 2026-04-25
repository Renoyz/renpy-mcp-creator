"""Pure domain logic for requirements refinement.

Extracted from the God Function ``create_app()`` in ``web/fastapi_app.py``
(P2-2) so that these functions can be:

* unit-tested without HTTP
* reused across multiple routers and services
* reasoned about independently of transport
"""

from __future__ import annotations

import re
from datetime import datetime

from ..blueprint.models import (
    BlueprintCharacter,
    BlueprintFreezeStatus,
    BriefCard,
    ChapterIntakeEntry,
    ChapterOutline,
    ChapterOutlineEntry,
    ChapterSummary,
    IntakeSlot,
    PipelineStage,
    ProjectBlueprint,
    ProjectBrief,
    ProjectMeta,
    ProjectStatus,
    RefinementIntake,
    RefinementState,
)
from ..blueprint.outline_derivation import derive_chapter_outline_fields


# ---------------------------------------------------------------------------
# Brief / outline confirmation predicates
# ---------------------------------------------------------------------------

def is_brief_fully_confirmed(brief: ProjectBrief) -> bool:
    if not brief.cards:
        return False
    for card_key, card in brief.cards.items():
        if not card.confirmed:
            return False
        if card_key == "character_identity":
            if not is_character_identity_card_valid(card):
                return False
    return True


def is_character_identity_card_valid(card: BriefCard) -> bool:
    """Reject empty character identity cards."""
    if not isinstance(card.content, dict):
        return False
    characters = card.content.get("characters", [])
    if not characters:
        return False
    for entry in characters:
        has_substance = bool(
            entry.get("name", "").strip()
            or entry.get("story_role", "").strip()
            or entry.get("core_motivation", "").strip()
            or entry.get("personality_anchors", [])
            or entry.get("visual_identity_anchors", [])
            or entry.get("forbidden_drift", [])
        )
        if not has_substance:
            return False
    return True


def is_outline_fully_confirmed(outline: ChapterOutline) -> bool:
    if not outline.chapters:
        return False
    return all(ch.confirmed for ch in outline.chapters)


# ---------------------------------------------------------------------------
# State computation (pure functions — no disk I/O)
# ---------------------------------------------------------------------------

def compute_refinement_state(
    brief: ProjectBrief | None,
    outline: ChapterOutline | None,
) -> RefinementState | None:
    """Compute the canonical refinement state from brief/outline confirmations."""
    brief_fully_confirmed = is_brief_fully_confirmed(brief) if brief else False
    outline_fully_confirmed = is_outline_fully_confirmed(outline) if outline else False

    if brief is None and outline is None:
        return None
    elif brief is not None and not brief_fully_confirmed:
        return RefinementState.BRIEF_REVIEWING
    elif brief is not None and brief_fully_confirmed:
        if outline is None or not outline.chapters:
            return RefinementState.BRIEF_CONFIRMED
        elif not outline_fully_confirmed:
            return RefinementState.CHAPTER_OUTLINE_REVIEWING
        else:
            return RefinementState.BLUEPRINT_READY
    else:
        # outline exists but no brief (edge case)
        return RefinementState.IDEA_COLLECTING


def compute_blueprint_freeze_status(
    meta: ProjectMeta | None,
    brief: ProjectBrief | None,
    outline: ChapterOutline | None,
) -> BlueprintFreezeStatus | None:
    """Compute the current freeze status without mutating disk."""
    if brief is None and outline is None:
        return meta.blueprint_freeze_status if meta else None
    if meta and meta.blueprint_freeze_status in {
        BlueprintFreezeStatus.FROZEN,
        BlueprintFreezeStatus.STALE,
    }:
        return meta.blueprint_freeze_status
    return BlueprintFreezeStatus.NOT_FROZEN


def freeze_status_after_upstream_change(
    current_status: BlueprintFreezeStatus | None,
) -> BlueprintFreezeStatus:
    if current_status in {BlueprintFreezeStatus.FROZEN, BlueprintFreezeStatus.STALE}:
        return BlueprintFreezeStatus.STALE
    return BlueprintFreezeStatus.NOT_FROZEN


# ---------------------------------------------------------------------------
# Metadata persistence helper
# ---------------------------------------------------------------------------

def persist_refinement_metadata(
    pm: "ProjectManager",  # noqa: F821 — avoids circular import
    project_name: str,
    target_state: RefinementState | None,
    target_freeze_status: BlueprintFreezeStatus | None,
) -> None:
    """Persist refinement and freeze status to meta/project.json if changed."""
    from pathlib import Path

    meta = pm.read_project_meta(project_name)
    current_state = meta.refinement_state if meta else None
    current_freeze_status = meta.blueprint_freeze_status if meta else None
    if target_state == current_state and target_freeze_status == current_freeze_status:
        return
    if meta is None:
        meta = ProjectMeta(
            name=project_name,
            path=Path("."),
            status=ProjectStatus.DRAFT,
            pipeline_stage=PipelineStage.IDLE,
        )
    meta = meta.model_copy(
        update={
            "refinement_state": target_state,
            "blueprint_freeze_status": target_freeze_status,
        }
    )
    pm.write_project_meta(project_name, meta)


# ---------------------------------------------------------------------------
# Card / slot accessors
# ---------------------------------------------------------------------------

def brief_card_text(brief: ProjectBrief, key: str) -> str:
    card = brief.cards.get(key)
    if card is None or not isinstance(card.content, str):
        return ""
    return card.content


def intake_slot_content(
    intake: RefinementIntake,
    key: str,
    default: str | dict,
) -> str | dict:
    slot = intake.slots.get(key)
    if slot is None or slot.value is None:
        return default
    return slot.value


# ---------------------------------------------------------------------------
# Materialization: intake → brief / outline / blueprint
# ---------------------------------------------------------------------------

def build_chapter_intake_entries_from_blueprint(
    blueprint: ProjectBlueprint,
) -> list[ChapterIntakeEntry]:
    """Derive chapter intake entries from a blueprint draft."""
    total_chapters = len(blueprint.chapters)
    entries: list[ChapterIntakeEntry] = []
    for chapter in blueprint.chapters:
        fields = derive_chapter_outline_fields(chapter, total_chapters=total_chapters)
        entries.append(
            ChapterIntakeEntry(
                chapter_id=chapter.id,
                order=chapter.order,
                chapter_name=chapter.name,
                **fields,
            )
        )
    return entries


def materialize_brief_from_intake(intake: RefinementIntake) -> ProjectBrief:
    cards = {
        "core_premise": BriefCard(content=intake_slot_content(intake, "core_premise", "")),
        "audience_genre": BriefCard(content=intake_slot_content(intake, "audience_genre", "")),
        "tone_themes": BriefCard(content=intake_slot_content(intake, "tone_themes", "")),
        "visual_style": BriefCard(content=intake_slot_content(intake, "visual_style", "")),
        "world_rules": BriefCard(content=intake_slot_content(intake, "world_rules", "")),
        "core_cast": BriefCard(content=intake_slot_content(intake, "core_cast", "")),
        "character_identity": BriefCard(
            content=intake_slot_content(intake, "character_identity", {"characters": []})
        ),
        "relationship_baselines": BriefCard(
            content=intake_slot_content(intake, "relationship_baselines", {"relationships": []})
        ),
        "constraints": BriefCard(content=intake_slot_content(intake, "constraints", "")),
    }
    return ProjectBrief(cards=cards, updated_at=datetime.utcnow().isoformat())


def materialize_outline_from_intake(intake: RefinementIntake) -> ChapterOutline:
    chapters = [
        ChapterOutlineEntry(
            chapter_id=entry.chapter_id,
            order=entry.order,
            chapter_name=entry.chapter_name,
            chapter_goal=entry.chapter_goal,
            key_conflict=entry.key_conflict,
            emotional_arc=entry.emotional_arc,
            reveals=entry.reveals,
            end_state=entry.end_state,
            mood_or_pacing_bias=entry.mood_or_pacing_bias,
            character_focus=entry.character_focus,
            relationship_shift=entry.relationship_shift,
            character_presentation_notes=entry.character_presentation_notes,
            confirmed=False,
        )
        for entry in intake.chapter_draft
    ]
    return ChapterOutline(chapters=chapters, updated_at=datetime.utcnow().isoformat())


def assemble_frozen_blueprint(
    project_name: str,
    brief: ProjectBrief,
    outline: ChapterOutline,
) -> ProjectBlueprint:
    """Assemble the authoritative frozen blueprint from confirmed upstream data."""
    if not is_brief_fully_confirmed(brief) or not is_outline_fully_confirmed(outline):
        raise ValueError("Cannot freeze blueprint before brief and outline are fully confirmed")

    char_card = brief.cards.get("character_identity")
    char_entries = []
    if char_card and isinstance(char_card.content, dict):
        char_entries = char_card.content.get("characters", [])

    characters = [
        BlueprintCharacter(
            name=entry.get("name", ""),
            role=entry.get("story_role", ""),
            personality=", ".join(entry.get("personality_anchors", [])),
            appearance=", ".join(entry.get("visual_identity_anchors", [])),
            variants=None,
        )
        for entry in char_entries
    ]

    chapters = [
        ChapterSummary(
            id=ch.chapter_id,
            name=ch.chapter_name,
            order=ch.order,
            scenes=[],
        )
        for ch in sorted(outline.chapters, key=lambda c: c.order)
    ]

    tone_themes = brief_card_text(brief, "tone_themes")
    themes = [part.strip() for part in re.split(r"[,\n]", tone_themes) if part.strip()]

    return ProjectBlueprint(
        title=project_name,
        genre=brief_card_text(brief, "audience_genre") or "Unknown",
        worldview=brief_card_text(brief, "world_rules") or "Unknown",
        themes=themes,
        target_audience=brief_card_text(brief, "audience_genre"),
        estimated_play_time="",
        art_style=brief_card_text(brief, "visual_style"),
        audio_style="",
        characters=characters,
        chapters=chapters,
    )
