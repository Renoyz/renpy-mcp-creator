"""Pure domain logic for requirements refinement.

Extracted from the God Function ``create_app()`` in ``web/fastapi_app.py``
(P2-2) and the God Class ``BlueprintOrchestrator`` in ``web/chat_ws.py``
(P2-3) so that these functions can be:

* unit-tested without HTTP or WebSocket
* reused across multiple routers and services
* reasoned about independently of transport
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..blueprint.models import (
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
from ..blueprint.outline_derivation import derive_chapter_outline_fields


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INTAKE_SLOT_KEYS: list[str] = [
    "core_premise",
    "audience_genre",
    "tone_themes",
    "visual_style",
    "world_rules",
    "core_cast",
    "character_identity",
    "relationship_baselines",
    "constraints",
]


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
            entry.get("story_role", "").strip()
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
    fallback_characters = [ch.name for ch in blueprint.characters if ch.name]
    entries: list[ChapterIntakeEntry] = []
    for chapter in blueprint.chapters:
        fields = derive_chapter_outline_fields(
            chapter,
            total_chapters=total_chapters,
            fallback_character_names=fallback_characters,
        )
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


# ---------------------------------------------------------------------------
# Intake computation (extracted from BlueprintOrchestrator._write_refinement_intake)
# ---------------------------------------------------------------------------

def compute_refinement_intake(
    orchestrator_phase: PipelineStage,
    draft: ProjectBlueprint | None,
    brief_confirmed: bool,
    latest_user_content: str | None = None,
) -> RefinementIntake:
    """Compute a ``RefinementIntake`` purely from state — no I/O.

    This is the domain logic formerly embedded inside
    ``BlueprintOrchestrator._write_refinement_intake``.
    """
    slots: dict[str, IntakeSlot] = {}
    chapter_draft: list[ChapterIntakeEntry] = []

    if orchestrator_phase == PipelineStage.REVIEWING and draft is not None:
        if brief_confirmed:
            # Chapter-level outline draft ready
            chapter_draft = build_chapter_intake_entries_from_blueprint(draft)
            current_summary = f"Chapter outline draft ready with {len(chapter_draft)} chapters"
            phase = IntakePhase.OUTLINE_READY
            brief_draft_ready = True
            outline_draft_ready = True
        else:
            # Project-level brief draft ready
            characters = [
                {
                    "character_id": re.sub(r"[^a-z0-9]+", "_", ch.name.lower()).strip("_") or f"char_{idx + 1}",
                    "name": ch.name,
                    "story_role": ch.role,
                    "core_motivation": "",
                    "personality_anchors": [ch.personality] if ch.personality else [],
                    "visual_identity_anchors": [ch.appearance] if ch.appearance else [],
                    "forbidden_drift": [],
                }
                for idx, ch in enumerate(draft.characters)
            ]
            slots = {
                "core_premise": IntakeSlot(
                    value=f"{draft.genre} story in {draft.worldview}".strip(),
                    complete=bool(draft.genre or draft.worldview),
                ),
                "audience_genre": IntakeSlot(value=draft.genre, complete=bool(draft.genre)),
                "tone_themes": IntakeSlot(value=", ".join(draft.themes), complete=bool(draft.themes)),
                "visual_style": IntakeSlot(value=draft.art_style, complete=bool(draft.art_style)),
                "world_rules": IntakeSlot(value=draft.worldview, complete=bool(draft.worldview)),
                "core_cast": IntakeSlot(
                    value=", ".join(ch.name for ch in draft.characters),
                    complete=bool(draft.characters),
                ),
                "character_identity": IntakeSlot(
                    value={"characters": characters},
                    complete=bool(characters),
                ),
                "relationship_baselines": IntakeSlot(value={"relationships": []}, complete=False),
                "constraints": IntakeSlot(value="", complete=False),
            }
            current_summary = f"{draft.genre} in {draft.worldview}".strip()
            phase = IntakePhase.BRIEF_READY
            brief_draft_ready = True
            outline_draft_ready = False
    else:
        latest = (latest_user_content or "").strip()
        if brief_confirmed:
            # Chapter-level collecting
            current_summary = latest
            phase = IntakePhase.CHAPTER
            brief_draft_ready = True
            outline_draft_ready = False
        else:
            # Project-level collecting
            slots = {key: IntakeSlot() for key in INTAKE_SLOT_KEYS}
            if latest:
                slots["core_premise"] = IntakeSlot(value=latest, complete=True)
            current_summary = latest
            phase = IntakePhase.PROJECT
            brief_draft_ready = False
            outline_draft_ready = False

    missing_slots = [key for key, slot in slots.items() if not slot.complete] if slots else []

    return RefinementIntake(
        phase=phase,
        current_summary=current_summary,
        missing_slots=missing_slots,
        slots=slots,
        brief_draft_ready=brief_draft_ready,
        outline_draft_ready=outline_draft_ready,
        chapter_draft=chapter_draft,
        updated_at=datetime.utcnow().isoformat(),
    )


# ---------------------------------------------------------------------------
# Interview response selection (extracted from BlueprintOrchestrator.handle_user_message)
# ---------------------------------------------------------------------------


@dataclass
class PostDraftResult:
    """Result of building post-draft-generation response messages.

    Used by the orchestrator to apply side-effects (persist to history,
    save session) and return WebSocket events to the caller.
    """

    next_phase: PipelineStage
    confirmation_id: str | None = None
    history_entries: list[dict[str, Any]] = field(default_factory=list)
    ws_events: list[dict[str, Any]] = field(default_factory=list)


def select_collecting_response(
    turn_count: int,
    intake_mode: bool,
    lang: str,
) -> tuple[str, str]:
    """Select the canned interview response for the collecting phase.

    Returns ``(content, message_kind)``.  The caller is responsible for
    appending the message to history and returning the appropriate
    WebSocket event payload.

    *turn_count* is 0 for the start trigger and 1 for the first
    follow-up (already incremented by the caller).
    """
    from ..utils.i18n import _localized_text  # lazy — avoid import cycle

    if turn_count == 0:
        if intake_mode:
            return (
                _localized_text(
                    lang,
                    "我会根据你的回答动态补齐 Project Brief。先说说你已有的故事想法即可；不用一次回答完整。",
                    "I'll help fill in the Project Brief dynamically from your answers. Share any story idea you already have; you do not need to answer everything at once.",
                ),
                "intake_text",
            )
        return (
            _localized_text(
                lang,
                "太好了！让我来帮你把这个想法变成完整的蓝图。首先，你希望这个故事大概有几章？有没有特别想设定的主角人设或故事基调？",
                "Great. I'll help turn this idea into a complete blueprint. To start, roughly how many chapters do you want, and are there any specific protagonist traits or story tone you want to establish?",
            ),
            "text",
        )

    # turn_count == 1 — first follow-up
    if intake_mode:
        return (
            _localized_text(
                lang,
                "收到。为了让 Project Brief 更完整，请再补充：\n1. 主角的核心动机\n2. 主要人物的视觉特征\n3. 角色之间的关系基线\n4. 不希望角色发生哪些形象偏移",
                "Got it. To make the Project Brief more complete, please add:\n1. The protagonist's core motivation\n2. Key visual traits for the main characters\n3. Relationship baselines between characters\n4. Any character drift you want to forbid",
            ),
            "intake_text",
        )
    return (
        _localized_text(
            lang,
            "收到。为了生成更准确的蓝图，请补充一下：\n1. 世界观或时代背景\n2. 核心角色（1-3位）\n3. 你希望的游戏时长",
            "Got it. To generate a more accurate blueprint, please add:\n1. The setting or historical era\n2. The core cast (1-3 characters)\n3. The playtime you want for the game",
        ),
        "text",
    )


def build_post_draft_result(
    draft: ProjectBlueprint,
    intake_mode: bool,
    brief_confirmed: bool,
    lang: str,
    phase_value: str,
    intake_dump: dict[str, Any] | None,
) -> PostDraftResult:
    """Construct response messages + WebSocket events after a successful draft generation.

    Returns a :class:`PostDraftResult` that the orchestrator applies:
    set ``next_phase`` and ``confirmation_id``, append ``history_entries``
    to ``self.messages``, and return ``ws_events`` to the caller.
    """
    from ..utils.i18n import _localized_text  # lazy — avoid import cycle

    draft_dict = draft.model_dump(mode="json")

    if intake_mode:
        if brief_confirmed:
            content = _localized_text(
                lang,
                "章节大纲草稿已经整理好。请在 Intake 面板点击 Enter Outline Review，进入章节大纲确认。",
                "Chapter outline draft is ready. Open the Intake panel and click Enter Outline Review.",
            )
            ready_kind = "outline_draft_ready"
        else:
            content = _localized_text(
                lang,
                "项目简报草稿已经整理好。请在 Intake 面板点击 Enter Brief Review，进入结构化确认。",
                "Project Brief draft is ready. Open the Intake panel and click Enter Brief Review.",
            )
            ready_kind = "brief_draft_ready"

        return PostDraftResult(
            next_phase=PipelineStage.IDLE,
            confirmation_id=None,
            history_entries=[
                {"role": "assistant", "content": content},
                {"role": "assistant", "message_kind": ready_kind, "content": content},
            ],
            ws_events=[
                {
                    "type": "message",
                    "role": "assistant",
                    "message_kind": "text",
                    "content": content,
                    "pipeline_stage": PipelineStage.IDLE.value,
                    "intake": intake_dump,
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "message_kind": ready_kind,
                    "content": content,
                    "pipeline_stage": PipelineStage.IDLE.value,
                    "intake": intake_dump,
                },
            ],
        )

    # Blueprint (non-intake) mode
    confirmation_id = f"conf_{uuid.uuid4().hex[:8]}"
    draft_notice = _localized_text(
        lang,
        "蓝图草案已生成，请查看并确认。",
        "The blueprint draft is ready. Please review and confirm it.",
    )
    confirm_notice = _localized_text(
        lang,
        "请确认以下蓝图草案，确认后我们将开始正式生成。",
        "Please confirm the blueprint draft below. Once confirmed, we'll begin full generation.",
    )
    assistant_content = _localized_text(
        lang,
        "信息已经足够丰富了。我现在为你整理一份蓝图草案，你可以在右侧查看。",
        "We have enough information now. I'm organizing a blueprint draft for you, and you can review it on the right.",
    )

    return PostDraftResult(
        next_phase=PipelineStage.REVIEWING,
        confirmation_id=confirmation_id,
        history_entries=[
            {"role": "assistant", "content": assistant_content},
            {
                "role": "assistant",
                "message_kind": "blueprint_draft",
                "content": draft_notice,
                "draft": draft_dict,
            },
            {
                "role": "assistant",
                "message_kind": "confirmation_request",
                "content": confirm_notice,
                "draft": draft_dict,
                "confirmation_id": confirmation_id,
            },
        ],
        ws_events=[
            {
                "type": "message",
                "role": "assistant",
                "message_kind": "text",
                "content": assistant_content,
                "pipeline_stage": PipelineStage.REVIEWING.value,
            },
            {
                "type": "message",
                "role": "assistant",
                "message_kind": "blueprint_draft",
                "content": draft_notice,
                "draft": draft_dict,
                "pipeline_stage": PipelineStage.REVIEWING.value,
            },
            {
                "type": "confirmation_request",
                "confirmation_id": confirmation_id,
                "message": confirm_notice,
                "draft": draft_dict,
                "pipeline_stage": PipelineStage.REVIEWING.value,
            },
        ],
    )


# ---------------------------------------------------------------------------
# Confirmation response helpers (P2-3 Step 3)
# ---------------------------------------------------------------------------


def select_confirmation_result_message(
    lang: str,
    prototype_error: str | None,
    build_error: str | None,
) -> str:
    """Return the localized result message after confirmation + pipeline."""
    from ..utils.i18n import _localized_text  # lazy — avoid import cycle

    if prototype_error:
        return _localized_text(
            lang,
            f"蓝图已保存，但原型生成失败：{prototype_error}",
            f"Blueprint saved, but prototype generation failed: {prototype_error}",
        )
    if build_error:
        return _localized_text(
            lang,
            f"蓝图已保存，原型已生成，但构建失败：{build_error}",
            f"Blueprint saved, prototype generated, but build failed: {build_error}",
        )
    return _localized_text(
        lang,
        "蓝图生成完成！原型已构建完毕，可以预览了。",
        "Blueprint generation is complete. The prototype is built and ready for preview.",
    )


def select_confirmation_rejection_message(lang: str) -> str:
    """Return the localized message when the user rejects a blueprint draft."""
    from ..utils.i18n import _localized_text  # lazy — avoid import cycle

    return _localized_text(
        lang,
        "好的，我们继续调整蓝图。你希望优先修改角色、章节还是整体基调？",
        "Understood. Let's keep refining the blueprint. Would you like to adjust the characters, the chapter structure, or the overall tone first?",
    )


def update_project_meta_after_confirmation(
    pm: "ProjectManager",  # noqa: F821
    project_name: str,
    draft: ProjectBlueprint | None,
) -> None:
    """Transition project meta to BLUEPRINTED/EDITING after confirmation."""
    meta = pm.read_project_meta(project_name)
    if meta is None:
        return
    meta.pipeline_stage = PipelineStage.EDITING
    meta.status = ProjectStatus.BLUEPRINTED
    if draft:
        meta.chapter_count = len(draft.chapters)
        meta.scene_count = sum(len(ch.scenes) for ch in draft.chapters)
    pm.write_project_meta(project_name, meta)


def build_first_progress_entry(lang: str) -> dict[str, Any]:
    """Return the first progress message dict for the pipeline start."""
    from ..utils.i18n import _localized_text  # lazy — avoid import cycle

    step_text = _localized_text(
        lang,
        "正在准备生成原型...",
        "Preparing prototype generation...",
    )
    return {
        "role": "assistant",
        "message_kind": "progress",
        "content": step_text,
        "step": step_text,
        "percent": 1,
    }
