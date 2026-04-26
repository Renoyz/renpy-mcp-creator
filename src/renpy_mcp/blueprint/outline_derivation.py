"""Shared chapter outline field derivation.

Derives narrative fields (chapter_goal, emotional_arc, etc.) from a
blueprint chapter so that scene generation receives meaningful direction.
Both chat_ws and fastapi_app use this to build ChapterIntakeEntry objects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from renpy_mcp.blueprint.models import ChapterSummary


def derive_chapter_outline_fields(
    chapter: ChapterSummary,
    total_chapters: int = 1,
) -> dict:
    """Derive the narrative intake fields for a single chapter.

    Returns a dict with keys: chapter_goal, key_conflict, emotional_arc,
    reveals, end_state, mood_or_pacing_bias, character_focus,
    relationship_shift, character_presentation_notes.
    """
    scene_names = [scene.name for scene in chapter.scenes if scene.name]
    first_scene_name = scene_names[0] if scene_names else chapter.name
    last_scene_name = scene_names[-1] if scene_names else chapter.name

    character_focus: list[str] = []
    for scene in chapter.scenes:
        for character in scene.characters:
            if character and character not in character_focus:
                character_focus.append(character)

    if total_chapters <= 1:
        pos = 1.0
    else:
        pos = (chapter.order - 1) / max(total_chapters - 1, 1)

    if pos <= 0.33:
        emotional_arc = "setup -> escalation"
    elif pos <= 0.66:
        emotional_arc = "escalation -> confrontation"
    else:
        emotional_arc = "climax -> resolution"

    if pos <= 0.33:
        chapter_goal = f"Introduce the world and characters through {first_scene_name}"
    elif pos <= 0.66:
        chapter_goal = f"Escalate stakes and deepen conflicts through {first_scene_name}"
    else:
        chapter_goal = f"Bring the story to its climax and resolution through {first_scene_name}"

    if pos <= 0.33:
        key_conflict = f"Initial friction emerges around {last_scene_name}"
    elif pos <= 0.66:
        key_conflict = f"Alliances shift and stakes intensify around {last_scene_name}"
    else:
        key_conflict = f"Final confrontation comes to a head around {last_scene_name}"
    reveals = last_scene_name or chapter.name
    end_state = last_scene_name or chapter.name
    mood_or_pacing_bias = "measured" if len(scene_names) <= 2 else "escalating"

    relationship_shift = ""
    if len(character_focus) >= 2:
        relationship_shift = (
            f"{character_focus[0]} and {character_focus[1]} "
            f"face new pressure together"
        )

    character_presentation_notes = (
        f"Keep visual focus on {', '.join(character_focus)}"
        if character_focus
        else f"Carry forward the chapter identity of {chapter.name}"
    )

    return {
        "chapter_goal": chapter_goal,
        "key_conflict": key_conflict,
        "emotional_arc": emotional_arc,
        "reveals": reveals,
        "end_state": end_state,
        "mood_or_pacing_bias": mood_or_pacing_bias,
        "character_focus": character_focus,
        "relationship_shift": relationship_shift,
        "character_presentation_notes": character_presentation_notes,
    }
