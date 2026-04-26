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
