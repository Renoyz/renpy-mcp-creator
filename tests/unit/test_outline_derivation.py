"""Tests for shared chapter outline field derivation."""

import pytest

from renpy_mcp.blueprint.outline_derivation import derive_chapter_outline_fields
from renpy_mcp.blueprint.models import ChapterSummary, SceneSummary


def _make_chapter(name="Chapter 1", scenes=None, order=0):
    return ChapterSummary(
        id=f"ch_{order}",
        order=order,
        name=name,
        scenes=scenes or [],
    )


def _make_scene(name="Scene 1", characters=None):
    return SceneSummary(
        id=f"sc_{name}",
        name=name,
        order=0,
        characters=characters or [],
    )


class TestDeriveChapterOutlineFields:
    def test_derives_fields_from_chapter_with_scenes(self):
        chapter = _make_chapter(
            "The Beginning",
            scenes=[
                _make_scene("First Contact", ["Alice", "Bob"]),
                _make_scene("Growing Tension", ["Alice", "Bob", "Charlie"]),
                _make_scene("The Confrontation", ["Alice", "Charlie"]),
            ],
        )

        fields = derive_chapter_outline_fields(chapter, total_chapters=5)

        assert fields["chapter_goal"] == "Advance The Beginning through First Contact"
        assert "Confrontation" in fields["key_conflict"]
        assert "setup -> escalation" in fields["emotional_arc"]
        assert fields["reveals"] == "The Confrontation"
        assert fields["end_state"] == "The Confrontation"
        assert fields["mood_or_pacing_bias"] == "escalating"
        assert "Alice" in fields["character_focus"]
        assert "Bob" in fields["character_focus"]
        assert "Charlie" in fields["character_focus"]
        assert "relationship_shift" in fields
        assert "character_presentation_notes" in fields

    def test_single_scene_chapter_uses_different_arc(self):
        chapter = _make_chapter(
            "Prologue",
            scenes=[_make_scene("Opening", ["Hero"])],
        )

        fields = derive_chapter_outline_fields(chapter, total_chapters=3)

        assert fields["emotional_arc"] == "setup -> turn"
        assert fields["mood_or_pacing_bias"] == "measured"
        assert fields["character_focus"] == ["Hero"]

    def test_two_characters_generates_relationship_shift(self):
        chapter = _make_chapter(
            "Partners",
            scenes=[_make_scene("Meeting", ["Kai", "Luna"])],
        )

        fields = derive_chapter_outline_fields(chapter, total_chapters=3)

        assert "Kai" in fields["relationship_shift"]
        assert "Luna" in fields["relationship_shift"]

    def test_no_scenes_falls_back_to_chapter_name(self):
        chapter = _make_chapter("Empty Chapter", scenes=[])

        fields = derive_chapter_outline_fields(chapter, total_chapters=2)

        assert "Advance Empty Chapter" in fields["chapter_goal"]
        assert fields["emotional_arc"] == "setup -> turn"

    def test_preserves_character_order_from_first_appearance(self):
        chapter = _make_chapter(
            "Cast Intro",
            scenes=[
                _make_scene("A", ["Zeta"]),
                _make_scene("B", ["Alpha"]),
                _make_scene("C", ["Zeta", "Alpha", "Beta"]),
            ],
        )

        fields = derive_chapter_outline_fields(chapter, total_chapters=4)

        assert fields["character_focus"] == ["Zeta", "Alpha", "Beta"]
