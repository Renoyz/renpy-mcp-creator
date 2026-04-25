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

    chapter_goal = (
        f"Advance {chapter.name} through {first_scene_name}"
        if first_scene_name
        else f"Advance {chapter.name}"
    )
    key_conflict = (
        f"Pressure escalates around {last_scene_name}"
        if last_scene_name
        else f"Core conflict in {chapter.name}"
    )
    emotional_arc = (
        "setup -> escalation" if len(scene_names) > 1 else "setup -> turn"
    )
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
