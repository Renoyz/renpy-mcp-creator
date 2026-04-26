"""Tests for shared chapter outline field derivation."""

import pytest

from renpy_mcp.blueprint.outline_derivation import derive_chapter_outline_fields
from renpy_mcp.blueprint.models import ChapterSummary, SceneSummary


def _make_chapter(name="Chapter 1", scenes=None, order=1):
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
    def test_early_chapter_fields(self):
        chapter = _make_chapter(
            "The Beginning",
            order=1,
            scenes=[
                _make_scene("First Contact", ["Alice", "Bob"]),
                _make_scene("Growing Tension", ["Alice", "Bob", "Charlie"]),
                _make_scene("The Confrontation", ["Alice", "Charlie"]),
            ],
        )

        fields = derive_chapter_outline_fields(chapter, total_chapters=5)

        assert fields["chapter_goal"] == "Introduce the world and characters through First Contact"
        assert "Initial friction emerges around The Confrontation" == fields["key_conflict"]
        assert fields["emotional_arc"] == "setup -> escalation"
        assert fields["reveals"] == "The Confrontation"
        assert fields["end_state"] == "The Confrontation"
        assert fields["mood_or_pacing_bias"] == "escalating"
        assert "Alice" in fields["character_focus"]
        assert "Bob" in fields["character_focus"]
        assert "Charlie" in fields["character_focus"]
        assert "relationship_shift" in fields
        assert "character_presentation_notes" in fields

    def test_mid_chapter_fields(self):
        chapter = _make_chapter(
            "The Middle",
            order=3,
            scenes=[
                _make_scene("Twist", ["Alice", "Bob"]),
                _make_scene("Betrayal", ["Alice", "Charlie"]),
            ],
        )

        fields = derive_chapter_outline_fields(chapter, total_chapters=5)

        assert fields["chapter_goal"] == "Escalate stakes and deepen conflicts through Twist"
        assert "Alliances shift and stakes intensify around Betrayal" == fields["key_conflict"]
        assert fields["emotional_arc"] == "escalation -> confrontation"

    def test_late_chapter_fields(self):
        chapter = _make_chapter(
            "The End",
            order=5,
            scenes=[
                _make_scene("Final Battle", ["Alice", "Bob", "Charlie"]),
                _make_scene("Aftermath", ["Alice"]),
            ],
        )

        fields = derive_chapter_outline_fields(chapter, total_chapters=5)

        assert fields["chapter_goal"] == "Bring the story to its climax and resolution through Final Battle"
        assert "Final confrontation comes to a head around Aftermath" == fields["key_conflict"]
        assert fields["emotional_arc"] == "climax -> resolution"

    def test_single_scene_chapter_uses_position_arc(self):
        chapter = _make_chapter(
            "Prologue",
            order=1,
            scenes=[_make_scene("Opening", ["Hero"])],
        )

        fields = derive_chapter_outline_fields(chapter, total_chapters=4)

        assert fields["emotional_arc"] == "setup -> escalation"
        assert fields["mood_or_pacing_bias"] == "measured"
        assert fields["character_focus"] == ["Hero"]

    def test_single_chapter_story_is_climax(self):
        """A one-chapter story should feel like a complete arc."""
        chapter = _make_chapter(
            "Solo Chapter",
            order=1,
            scenes=[_make_scene("The Only Scene", ["Hero"])],
        )

        fields = derive_chapter_outline_fields(chapter, total_chapters=1)

        assert fields["emotional_arc"] == "climax -> resolution"

    def test_two_chapter_story_first_is_setup_second_is_climax(self):
        first = _make_chapter(
            "Opening",
            order=1,
            scenes=[_make_scene("Arrival", ["Hero"])],
        )
        second = _make_chapter(
            "Finale",
            order=2,
            scenes=[_make_scene("Showdown", ["Hero", "Rival"])],
        )

        first_fields = derive_chapter_outline_fields(first, total_chapters=2)
        second_fields = derive_chapter_outline_fields(second, total_chapters=2)

        assert first_fields["emotional_arc"] == "setup -> escalation"
        assert second_fields["emotional_arc"] == "climax -> resolution"
        assert first_fields["chapter_goal"].startswith("Introduce the world and characters")
        assert second_fields["chapter_goal"].startswith("Bring the story to its climax and resolution")

    def test_two_characters_generates_relationship_shift(self):
        chapter = _make_chapter(
            "Partners",
            order=1,
            scenes=[_make_scene("Meeting", ["Kai", "Luna"])],
        )

        fields = derive_chapter_outline_fields(chapter, total_chapters=3)

        assert "Kai" in fields["relationship_shift"]
        assert "Luna" in fields["relationship_shift"]

    def test_no_scenes_falls_back_to_chapter_name(self):
        chapter = _make_chapter("Empty Chapter", order=1, scenes=[])

        fields = derive_chapter_outline_fields(chapter, total_chapters=4)

        assert "Introduce the world and characters through Empty Chapter" == fields["chapter_goal"]
        assert fields["emotional_arc"] == "setup -> escalation"

    def test_preserves_character_order_from_first_appearance(self):
        chapter = _make_chapter(
            "Cast Intro",
            order=1,
            scenes=[
                _make_scene("A", ["Zeta"]),
                _make_scene("B", ["Alpha"]),
                _make_scene("C", ["Zeta", "Alpha", "Beta"]),
            ],
        )

        fields = derive_chapter_outline_fields(chapter, total_chapters=4)

        assert fields["character_focus"] == ["Zeta", "Alpha", "Beta"]

    def test_does_not_apply_fallback_when_chapter_has_scenes_but_no_scene_characters(self):
        chapter = _make_chapter(
            "Empty Cast",
            order=1,
            scenes=[_make_scene("Quiet Room"), _make_scene("Lonely Hall")],
        )

        fields = derive_chapter_outline_fields(
            chapter,
            total_chapters=3,
            fallback_character_names=["Alice", "Bob", "Alice", "Chloe"],
        )

        assert fields["character_focus"] == []
        assert fields["relationship_shift"] == ""

    def test_falls_back_to_blueprint_characters_when_chapter_has_no_scenes(self):
        chapter = _make_chapter(
            "Empty Cast",
            order=1,
            scenes=[],
        )

        fields = derive_chapter_outline_fields(
            chapter,
            total_chapters=3,
            fallback_character_names=["Alice", "Bob", "Alice", "Chloe"],
        )

        assert fields["character_focus"] == ["Alice", "Bob", "Chloe"]
        assert "Alice and Bob" in fields["relationship_shift"]

    def test_prefers_scene_characters_over_blueprint_fallback(self):
        chapter = _make_chapter(
            "Scene Focused Cast",
            order=1,
            scenes=[_make_scene("Meeting", ["Lena"]), _make_scene("Departure", ["Lena", "Nate"])],
        )

        fields = derive_chapter_outline_fields(
            chapter,
            total_chapters=3,
            fallback_character_names=["Alice", "Bob"],
        )

        assert fields["character_focus"] == ["Lena", "Nate"]
        assert fields["relationship_shift"] == "Lena and Nate face new pressure together"
