"""TDD: draft recovery preserves old value on transient failure."""
import logging

import pytest


def test_draft_restore_keeps_old_draft_on_failure(caplog, monkeypatch, tmp_path):
    """When blueprint_session.json is unparseable, old self.draft is preserved."""
    from renpy_mcp.web.chat_ws import BlueprintOrchestrator

    # Monkeypatch _load_runtime_session to return a corrupt draft
    def _bad_session(project_name):
        return {"draft": {"title": None, "chapters": "not-a-list"}}

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._load_runtime_session", _bad_session
    )

    orch = BlueprintOrchestrator.__new__(BlueprintOrchestrator)
    orch.project_name = "test"
    orch.pm = None
    orch.phase = None
    orch.turn_count = 0
    orch.draft = {"title": "Old Draft", "chapters": []}
    orch.confirmation_id = None
    orch.intake_mode = False
    orch.messages = []

    with caplog.at_level(logging.WARNING):
        orch._try_restore_session()

    assert orch.draft == {"title": "Old Draft", "chapters": []}, (
        "Fixed: old draft preserved when session recovery fails"
    )
    assert any("keeping previous draft" in r.message for r in caplog.records)


def test_draft_restore_sets_none_when_no_old_draft(caplog, monkeypatch, tmp_path):
    """When there is no previous draft, None is correctly retained."""
    from renpy_mcp.web.chat_ws import BlueprintOrchestrator

    def _bad_session(project_name):
        return {"draft": {"title": None, "chapters": "not-a-list"}}

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._load_runtime_session", _bad_session
    )

    orch = BlueprintOrchestrator.__new__(BlueprintOrchestrator)
    orch.project_name = "test"
    orch.pm = None
    orch.phase = None
    orch.turn_count = 0
    orch.draft = None
    orch.confirmation_id = None
    orch.intake_mode = False
    orch.messages = []

    with caplog.at_level(logging.WARNING):
        orch._try_restore_session()

    assert orch.draft is None


def test_build_chapter_intake_entry_uses_draft_characters_as_fallback_for_empty_chapter():
    """Character fallback should use draft-level names when chapter has no scenes."""
    from renpy_mcp.blueprint.models import BlueprintCharacter, ChapterSummary, ProjectBlueprint
    from renpy_mcp.web.chat_ws import BlueprintOrchestrator

    orchestrator = BlueprintOrchestrator.__new__(BlueprintOrchestrator)
    orchestrator.draft = ProjectBlueprint(
        title="Fallback Draft",
        genre="Drama",
        worldview="Small town",
        chapters=[],
        characters=[
            BlueprintCharacter(name="Alice", role="protagonist", personality="", appearance=""),
            BlueprintCharacter(name="Bob", role="support", personality="", appearance=""),
        ],
    )

    chapter = ChapterSummary(
        id="ch1",
        name="Calm Beginning",
        order=1,
        scenes=[],
    )

    entry = orchestrator._build_chapter_intake_entry(chapter)

    assert entry.character_focus == ["Alice", "Bob"]
    assert entry.relationship_shift == "Alice and Bob face new pressure together"
