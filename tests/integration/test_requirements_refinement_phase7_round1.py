"""Phase 7 Round 1: Structured requirements refinement, state machine, and generation gates."""

import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from renpy_mcp.blueprint.models import RefinementIntake

from renpy_mcp.web.fastapi_app import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from renpy_mcp.config import RenPyConfig, get_settings
    from renpy_mcp.web.fastapi_app import set_config

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)
    set_config(RenPyConfig(sdk_path=Path(".")))
    app = create_app()
    return TestClient(app)


def _create_project(client: TestClient, tmp_path: Path, name: str) -> None:
    game_dir = tmp_path / name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text(
        'label start:\n    "Hello from the Ren\'Py MCP server!"\n    return\n',
        encoding="utf-8",
    )
    r = client.post("/api/projects", json={"name": name})
    assert r.status_code == 200


def _make_valid_brief() -> dict:
    """Return a fully-populated project brief dict."""
    return {
        "cards": {
            "core_premise": {"content": "A story about discovery.", "confirmed": False},
            "audience_genre": {"content": "Sci-fi, teens.", "confirmed": False},
            "tone_themes": {"content": "Hopeful, exploration.", "confirmed": False},
            "visual_style": {"content": "Cel-shaded, neon.", "confirmed": False},
            "world_rules": {"content": "Faster-than-light travel exists.", "confirmed": False},
            "core_cast": {"content": "Elena, Marcus, AI companion.", "confirmed": False},
            "character_identity": {
                "content": {
                    "characters": [
                        {
                            "character_id": "elena",
                            "name": "Elena",
                            "story_role": "Protagonist",
                            "core_motivation": "Find her lost brother",
                            "personality_anchors": ["curious", "stubborn"],
                            "visual_identity_anchors": ["blue hair", "lab coat"],
                            "forbidden_drift": ["do not make her cruel"],
                        }
                    ]
                },
                "confirmed": False,
            },
            "relationship_baselines": {
                "content": {
                    "relationships": [
                        {
                            "pair": ["elena", "marcus"],
                            "baseline": "Sibling rivalry with deep care",
                            "must_preserve": ["mutual respect"],
                        }
                    ]
                },
                "confirmed": False,
            },
            "constraints": {"content": "No time travel.", "confirmed": False},
        },
        "updated_at": "2026-04-22T00:00:00Z",
    }


def _make_valid_outline() -> dict:
    """Return a chapter outline dict with two chapters."""
    return {
        "chapters": [
            {
                "chapter_id": "ch1",
                "order": 1,
                "chapter_name": "Departure",
                "chapter_goal": "Establish Elena's motivation",
                "key_conflict": "Elena vs authority",
                "emotional_arc": "hope -> tension",
                "reveals": "Brother is missing",
                "end_state": "Elena leaves home",
                "mood_or_pacing_bias": "slow, contemplative",
                "character_focus": ["elena"],
                "relationship_shift": "Elena distances from parents",
                "character_presentation_notes": "Elena in civilian clothes",
                "confirmed": False,
            },
            {
                "chapter_id": "ch2",
                "order": 2,
                "chapter_name": "The Jump",
                "chapter_goal": "First FTL journey",
                "key_conflict": "Engine malfunction",
                "emotional_arc": "fear -> exhilaration",
                "reveals": "Marcus may still be alive",
                "end_state": "Arrival at Outpost 7",
                "mood_or_pacing_bias": "fast, tense",
                "character_focus": ["elena", "marcus"],
                "relationship_shift": "Marcus reappears as ally",
                "character_presentation_notes": "Elena in flight suit",
                "confirmed": False,
            },
        ],
        "updated_at": "2026-04-22T00:00:00Z",
    }


def _make_valid_intake() -> dict:
    """Return a project-level refinement intake snapshot."""
    return {
        "phase": "project",
        "current_summary": "A YA sci-fi mystery about a missing brother and a regulated FTL society.",
        "missing_slots": ["relationship_baselines", "constraints"],
        "slots": {
            "core_premise": {
                "value": "A YA sci-fi mystery about a missing brother.",
                "complete": True,
            },
            "audience_genre": {
                "value": "YA sci-fi mystery",
                "complete": True,
            },
            "tone_themes": {
                "value": "Hope, grief, discovery",
                "complete": True,
            },
            "visual_style": {
                "value": "Cel-shaded anime with cool neon lighting",
                "complete": True,
            },
            "world_rules": {
                "value": "Interstellar travel exists but is tightly regulated",
                "complete": True,
            },
            "core_cast": {
                "value": "Elena, Marcus, station AI",
                "complete": True,
            },
            "character_identity": {
                "value": {
                    "characters": [
                        {
                            "character_id": "elena",
                            "name": "Elena",
                            "story_role": "Protagonist",
                            "core_motivation": "Find her brother",
                            "personality_anchors": ["curious", "stubborn"],
                            "visual_identity_anchors": ["blue hair", "lab coat"],
                            "forbidden_drift": ["do not make her cruel"],
                        }
                    ]
                },
                "complete": True,
            },
        },
        "brief_draft_ready": False,
        "updated_at": "2026-04-23T00:00:00Z",
    }


def _confirm_all_brief_cards(client: TestClient, project_name: str, brief: dict) -> None:
    for key in brief["cards"]:
        response = client.post(
            f"/api/projects/{project_name}/brief/confirm-card",
            json={"card_key": key},
        )
        assert response.status_code == 200, response.text


def _confirm_all_outline_chapters(client: TestClient, project_name: str, outline: dict) -> None:
    for ch in outline["chapters"]:
        response = client.post(
            f"/api/projects/{project_name}/chapter-outline/confirm-chapter",
            json={"chapter_id": ch["chapter_id"]},
        )
        assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# A. Project Brief persistence
# ---------------------------------------------------------------------------


class TestProjectBriefPersistence:
    def test_project_brief_roundtrip_uses_structured_model(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "brief_rt")
        payload = _make_valid_brief()

        r = client.put("/api/projects/brief_rt/brief", json=payload)
        assert r.status_code == 200, r.text

        r = client.get("/api/projects/brief_rt/brief")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["cards"]["core_premise"]["content"] == "A story about discovery."
        assert data["cards"]["core_premise"]["confirmed"] is False
        assert "character_identity" in data["cards"]
        chars = data["cards"]["character_identity"]["content"]["characters"]
        assert chars[0]["character_id"] == "elena"
        assert chars[0]["story_role"] == "Protagonist"

    def test_get_brief_returns_404_when_missing(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "brief_missing")
        r = client.get("/api/projects/brief_missing/brief")
        assert r.status_code == 404
        assert "brief" in r.json()["detail"].lower()

    def test_invalid_project_brief_file_raises_value_error(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "brief_bad")
        brief_path = tmp_path / "brief_bad" / "meta" / "project_brief.json"
        brief_path.write_text("not json", encoding="utf-8")
        r = client.get("/api/projects/brief_bad/brief")
        assert r.status_code == 500
        assert "invalid" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# B. Chapter Outline persistence
# ---------------------------------------------------------------------------


class TestChapterOutlinePersistence:
    def test_chapter_outline_roundtrip_uses_structured_model(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "outline_rt")
        payload = _make_valid_outline()

        r = client.put("/api/projects/outline_rt/chapter-outline", json=payload)
        assert r.status_code == 200, r.text

        r = client.get("/api/projects/outline_rt/chapter-outline")
        assert r.status_code == 200, r.text
        data = r.json()
        assert len(data["chapters"]) == 2
        assert data["chapters"][0]["chapter_name"] == "Departure"
        assert data["chapters"][0]["character_focus"] == ["elena"]

    def test_get_chapter_outline_returns_404_when_missing(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "outline_missing")
        r = client.get("/api/projects/outline_missing/chapter-outline")
        assert r.status_code == 404
        assert "outline" in r.json()["detail"].lower()

    def test_invalid_chapter_outline_file_raises_value_error(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "outline_bad")
        outline_path = tmp_path / "outline_bad" / "meta" / "chapter_outline.json"
        outline_path.write_text("not json", encoding="utf-8")
        r = client.get("/api/projects/outline_bad/chapter-outline")
        assert r.status_code == 500
        assert "invalid" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# B2. Refinement intake persistence
# ---------------------------------------------------------------------------


class TestRefinementIntakePersistence:
    def test_refinement_intake_roundtrip_uses_structured_model(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.config import get_settings
        from renpy_mcp.services.project_manager import ProjectManager

        _create_project(client, tmp_path, "intake_rt")
        settings = get_settings()
        monkeypatch.setattr(settings, "workspace", tmp_path)
        pm = ProjectManager(settings)

        payload = _make_valid_intake()
        pm.write_refinement_intake("intake_rt", RefinementIntake.model_validate(payload))

        intake = pm.read_refinement_intake("intake_rt")
        assert intake is not None
        assert intake.phase == "project"
        assert intake.current_summary.startswith("A YA sci-fi mystery")
        assert intake.slots["core_premise"].complete is True
        assert intake.slots["core_premise"].value == "A YA sci-fi mystery about a missing brother."

    def test_get_refinement_intake_returns_404_when_missing(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "intake_missing")
        r = client.get("/api/projects/intake_missing/refinement-intake")
        assert r.status_code == 404
        assert "intake" in r.json()["detail"].lower()

    def test_invalid_refinement_intake_file_raises_value_error(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.config import get_settings
        from renpy_mcp.services.project_manager import ProjectManager

        _create_project(client, tmp_path, "intake_bad")
        settings = get_settings()
        monkeypatch.setattr(settings, "workspace", tmp_path)
        pm = ProjectManager(settings)

        intake_path = tmp_path / "intake_bad" / "meta" / "refinement_intake.json"
        intake_path.write_text("not json", encoding="utf-8")

        with pytest.raises(ValueError):
            pm.read_refinement_intake("intake_bad")


# ---------------------------------------------------------------------------
# B3. Refinement intake API and brief promotion
# ---------------------------------------------------------------------------


def _make_chapter_intake(project_name: str = "test") -> dict:
    """Return a chapter-level refinement intake snapshot."""
    return {
        "phase": "chapter",
        "current_summary": "Brief confirmed. Collecting chapter details.",
        "missing_slots": [],
        "slots": {},
        "brief_draft_ready": True,
        "chapter_draft": [
            {
                "chapter_id": "ch1",
                "order": 1,
                "chapter_name": "Departure",
                "chapter_goal": "Establish Elena's motivation",
                "key_conflict": "Elena vs authority",
                "emotional_arc": "hope -> tension",
                "reveals": "Brother is missing",
                "end_state": "Elena leaves home",
                "mood_or_pacing_bias": "slow, contemplative",
                "character_focus": ["elena"],
                "relationship_shift": "Elena distances from parents",
                "character_presentation_notes": "Elena in civilian clothes",
            },
            {
                "chapter_id": "ch2",
                "order": 2,
                "chapter_name": "The Jump",
                "chapter_goal": "First FTL journey",
                "key_conflict": "Engine malfunction",
                "emotional_arc": "fear -> exhilaration",
                "reveals": "Marcus may still be alive",
                "end_state": "Arrival at Outpost 7",
                "mood_or_pacing_bias": "fast, tense",
                "character_focus": ["elena", "marcus"],
                "relationship_shift": "Marcus reappears as ally",
                "character_presentation_notes": "Elena in flight suit",
            },
        ],
        "outline_draft_ready": True,
        "updated_at": "2026-04-23T00:00:00Z",
    }


class TestRefinementIntakeApi:
    def test_refinement_intake_status_returns_structured_project_intake(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.config import get_settings
        from renpy_mcp.services.project_manager import ProjectManager

        _create_project(client, tmp_path, "intake_status")
        settings = get_settings()
        monkeypatch.setattr(settings, "workspace", tmp_path)
        pm = ProjectManager(settings)
        pm.write_refinement_intake("intake_status", RefinementIntake.model_validate(_make_valid_intake()))

        r = client.get("/api/projects/intake_status/refinement-intake")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["phase"] == "project"
        assert data["current_summary"].startswith("A YA sci-fi mystery")
        assert data["slots"]["core_premise"]["complete"] is True

    def test_promote_brief_draft_materializes_project_brief(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.config import get_settings
        from renpy_mcp.services.project_manager import ProjectManager

        _create_project(client, tmp_path, "promote_ok")
        settings = get_settings()
        monkeypatch.setattr(settings, "workspace", tmp_path)
        pm = ProjectManager(settings)
        payload = _make_valid_intake()
        payload["brief_draft_ready"] = True
        payload["phase"] = "brief_ready"
        pm.write_refinement_intake("promote_ok", RefinementIntake.model_validate(payload))

        r = client.post("/api/projects/promote_ok/brief/promote-draft")
        assert r.status_code == 200, r.text

        r = client.get("/api/projects/promote_ok/brief")
        assert r.status_code == 200, r.text
        brief = r.json()
        assert brief["cards"]["core_premise"]["content"] == payload["slots"]["core_premise"]["value"]
        assert brief["cards"]["audience_genre"]["content"] == payload["slots"]["audience_genre"]["value"]
        assert brief["cards"]["character_identity"]["content"]["characters"][0]["name"] == "Elena"
        assert brief["cards"]["core_premise"]["confirmed"] is False

        r = client.get("/api/projects/promote_ok/refinement-status")
        data = r.json()
        assert data["refinement_state"] == "brief_reviewing"
        assert data["intake_phase"] == "brief_ready"
        assert data["brief_draft_ready"] is True
        assert data["intake_required"] is False

    def test_promote_brief_draft_requires_brief_draft_ready(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.config import get_settings
        from renpy_mcp.services.project_manager import ProjectManager

        _create_project(client, tmp_path, "promote_blocked")
        settings = get_settings()
        monkeypatch.setattr(settings, "workspace", tmp_path)
        pm = ProjectManager(settings)
        pm.write_refinement_intake(
            "promote_blocked",
            RefinementIntake.model_validate(_make_valid_intake()),
        )

        r = client.post("/api/projects/promote_blocked/brief/promote-draft")
        assert r.status_code == 409, r.text
        assert "draft" in r.json()["detail"].lower()

    def test_refinement_status_for_new_project_exposes_intake_entry_state(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "intake_entry")

        r = client.get("/api/projects/intake_entry/refinement-status")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["refinement_state"] is None
        assert data["intake_phase"] is None
        assert data["brief_draft_ready"] is False
        assert data["intake_required"] is True
        assert data["generation_allowed"] is False

    # --- Chapter outline promote-draft ---

    def test_promote_outline_draft_materializes_chapter_outline(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.config import get_settings
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.blueprint.models import RefinementIntake

        _create_project(client, tmp_path, "ch_promote_ok")
        settings = get_settings()
        monkeypatch.setattr(settings, "workspace", tmp_path)
        pm = ProjectManager(settings)

        # Seed a fully confirmed brief
        brief = _make_valid_brief()
        client.put("/api/projects/ch_promote_ok/brief", json=brief)
        _confirm_all_brief_cards(client, "ch_promote_ok", brief)

        # Seed chapter intake with outline_draft_ready
        payload = _make_chapter_intake()
        pm.write_refinement_intake("ch_promote_ok", RefinementIntake.model_validate(payload))

        r = client.post("/api/projects/ch_promote_ok/chapter-outline/promote-draft")
        assert r.status_code == 200, r.text

        r = client.get("/api/projects/ch_promote_ok/chapter-outline")
        assert r.status_code == 200, r.text
        outline = r.json()
        assert len(outline["chapters"]) == 2
        assert outline["chapters"][0]["chapter_id"] == "ch1"
        assert outline["chapters"][0]["chapter_name"] == "Departure"
        assert outline["chapters"][0]["confirmed"] is False
        assert outline["chapters"][1]["character_focus"] == ["elena", "marcus"]

        r = client.get("/api/projects/ch_promote_ok/refinement-status")
        data = r.json()
        assert data["refinement_state"] == "chapter_outline_reviewing"
        assert data["intake_phase"] == "chapter"
        assert data["outline_draft_ready"] is True

    def test_promote_outline_draft_requires_outline_draft_ready(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ):
        from renpy_mcp.config import get_settings
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.blueprint.models import RefinementIntake

        _create_project(client, tmp_path, "ch_promote_blocked")
        settings = get_settings()
        monkeypatch.setattr(settings, "workspace", tmp_path)
        pm = ProjectManager(settings)

        brief = _make_valid_brief()
        client.put("/api/projects/ch_promote_blocked/brief", json=brief)
        _confirm_all_brief_cards(client, "ch_promote_blocked", brief)

        payload = _make_chapter_intake()
        payload["outline_draft_ready"] = False
        pm.write_refinement_intake("ch_promote_blocked", RefinementIntake.model_validate(payload))
        caplog.set_level(logging.INFO, logger="renpy_mcp.web.fastapi_app")

        r = client.post("/api/projects/ch_promote_blocked/chapter-outline/promote-draft")
        assert r.status_code == 409, r.text
        assert "draft" in r.json()["detail"].lower()
        assert "Chapter outline promote blocked for project ch_promote_blocked: outline draft not ready" in caplog.text
        flow_log = tmp_path / "ch_promote_blocked" / "logs" / "refinement-flow.log"
        assert flow_log.exists()
        assert "Chapter outline promote blocked for project ch_promote_blocked: outline draft not ready" in flow_log.read_text(
            encoding="utf-8"
        )

    def test_promote_outline_draft_requires_brief_fully_confirmed(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.config import get_settings
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.blueprint.models import RefinementIntake

        _create_project(client, tmp_path, "ch_promote_no_brief")
        settings = get_settings()
        monkeypatch.setattr(settings, "workspace", tmp_path)
        pm = ProjectManager(settings)

        # Do NOT confirm brief
        brief = _make_valid_brief()
        client.put("/api/projects/ch_promote_no_brief/brief", json=brief)

        payload = _make_chapter_intake()
        pm.write_refinement_intake("ch_promote_no_brief", RefinementIntake.model_validate(payload))

        r = client.post("/api/projects/ch_promote_no_brief/chapter-outline/promote-draft")
        assert r.status_code == 409, r.text
        assert "brief" in r.json()["detail"].lower()

    def test_refinement_status_exposes_chapter_intake_entry_state(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.config import get_settings
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.blueprint.models import RefinementIntake

        _create_project(client, tmp_path, "ch_intake_status")
        settings = get_settings()
        monkeypatch.setattr(settings, "workspace", tmp_path)
        pm = ProjectManager(settings)

        brief = _make_valid_brief()
        client.put("/api/projects/ch_intake_status/brief", json=brief)
        _confirm_all_brief_cards(client, "ch_intake_status", brief)

        payload = _make_chapter_intake()
        payload["outline_draft_ready"] = False
        pm.write_refinement_intake("ch_intake_status", RefinementIntake.model_validate(payload))

        r = client.get("/api/projects/ch_intake_status/refinement-status")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["refinement_state"] == "brief_confirmed"
        assert data["intake_phase"] == "chapter"
        assert data["outline_draft_ready"] is False
        assert data["chapter_intake_required"] is True
        assert data["brief_fully_confirmed"] is True

    def test_refinement_status_requires_chapter_intake_without_existing_intake_file(
        self, client: TestClient, tmp_path: Path
    ):
        _create_project(client, tmp_path, "ch_missing_intake")

        brief = _make_valid_brief()
        client.put("/api/projects/ch_missing_intake/brief", json=brief)
        _confirm_all_brief_cards(client, "ch_missing_intake", brief)

        r = client.get("/api/projects/ch_missing_intake/refinement-status")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["brief_fully_confirmed"] is True
        assert data["outline_draft_ready"] is False
        assert data["chapter_intake_required"] is True


# ---------------------------------------------------------------------------
# C. Refinement state machine
# ---------------------------------------------------------------------------


class TestRefinementStateMachine:
    def test_refinement_status_reflects_unconfirmed_brief(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "ref_status")
        r = client.get("/api/projects/ref_status/refinement-status")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["refinement_state"] is None or data["refinement_state"] == "idea_collecting"
        assert data["brief_fully_confirmed"] is False
        assert data["outline_fully_confirmed"] is False
        assert data["blueprint_ready"] is False
        assert data["generation_allowed"] is False  # no blueprint yet either

    def test_confirm_card_advances_brief_card(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "confirm_card")
        client.put("/api/projects/confirm_card/brief", json=_make_valid_brief())

        r = client.post(
            "/api/projects/confirm_card/brief/confirm-card",
            json={"card_key": "core_premise"},
        )
        assert r.status_code == 200, r.text

        r = client.get("/api/projects/confirm_card/brief")
        assert r.json()["cards"]["core_premise"]["confirmed"] is True

    def test_confirm_chapter_advances_chapter_card(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "confirm_ch")
        brief = _make_valid_brief()
        client.put("/api/projects/confirm_ch/brief", json=brief)
        client.put("/api/projects/confirm_ch/chapter-outline", json=_make_valid_outline())

        # Confirm all brief cards first (required by the hard gate)
        for key in brief["cards"]:
            client.post("/api/projects/confirm_ch/brief/confirm-card", json={"card_key": key})

        r = client.post(
            "/api/projects/confirm_ch/chapter-outline/confirm-chapter",
            json={"chapter_id": "ch1"},
        )
        assert r.status_code == 200, r.text

        r = client.get("/api/projects/confirm_ch/chapter-outline")
        ch1 = next(c for c in r.json()["chapters"] if c["chapter_id"] == "ch1")
        assert ch1["confirmed"] is True
        ch2 = next(c for c in r.json()["chapters"] if c["chapter_id"] == "ch2")
        assert ch2["confirmed"] is False


# ---------------------------------------------------------------------------
# D. Character identity gate
# ---------------------------------------------------------------------------


class TestCharacterIdentityGate:
    def test_brief_confirmation_rejects_name_only_character_identity_card(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "char_gate")
        brief = _make_valid_brief()
        # strip all substantive fields except name
        brief["cards"]["character_identity"]["content"]["characters"][0] = {
            "character_id": "elena",
            "name": "Elena",
            "story_role": "",
            "core_motivation": "",
            "personality_anchors": [],
            "visual_identity_anchors": [],
            "forbidden_drift": [],
        }
        client.put("/api/projects/char_gate/brief", json=brief)

        r = client.post(
            "/api/projects/char_gate/brief/confirm-card",
            json={"card_key": "character_identity"},
        )
        assert r.status_code == 400, r.text
        assert "identity" in r.json()["detail"].lower()

    def test_brief_confirmation_accepts_filled_character_identity_card(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "char_ok")
        client.put("/api/projects/char_ok/brief", json=_make_valid_brief())

        r = client.post(
            "/api/projects/char_ok/brief/confirm-card",
            json={"card_key": "character_identity"},
        )
        assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# E. Confirmation gates
# ---------------------------------------------------------------------------


class TestConfirmationGates:
    def test_project_cannot_enter_chapter_outline_confirmed_before_all_brief_cards_are_confirmed(
        self, client: TestClient, tmp_path: Path
    ):
        _create_project(client, tmp_path, "gate_brief")
        brief = _make_valid_brief()
        client.put("/api/projects/gate_brief/brief", json=brief)
        client.put("/api/projects/gate_brief/chapter-outline", json=_make_valid_outline())

        # Confirm only one brief card
        client.post("/api/projects/gate_brief/brief/confirm-card", json={"card_key": "core_premise"})

        # Attempt to confirm a chapter — must be rejected because brief is not fully confirmed
        r = client.post(
            "/api/projects/gate_brief/chapter-outline/confirm-chapter",
            json={"chapter_id": "ch1"},
        )
        assert r.status_code == 409, r.text
        assert "brief" in r.json()["detail"].lower()

        # The chapter must NOT be written as confirmed
        r = client.get("/api/projects/gate_brief/chapter-outline")
        ch1 = next(c for c in r.json()["chapters"] if c["chapter_id"] == "ch1")
        assert ch1["confirmed"] is False

        r = client.get("/api/projects/gate_brief/refinement-status")
        data = r.json()
        assert data["brief_fully_confirmed"] is False
        assert data["blueprint_ready"] is False

    def test_project_cannot_enter_blueprint_ready_before_all_chapters_are_confirmed(
        self, client: TestClient, tmp_path: Path
    ):
        _create_project(client, tmp_path, "gate_ch")
        brief = _make_valid_brief()
        client.put("/api/projects/gate_ch/brief", json=brief)
        client.put("/api/projects/gate_ch/chapter-outline", json=_make_valid_outline())

        # Confirm all brief cards
        for key in brief["cards"]:
            client.post("/api/projects/gate_ch/brief/confirm-card", json={"card_key": key})

        # Confirm only one chapter
        client.post("/api/projects/gate_ch/chapter-outline/confirm-chapter", json={"chapter_id": "ch1"})

        r = client.get("/api/projects/gate_ch/refinement-status")
        data = r.json()
        assert data["brief_fully_confirmed"] is True
        assert data["outline_fully_confirmed"] is False
        assert data["blueprint_ready"] is False

    def test_blueprint_ready_true_only_when_all_confirmed(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "ready_ok")
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/ready_ok/brief", json=brief)
        client.put("/api/projects/ready_ok/chapter-outline", json=outline)

        _confirm_all_brief_cards(client, "ready_ok", brief)
        _confirm_all_outline_chapters(client, "ready_ok", outline)

        r = client.get("/api/projects/ready_ok/refinement-status")
        data = r.json()
        assert data["brief_fully_confirmed"] is True
        assert data["outline_fully_confirmed"] is True
        assert data["blueprint_ready"] is True
        assert data["freeze_allowed"] is True
        assert data["blueprint_freeze_status"] == "not_frozen"
        assert data["generation_allowed"] is False


# ---------------------------------------------------------------------------
# F. Generation gates
# ---------------------------------------------------------------------------


class TestGenerationGates:
    def test_scene_packages_generate_is_blocked_before_blueprint_ready(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "gate_gen")
        # Seed a brief so the project is on the new refinement flow
        client.put("/api/projects/gate_gen/brief", json=_make_valid_brief())

        r = client.post("/api/projects/gate_gen/scene-packages/generate")
        assert r.status_code == 403, r.text
        detail = r.json()["detail"].lower()
        assert "blueprint_ready" in detail or "refinement" in detail

    def test_prototype_generate_is_blocked_before_blueprint_ready(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "gate_proto")
        # Seed a brief so the project is on the new refinement flow
        client.put("/api/projects/gate_proto/brief", json=_make_valid_brief())

        # scene_packages must exist for prototype generate; seed an empty one
        scene_packages = {"chapters": []}
        (tmp_path / "gate_proto" / "meta" / "scene_packages.json").write_text(
            json.dumps(scene_packages), encoding="utf-8"
        )

        r = client.post("/api/projects/gate_proto/prototype/multi-chapter/generate")
        assert r.status_code == 403, r.text
        detail = r.json()["detail"].lower()
        assert "blueprint_ready" in detail or "refinement" in detail

    def test_generation_gate_rejects_blueprint_ready_but_not_frozen(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "not_frozen_gate")
        blueprint = {
            "title": "Test",
            "genre": "Sci-fi",
            "worldview": "Space",
            "themes": ["discovery"],
            "target_audience": "Teens",
            "estimated_play_time": "2h",
            "art_style": "Cel-shaded",
            "audio_style": "Synth",
            "characters": [],
            "chapters": [],
        }
        seed = client.put("/api/projects/not_frozen_gate/blueprint", json=blueprint)
        assert seed.status_code == 200, seed.text
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/not_frozen_gate/brief", json=brief)
        client.put("/api/projects/not_frozen_gate/chapter-outline", json=outline)
        _confirm_all_brief_cards(client, "not_frozen_gate", brief)
        _confirm_all_outline_chapters(client, "not_frozen_gate", outline)

        r = client.post("/api/projects/not_frozen_gate/scene-packages/generate")
        assert r.status_code == 403, r.text
        assert "frozen" in r.json()["detail"].lower()

    def test_legacy_project_without_brief_is_generation_allowed(self, client: TestClient, tmp_path: Path):
        """Old projects that have a blueprint but no brief/outline should remain usable."""
        _create_project(client, tmp_path, "legacy_ok")
        blueprint = {
            "title": "Legacy",
            "genre": "Fantasy",
            "worldview": "Medieval",
            "themes": ["honor"],
            "target_audience": "All ages",
            "estimated_play_time": "1h",
            "art_style": "Pixel",
            "audio_style": "Orchestral",
            "characters": [],
            "chapters": [
                {
                    "id": "ch1",
                    "name": "Ch1",
                    "order": 1,
                    "scenes": [
                        {"id": "s1", "name": "S1", "order": 1, "characters": [], "backgrounds": [], "status": "pending", "type": "normal"}
                    ],
                }
            ],
        }
        client.put("/api/projects/legacy_ok/blueprint", json=blueprint)

        r = client.get("/api/projects/legacy_ok/refinement-status")
        data = r.json()
        assert data["generation_allowed"] is True


# ---------------------------------------------------------------------------
# G. Explicit blueprint freeze
# ---------------------------------------------------------------------------


class TestBlueprintFreeze:
    def test_refinement_status_requires_frozen_blueprint_for_generation(
        self, client: TestClient, tmp_path: Path
    ):
        _create_project(client, tmp_path, "freeze_status")
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/freeze_status/brief", json=brief)
        client.put("/api/projects/freeze_status/chapter-outline", json=outline)
        _confirm_all_brief_cards(client, "freeze_status", brief)
        _confirm_all_outline_chapters(client, "freeze_status", outline)

        r = client.get("/api/projects/freeze_status/refinement-status")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["blueprint_ready"] is True
        assert data["freeze_allowed"] is True
        assert data["blueprint_freeze_status"] == "not_frozen"
        assert data["generation_allowed"] is False

    def test_freeze_blueprint_creates_blueprint_and_marks_project_frozen(
        self, client: TestClient, tmp_path: Path
    ):
        _create_project(client, tmp_path, "freeze_ok")
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/freeze_ok/brief", json=brief)
        client.put("/api/projects/freeze_ok/chapter-outline", json=outline)
        _confirm_all_brief_cards(client, "freeze_ok", brief)
        _confirm_all_outline_chapters(client, "freeze_ok", outline)

        r = client.post("/api/projects/freeze_ok/blueprint/freeze")
        assert r.status_code == 200, r.text

        r = client.get("/api/projects/freeze_ok/blueprint")
        assert r.status_code == 200, r.text
        blueprint = r.json()
        assert blueprint["genre"] == "Sci-fi, teens."
        assert blueprint["worldview"] == "Faster-than-light travel exists."
        assert blueprint["art_style"] == "Cel-shaded, neon."
        assert len(blueprint["characters"]) == 1
        assert len(blueprint["chapters"]) == 2
        assert blueprint["chapters"][0]["id"] == "ch1"

        r = client.get("/api/projects/freeze_ok/refinement-status")
        data = r.json()
        assert data["blueprint_freeze_status"] == "frozen"
        assert data["generation_allowed"] is True

    def test_upstream_edit_marks_frozen_blueprint_stale(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "freeze_stale")
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/freeze_stale/brief", json=brief)
        client.put("/api/projects/freeze_stale/chapter-outline", json=outline)
        _confirm_all_brief_cards(client, "freeze_stale", brief)
        _confirm_all_outline_chapters(client, "freeze_stale", outline)
        freeze = client.post("/api/projects/freeze_stale/blueprint/freeze")
        assert freeze.status_code == 200, freeze.text

        brief["cards"]["core_premise"]["content"] = "Changed premise after freeze."
        update = client.put("/api/projects/freeze_stale/brief", json=brief)
        assert update.status_code == 200, update.text

        r = client.get("/api/projects/freeze_stale/refinement-status")
        data = r.json()
        assert data["blueprint_freeze_status"] == "stale"
        assert data["generation_allowed"] is False

    def test_freeze_blueprint_rolls_back_when_meta_persist_fails(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.services.project_manager import ProjectManager

        _create_project(client, tmp_path, "freeze_rollback")
        seed = client.put(
            "/api/projects/freeze_rollback/blueprint",
            json={
                "title": "Old",
                "genre": "Old",
                "worldview": "Old",
                "themes": [],
                "target_audience": "",
                "estimated_play_time": "",
                "art_style": "",
                "audio_style": "",
                "characters": [],
                "chapters": [],
            },
        )
        assert seed.status_code == 200, seed.text
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/freeze_rollback/brief", json=brief)
        client.put("/api/projects/freeze_rollback/chapter-outline", json=outline)
        _confirm_all_brief_cards(client, "freeze_rollback", brief)
        _confirm_all_outline_chapters(client, "freeze_rollback", outline)

        blueprint_path = tmp_path / "freeze_rollback" / "meta" / "blueprint.yaml"
        meta_path = tmp_path / "freeze_rollback" / "meta" / "project.json"
        old_blueprint = blueprint_path.read_text(encoding="utf-8")
        old_meta = meta_path.read_text(encoding="utf-8")

        def _failing_write_meta(*args, **kwargs):
            raise RuntimeError("disk full")

        monkeypatch.setattr(ProjectManager, "write_project_meta", _failing_write_meta)

        r = client.post("/api/projects/freeze_rollback/blueprint/freeze")
        assert r.status_code == 500, r.text
        assert blueprint_path.read_text(encoding="utf-8") == old_blueprint
        assert meta_path.read_text(encoding="utf-8") == old_meta

    def test_freeze_blueprint_replaces_existing_blueprint_and_keeps_backup(
        self, client: TestClient, tmp_path: Path
    ):
        _create_project(client, tmp_path, "freeze_backup")
        seed = client.put(
            "/api/projects/freeze_backup/blueprint",
            json={
                "title": "Old title",
                "genre": "Old genre",
                "worldview": "Old worldview",
                "themes": [],
                "target_audience": "",
                "estimated_play_time": "",
                "art_style": "",
                "audio_style": "",
                "characters": [],
                "chapters": [],
            },
        )
        assert seed.status_code == 200, seed.text
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/freeze_backup/brief", json=brief)
        client.put("/api/projects/freeze_backup/chapter-outline", json=outline)
        _confirm_all_brief_cards(client, "freeze_backup", brief)
        _confirm_all_outline_chapters(client, "freeze_backup", outline)

        r = client.post("/api/projects/freeze_backup/blueprint/freeze")
        assert r.status_code == 200, r.text

        backup_path = tmp_path / "freeze_backup" / "meta" / "blueprint.previous.yaml"
        assert backup_path.exists()
        backup_text = backup_path.read_text(encoding="utf-8")
        assert "Old title" in backup_text

    def test_manual_blueprint_put_is_rejected_for_refinement_projects(
        self, client: TestClient, tmp_path: Path
    ):
        _create_project(client, tmp_path, "freeze_no_bypass")
        client.put("/api/projects/freeze_no_bypass/brief", json=_make_valid_brief())

        r = client.put(
            "/api/projects/freeze_no_bypass/blueprint",
            json={
                "title": "Manual",
                "genre": "Manual genre",
                "worldview": "Manual worldview",
            },
        )
        assert r.status_code == 409, r.text
        assert "freeze" in r.json()["detail"].lower() or "refinement" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# G. Upstream edit invalidates downstream readiness
# ---------------------------------------------------------------------------


class TestUpstreamInvalidation:
    def test_brief_edit_unconfirms_card_and_invalidation_propagates(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "invalidate")
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/invalidate/brief", json=brief)
        client.put("/api/projects/invalidate/chapter-outline", json=outline)

        # Confirm everything
        for key in brief["cards"]:
            client.post("/api/projects/invalidate/brief/confirm-card", json={"card_key": key})
        for ch in outline["chapters"]:
            client.post(
                "/api/projects/invalidate/chapter-outline/confirm-chapter",
                json={"chapter_id": ch["chapter_id"]},
            )

        r = client.get("/api/projects/invalidate/refinement-status")
        assert r.json()["blueprint_ready"] is True

        # Edit a brief card (PUT replaces the whole brief)
        brief["cards"]["core_premise"]["content"] = "A darker story about loss."
        brief["cards"]["core_premise"]["confirmed"] = False
        client.put("/api/projects/invalidate/brief", json=brief)

        r = client.get("/api/projects/invalidate/refinement-status")
        data = r.json()
        assert data["brief_fully_confirmed"] is False
        assert data["blueprint_ready"] is False


# ---------------------------------------------------------------------------
# H. Chapter confirm hard gate
# ---------------------------------------------------------------------------


class TestChapterConfirmHardGate:
    def test_confirm_chapter_rejects_when_brief_is_not_fully_confirmed(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "ch_gate")
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/ch_gate/brief", json=brief)
        client.put("/api/projects/ch_gate/chapter-outline", json=outline)

        # Do NOT confirm any brief cards
        r = client.post(
            "/api/projects/ch_gate/chapter-outline/confirm-chapter",
            json={"chapter_id": "ch1"},
        )
        assert r.status_code == 409, r.text
        assert "brief" in r.json()["detail"].lower()

        r = client.get("/api/projects/ch_gate/chapter-outline")
        ch1 = next(c for c in r.json()["chapters"] if c["chapter_id"] == "ch1")
        assert ch1["confirmed"] is False


# ---------------------------------------------------------------------------
# I. Refinement status strict error handling
# ---------------------------------------------------------------------------


class TestRefinementStatusStrictErrors:
    def test_refinement_status_returns_500_for_invalid_brief(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "ref_bad_brief")
        bad_path = tmp_path / "ref_bad_brief" / "meta" / "project_brief.json"
        bad_path.write_text("not json", encoding="utf-8")
        r = client.get("/api/projects/ref_bad_brief/refinement-status")
        assert r.status_code == 500, r.text
        assert "brief" in r.json()["detail"].lower()

    def test_refinement_status_returns_500_for_invalid_chapter_outline(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "ref_bad_outline")
        bad_path = tmp_path / "ref_bad_outline" / "meta" / "chapter_outline.json"
        bad_path.write_text("not json", encoding="utf-8")
        r = client.get("/api/projects/ref_bad_outline/refinement-status")
        assert r.status_code == 500, r.text
        assert "outline" in r.json()["detail"].lower()

    def test_refinement_status_returns_500_for_invalid_project_meta(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "ref_bad_meta")
        # Also seed a valid brief so the endpoint is on the new-flow path
        client.put("/api/projects/ref_bad_meta/brief", json=_make_valid_brief())
        bad_path = tmp_path / "ref_bad_meta" / "meta" / "project.json"
        bad_path.write_text("not json", encoding="utf-8")
        r = client.get("/api/projects/ref_bad_meta/refinement-status")
        assert r.status_code == 500, r.text
        assert "meta" in r.json()["detail"].lower()

    def test_refinement_status_returns_500_for_invalid_legacy_blueprint(
        self, client: TestClient, tmp_path: Path
    ):
        _create_project(client, tmp_path, "ref_bad_bp")
        # No brief, no outline => legacy path. Seed a bad blueprint.yaml.
        bp_path = tmp_path / "ref_bad_bp" / "meta" / "blueprint.yaml"
        bp_path.write_text("not-yaml: [", encoding="utf-8")
        r = client.get("/api/projects/ref_bad_bp/refinement-status")
        assert r.status_code == 500, r.text
        detail = r.json()["detail"].lower()
        assert "blueprint" in detail


# ---------------------------------------------------------------------------
# J. Unified refinement state persistence
# ---------------------------------------------------------------------------


class TestRefinementStatePersistence:
    def test_refinement_state_is_persisted_to_blueprint_ready_when_all_confirmed(
        self, client: TestClient, tmp_path: Path
    ):
        _create_project(client, tmp_path, "persist_ready")
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/persist_ready/brief", json=brief)
        client.put("/api/projects/persist_ready/chapter-outline", json=outline)

        for key in brief["cards"]:
            client.post("/api/projects/persist_ready/brief/confirm-card", json={"card_key": key})
        for ch in outline["chapters"]:
            client.post(
                "/api/projects/persist_ready/chapter-outline/confirm-chapter",
                json={"chapter_id": ch["chapter_id"]},
            )

        # Verify refinement-status reports ready
        r = client.get("/api/projects/persist_ready/refinement-status")
        data = r.json()
        assert data["blueprint_ready"] is True
        assert data["refinement_state"] == "blueprint_ready"

        # Verify the state is actually persisted in meta/project.json
        meta_path = tmp_path / "persist_ready" / "meta" / "project.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta.get("refinement_state") == "blueprint_ready"


class TestBriefConfirmAutoPromotesOutline:
    def test_confirming_last_brief_card_auto_promotes_outline_draft_from_session(
        self, client: TestClient, tmp_path: Path
    ):
        """When the last brief card is confirmed and a blueprint session draft exists,
        the refinement intake should be auto-promoted to outline_ready."""
        _create_project(client, tmp_path, "auto_outline")
        brief = _make_valid_brief()
        client.put("/api/projects/auto_outline/brief", json=brief)

        # Seed an initial refinement intake in brief_ready state
        from renpy_mcp.blueprint.models import RefinementIntake, IntakePhase
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.config import get_settings
        pm = ProjectManager(get_settings())
        pm.write_refinement_intake(
            "auto_outline",
            RefinementIntake(phase=IntakePhase.BRIEF_READY, brief_draft_ready=True),
        )

        # Seed a blueprint session draft with chapters
        from renpy_mcp.web.chat_ws import _save_runtime_session
        blueprint_draft = {
            "title": "Auto Outline Test",
            "genre": "Sci-fi",
            "worldview": "Space",
            "themes": ["discovery"],
            "target_audience": "Teens",
            "estimated_play_time": "1 hour",
            "art_style": "",
            "audio_style": "",
            "characters": [],
            "chapters": [
                {
                    "id": "ch1",
                    "name": "Chapter 1",
                    "order": 1,
                    "scenes": [
                        {
                            "id": "s1",
                            "name": "Opening",
                            "order": 1,
                            "characters": ["Elena"],
                            "setting": "Ship",
                            "status": "pending",
                            "type": "normal",
                        }
                    ],
                },
                {
                    "id": "ch2",
                    "name": "Chapter 2",
                    "order": 2,
                    "scenes": [
                        {
                            "id": "s2",
                            "name": "Conflict",
                            "order": 1,
                            "characters": ["Elena", "Marcus"],
                            "setting": "Station",
                            "status": "pending",
                            "type": "normal",
                        }
                    ],
                },
            ],
        }
        _save_runtime_session("auto_outline", {
            "pipeline_stage": "idle",
            "turn_count": 2,
            "draft": blueprint_draft,
            "intake_mode": True,
            "awaiting_confirmation": False,
            "confirmation_id": None,
        })

        # Confirm all brief cards
        for key in brief["cards"]:
            r = client.post("/api/projects/auto_outline/brief/confirm-card", json={"card_key": key})
            assert r.status_code == 200, r.text

        # Verify refinement intake was auto-promoted to outline_ready
        r = client.get("/api/projects/auto_outline/refinement-intake")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["outline_draft_ready"] is True
        assert data["phase"] == "outline_ready"
        assert len(data["chapter_draft"]) == 2
        assert data["chapter_draft"][0]["chapter_id"] == "ch1"
        assert data["chapter_draft"][1]["chapter_id"] == "ch2"

    def test_confirming_brief_card_does_not_auto_promote_without_session_draft(
        self, client: TestClient, tmp_path: Path
    ):
        """If no blueprint session draft exists, confirm-card should not change intake phase."""
        _create_project(client, tmp_path, "no_session")
        brief = _make_valid_brief()
        client.put("/api/projects/no_session/brief", json=brief)

        # Confirm all brief cards (no blueprint session seeded)
        for key in brief["cards"]:
            r = client.post("/api/projects/no_session/brief/confirm-card", json={"card_key": key})
            assert r.status_code == 200, r.text

        # Refinement intake should not exist (never created)
        r = client.get("/api/projects/no_session/refinement-intake")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# O. confirm-chapter transaction rollback
# ---------------------------------------------------------------------------


class TestConfirmChapterRollback:
    def test_confirm_chapter_rolls_back_when_refinement_state_persist_fails(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.services.project_manager import ProjectManager

        _create_project(client, tmp_path, "rollback_ch")
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/rollback_ch/brief", json=brief)
        for key in brief["cards"]:
            client.post("/api/projects/rollback_ch/brief/confirm-card", json={"card_key": key})
        client.put("/api/projects/rollback_ch/chapter-outline", json=outline)
        # Confirm all but the last chapter first (state stays chapter_outline_reviewing)
        for ch in outline["chapters"][:-1]:
            client.post(
                "/api/projects/rollback_ch/chapter-outline/confirm-chapter",
                json={"chapter_id": ch["chapter_id"]},
            )

        outline_path = tmp_path / "rollback_ch" / "meta" / "chapter_outline.json"

        def _failing_write_meta(*args, **kwargs):
            raise RuntimeError("disk full")

        monkeypatch.setattr(ProjectManager, "write_project_meta", _failing_write_meta)

        old_text = outline_path.read_text(encoding="utf-8")

        # Confirming the last chapter will change state to blueprint_ready and trigger write_project_meta
        r = client.post(
            "/api/projects/rollback_ch/chapter-outline/confirm-chapter",
            json={"chapter_id": outline["chapters"][-1]["chapter_id"]},
        )
        assert r.status_code == 500, r.text

        assert outline_path.read_text(encoding="utf-8") == old_text

    def test_confirm_chapter_returns_500_for_invalid_project_brief(
        self, client: TestClient, tmp_path: Path
    ):
        _create_project(client, tmp_path, "bad_brief_ch")
        # Seed a valid outline
        outline = _make_valid_outline()
        client.put("/api/projects/bad_brief_ch/chapter-outline", json=outline)

        # Seed an invalid project_brief.json
        brief_path = tmp_path / "bad_brief_ch" / "meta" / "project_brief.json"
        brief_path.write_text("not-json", encoding="utf-8")

        r = client.post(
            "/api/projects/bad_brief_ch/chapter-outline/confirm-chapter",
            json={"chapter_id": outline["chapters"][0]["chapter_id"]},
        )
        assert r.status_code == 500, r.text
        data = r.json()
        detail = data.get("detail", "").lower()
        assert "brief" in detail or "project_brief.json" in detail


# ---------------------------------------------------------------------------
# P. character_identity semantic readiness gate
# ---------------------------------------------------------------------------


class TestCharacterIdentitySemanticReadiness:
    def test_invalid_confirmed_character_identity_blocks_blueprint_ready(
        self, client: TestClient, tmp_path: Path
    ):
        _create_project(client, tmp_path, "dirty_identity")

        # Craft a dirty brief with name-only character_identity but confirmed=true
        brief = _make_valid_brief()
        brief["cards"]["character_identity"]["content"]["characters"][0] = {
            "character_id": "elena",
            "name": "Elena",
            "story_role": "",
            "core_motivation": "",
            "personality_anchors": [],
            "visual_identity_anchors": [],
            "forbidden_drift": [],
        }
        for card in brief["cards"].values():
            card["confirmed"] = True
        brief_path = tmp_path / "dirty_identity" / "meta" / "project_brief.json"
        brief_path.write_text(json.dumps(brief), encoding="utf-8")

        # Seed a valid outline with all chapters confirmed directly on disk
        outline = _make_valid_outline()
        for ch in outline["chapters"]:
            ch["confirmed"] = True
        outline_path = tmp_path / "dirty_identity" / "meta" / "chapter_outline.json"
        outline_path.write_text(json.dumps(outline), encoding="utf-8")

        r = client.get("/api/projects/dirty_identity/refinement-status")
        data = r.json()
        assert data["blueprint_ready"] is False
        assert data["generation_allowed"] is False

    def test_generation_gate_rejects_invalid_confirmed_character_identity_even_when_flags_are_true(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService

        _create_project(client, tmp_path, "dirty_gen")
        # Seed a valid blueprint
        blueprint = {
            "title": "Test",
            "genre": "Sci-fi",
            "worldview": "Space",
            "themes": ["discovery"],
            "target_audience": "Teens",
            "estimated_play_time": "2h",
            "art_style": "Cel-shaded",
            "audio_style": "Synth",
            "characters": [],
            "chapters": [
                {
                    "id": "ch1",
                    "name": "Ch1",
                    "order": 1,
                    "scenes": [
                        {"id": "s1", "name": "S1", "order": 1, "characters": [], "backgrounds": [], "status": "pending", "type": "normal"}
                    ],
                }
            ],
        }
        client.put("/api/projects/dirty_gen/blueprint", json=blueprint)

        # Seed dirty brief: all confirmed, but character_identity is name-only
        brief = _make_valid_brief()
        brief["cards"]["character_identity"]["content"]["characters"][0] = {
            "character_id": "elena",
            "name": "Elena",
            "story_role": "",
            "core_motivation": "",
            "personality_anchors": [],
            "visual_identity_anchors": [],
            "forbidden_drift": [],
        }
        for card in brief["cards"].values():
            card["confirmed"] = True
        brief_path = tmp_path / "dirty_gen" / "meta" / "project_brief.json"
        brief_path.write_text(json.dumps(brief), encoding="utf-8")

        # Seed dirty outline: all chapters confirmed
        outline = _make_valid_outline()
        for ch in outline["chapters"]:
            ch["confirmed"] = True
        outline_path = tmp_path / "dirty_gen" / "meta" / "chapter_outline.json"
        outline_path.write_text(json.dumps(outline), encoding="utf-8")

        # Monkeypatch generation so if gate passes we get 200, not 503 from missing provider
        async def _fake_generate(*args, **kwargs):
            return {}

        monkeypatch.setattr(PrototypeGenerationService, "generate_all_chapter_scenes", _fake_generate)

        r = client.post("/api/projects/dirty_gen/scene-packages/generate")
        assert r.status_code == 403, r.text
        detail = r.json()["detail"].lower()
        assert "blueprint_ready" in detail or "refinement" in detail


# ---------------------------------------------------------------------------
# M. Write interface transaction rollback
# ---------------------------------------------------------------------------


class TestWriteInterfaceRollback:
    def test_put_brief_rolls_back_when_refinement_state_persist_fails(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.services.project_manager import ProjectManager

        _create_project(client, tmp_path, "rollback_brief")
        brief = _make_valid_brief()
        client.put("/api/projects/rollback_brief/brief", json=brief)
        # Confirm all cards so state advances past brief_reviewing
        for key in brief["cards"]:
            client.post("/api/projects/rollback_brief/brief/confirm-card", json={"card_key": key})

        brief_path = tmp_path / "rollback_brief" / "meta" / "project_brief.json"
        old_text = brief_path.read_text(encoding="utf-8")

        def _failing_write_meta(*args, **kwargs):
            raise RuntimeError("disk full")

        monkeypatch.setattr(ProjectManager, "write_project_meta", _failing_write_meta)

        # PUT resets confirmed, so state will change and trigger write_project_meta
        brief["cards"]["core_premise"]["content"] = "Modified."
        r = client.put("/api/projects/rollback_brief/brief", json=brief)
        assert r.status_code == 500, r.text

        assert brief_path.read_text(encoding="utf-8") == old_text

    def test_confirm_card_rolls_back_when_refinement_state_persist_fails(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.services.project_manager import ProjectManager

        _create_project(client, tmp_path, "rollback_card")
        brief = _make_valid_brief()
        client.put("/api/projects/rollback_card/brief", json=brief)

        brief_path = tmp_path / "rollback_card" / "meta" / "project_brief.json"

        def _failing_write_meta(*args, **kwargs):
            raise RuntimeError("disk full")

        monkeypatch.setattr(ProjectManager, "write_project_meta", _failing_write_meta)

        # Confirm all but the last card first (these succeed because state doesn't change yet)
        for key in list(brief["cards"].keys())[:-1]:
            client.post("/api/projects/rollback_card/brief/confirm-card", json={"card_key": key})

        # Save text after the successful partial confirmations
        old_text = brief_path.read_text(encoding="utf-8")

        # Confirming the last card will change state and trigger write_project_meta
        r = client.post(
            "/api/projects/rollback_card/brief/confirm-card",
            json={"card_key": list(brief["cards"].keys())[-1]},
        )
        assert r.status_code == 500, r.text

        assert brief_path.read_text(encoding="utf-8") == old_text

    def test_put_chapter_outline_rolls_back_when_refinement_state_persist_fails(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.services.project_manager import ProjectManager

        _create_project(client, tmp_path, "rollback_outline")
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/rollback_outline/brief", json=brief)
        for key in brief["cards"]:
            client.post("/api/projects/rollback_outline/brief/confirm-card", json={"card_key": key})
        client.put("/api/projects/rollback_outline/chapter-outline", json=outline)
        for ch in outline["chapters"]:
            client.post(
                "/api/projects/rollback_outline/chapter-outline/confirm-chapter",
                json={"chapter_id": ch["chapter_id"]},
            )

        outline_path = tmp_path / "rollback_outline" / "meta" / "chapter_outline.json"
        old_text = outline_path.read_text(encoding="utf-8")

        def _failing_write_meta(*args, **kwargs):
            raise RuntimeError("disk full")

        monkeypatch.setattr(ProjectManager, "write_project_meta", _failing_write_meta)

        # PUT resets confirmed, so state will change (blueprint_ready -> chapter_outline_reviewing)
        # and trigger write_project_meta
        outline["chapters"][0]["chapter_name"] = "Modified"
        r = client.put("/api/projects/rollback_outline/chapter-outline", json=outline)
        assert r.status_code == 500, r.text

        assert outline_path.read_text(encoding="utf-8") == old_text


# ---------------------------------------------------------------------------
# N. refinement-status must be read-only
# ---------------------------------------------------------------------------


class TestRefinementStatusReadOnly:
    def test_refinement_status_does_not_write_project_meta(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "status_read")
        brief = _make_valid_brief()
        client.put("/api/projects/status_read/brief", json=brief)

        meta_path = tmp_path / "status_read" / "meta" / "project.json"
        old_text = meta_path.read_text(encoding="utf-8")

        r = client.get("/api/projects/status_read/refinement-status")
        assert r.status_code == 200, r.text

        assert meta_path.read_text(encoding="utf-8") == old_text

    def test_refinement_status_reports_blueprint_ready_without_mutating_meta(
        self, client: TestClient, tmp_path: Path
    ):
        _create_project(client, tmp_path, "status_no_mutate")
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/status_no_mutate/brief", json=brief)
        client.put("/api/projects/status_no_mutate/chapter-outline", json=outline)

        for key in brief["cards"]:
            client.post("/api/projects/status_no_mutate/brief/confirm-card", json={"card_key": key})
        for ch in outline["chapters"]:
            client.post(
                "/api/projects/status_no_mutate/chapter-outline/confirm-chapter",
                json={"chapter_id": ch["chapter_id"]},
            )

        # Manually corrupt meta refinement_state to an old value
        meta_path = tmp_path / "status_no_mutate" / "meta" / "project.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["refinement_state"] = "brief_reviewing"
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

        r = client.get("/api/projects/status_no_mutate/refinement-status")
        data = r.json()
        assert data["blueprint_ready"] is True
        assert data["refinement_state"] == "blueprint_ready"

        # Meta must NOT be rewritten
        meta_after = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta_after["refinement_state"] == "brief_reviewing"

    def test_scene_packages_generate_is_allowed_after_refinement_reaches_blueprint_ready(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.services.prototype_generation_service import PrototypeGenerationService

        _create_project(client, tmp_path, "gen_allowed")
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/gen_allowed/brief", json=brief)
        client.put("/api/projects/gen_allowed/chapter-outline", json=outline)

        _confirm_all_brief_cards(client, "gen_allowed", brief)
        _confirm_all_outline_chapters(client, "gen_allowed", outline)

        # Seed a blueprint so generation can proceed past the gate
        blueprint = {
            "title": "Test",
            "genre": "Sci-fi",
            "worldview": "Space",
            "themes": ["discovery"],
            "target_audience": "Teens",
            "estimated_play_time": "2h",
            "art_style": "Cel-shaded",
            "audio_style": "Synth",
            "characters": [],
            "chapters": [
                {
                    "id": "ch1",
                    "name": "Ch1",
                    "order": 1,
                    "scenes": [
                        {"id": "s1", "name": "S1", "order": 1, "characters": [], "backgrounds": [], "status": "pending", "type": "normal"}
                    ],
                }
            ],
        }
        client.put("/api/projects/gen_allowed/blueprint", json=blueprint)

        freeze = client.post("/api/projects/gen_allowed/blueprint/freeze")
        assert freeze.status_code == 200, freeze.text

        # Monkeypatch the async generation so no real LLM/images are invoked
        async def _fake_generate(*args, **kwargs):
            return {}

        monkeypatch.setattr(PrototypeGenerationService, "generate_all_chapter_scenes", _fake_generate)

        r = client.post("/api/projects/gen_allowed/scene-packages/generate")
        # Must NOT be 403 (gate blocked). 200 means gate passed.
        assert r.status_code == 200, r.text

    def test_prototype_generate_is_allowed_after_refinement_reaches_blueprint_ready(
        self, client: TestClient, tmp_path: Path
    ):
        _create_project(client, tmp_path, "proto_allowed")
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/proto_allowed/brief", json=brief)
        client.put("/api/projects/proto_allowed/chapter-outline", json=outline)

        _confirm_all_brief_cards(client, "proto_allowed", brief)
        _confirm_all_outline_chapters(client, "proto_allowed", outline)

        # Seed blueprint and minimal scene packages
        blueprint = {
            "title": "Test",
            "genre": "Sci-fi",
            "worldview": "Space",
            "themes": ["discovery"],
            "target_audience": "Teens",
            "estimated_play_time": "2h",
            "art_style": "Cel-shaded",
            "audio_style": "Synth",
            "characters": [],
            "chapters": [
                {
                    "id": "ch1",
                    "name": "Ch1",
                    "order": 1,
                    "scenes": [
                        {"id": "s1", "name": "S1", "order": 1, "characters": [], "backgrounds": [], "status": "pending", "type": "normal"}
                    ],
                }
            ],
        }
        client.put("/api/projects/proto_allowed/blueprint", json=blueprint)

        freeze = client.post("/api/projects/proto_allowed/blueprint/freeze")
        assert freeze.status_code == 200, freeze.text

        scene_packages = {"chapters": []}
        (tmp_path / "proto_allowed" / "meta" / "scene_packages.json").write_text(
            json.dumps(scene_packages), encoding="utf-8"
        )

        r = client.post("/api/projects/proto_allowed/prototype/multi-chapter/generate")
        # Must NOT be 403 (gate blocked). 200 means gate passed.
        assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# K. Bulk PUT normalization prevents confirmed bypass
# ---------------------------------------------------------------------------


class TestBulkPutNormalization:
    def test_put_brief_resets_confirmed_flags_to_false(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "put_brief_norm")
        brief = _make_valid_brief()
        # Client tries to sneak in confirmed=true on every card
        for card in brief["cards"].values():
            card["confirmed"] = True
        r = client.put("/api/projects/put_brief_norm/brief", json=brief)
        assert r.status_code == 200, r.text

        r = client.get("/api/projects/put_brief_norm/brief")
        data = r.json()
        for key, card in data["cards"].items():
            assert card["confirmed"] is False, f"Card {key!r} should be reset to false by PUT"

    def test_put_chapter_outline_resets_confirmed_flags_to_false(self, client: TestClient, tmp_path: Path):
        _create_project(client, tmp_path, "put_outline_norm")
        outline = _make_valid_outline()
        # Client tries to sneak in confirmed=true on every chapter
        for ch in outline["chapters"]:
            ch["confirmed"] = True
        r = client.put("/api/projects/put_outline_norm/chapter-outline", json=outline)
        assert r.status_code == 200, r.text

        r = client.get("/api/projects/put_outline_norm/chapter-outline")
        data = r.json()
        for ch in data["chapters"]:
            assert ch["confirmed"] is False, f"Chapter {ch['chapter_id']!r} should be reset to false by PUT"

    def test_name_only_character_identity_cannot_reach_blueprint_ready_via_put_bypass(
        self, client: TestClient, tmp_path: Path
    ):
        _create_project(client, tmp_path, "put_bypass")
        brief = _make_valid_brief()
        # name-only character_identity
        brief["cards"]["character_identity"]["content"]["characters"][0] = {
            "character_id": "elena",
            "name": "Elena",
            "story_role": "",
            "core_motivation": "",
            "personality_anchors": [],
            "visual_identity_anchors": [],
            "forbidden_drift": [],
        }
        # Try to force confirmed on all cards via PUT
        for card in brief["cards"].values():
            card["confirmed"] = True
        client.put("/api/projects/put_bypass/brief", json=brief)

        outline = _make_valid_outline()
        for ch in outline["chapters"]:
            ch["confirmed"] = True
        client.put("/api/projects/put_bypass/chapter-outline", json=outline)

        r = client.get("/api/projects/put_bypass/refinement-status")
        data = r.json()
        assert data["blueprint_ready"] is False
        assert data["generation_allowed"] is False


# ---------------------------------------------------------------------------
# R4B. Chapter intake model extension
# ---------------------------------------------------------------------------


class TestChapterIntakeModel:
    def test_refinement_intake_roundtrip_supports_chapter_draft(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.config import get_settings
        from renpy_mcp.services.project_manager import ProjectManager
        from renpy_mcp.blueprint.models import RefinementIntake, ChapterIntakeEntry

        _create_project(client, tmp_path, "ch_intake_rt")
        settings = get_settings()
        monkeypatch.setattr(settings, "workspace", tmp_path)
        pm = ProjectManager(settings)

        payload = _make_valid_intake()
        payload["phase"] = "chapter"
        payload["outline_draft_ready"] = True
        payload["chapter_draft"] = [
            {
                "chapter_id": "ch1",
                "order": 1,
                "chapter_name": "Departure",
                "chapter_goal": "Establish motivation",
                "key_conflict": "Elena vs authority",
                "emotional_arc": "hope -> tension",
                "reveals": "Brother is missing",
                "end_state": "Elena leaves home",
                "mood_or_pacing_bias": "slow",
                "character_focus": ["elena"],
                "relationship_shift": "Elena distances from parents",
                "character_presentation_notes": "Civilian clothes",
            },
            {
                "chapter_id": "ch2",
                "order": 2,
                "chapter_name": "The Jump",
                "chapter_goal": "First FTL journey",
                "key_conflict": "Engine malfunction",
                "emotional_arc": "fear -> exhilaration",
                "reveals": "Marcus may still be alive",
                "end_state": "Arrival at Outpost 7",
                "mood_or_pacing_bias": "fast",
                "character_focus": ["elena", "marcus"],
                "relationship_shift": "Marcus reappears as ally",
                "character_presentation_notes": "Flight suit",
            },
        ]
        pm.write_refinement_intake("ch_intake_rt", RefinementIntake.model_validate(payload))

        intake = pm.read_refinement_intake("ch_intake_rt")
        assert intake is not None
        assert intake.phase == "chapter"
        assert intake.outline_draft_ready is True
        assert len(intake.chapter_draft) == 2
        assert intake.chapter_draft[0].chapter_id == "ch1"
        assert intake.chapter_draft[0].chapter_name == "Departure"
        assert intake.chapter_draft[1].character_focus == ["elena", "marcus"]

    def test_existing_project_intake_file_without_chapter_fields_remains_readable(
        self, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from renpy_mcp.config import get_settings
        from renpy_mcp.services.project_manager import ProjectManager

        _create_project(client, tmp_path, "ch_intake_legacy")
        settings = get_settings()
        monkeypatch.setattr(settings, "workspace", tmp_path)
        pm = ProjectManager(settings)

        # Write an old-style intake file (no chapter_draft, no outline_draft_ready)
        legacy = _make_valid_intake()
        intake_path = tmp_path / "ch_intake_legacy" / "meta" / "refinement_intake.json"
        intake_path.write_text(json.dumps(legacy), encoding="utf-8")

        intake = pm.read_refinement_intake("ch_intake_legacy")
        assert intake is not None
        assert intake.phase == "project"
        assert intake.brief_draft_ready is False
        assert intake.chapter_draft == []
        assert intake.outline_draft_ready is False


# ---------------------------------------------------------------------------
# L. Recompute uses current outline / brief side completeness
# ---------------------------------------------------------------------------


class TestRecomputeUsesCurrentCompanionData:
    def test_confirming_last_brief_card_with_existing_confirmed_outline_persists_blueprint_ready(
        self, client: TestClient, tmp_path: Path
    ):
        _create_project(client, tmp_path, "recompute_ok")
        brief = _make_valid_brief()
        outline = _make_valid_outline()
        client.put("/api/projects/recompute_ok/brief", json=brief)
        client.put("/api/projects/recompute_ok/chapter-outline", json=outline)

        # Confirm all brief cards first (required by chapter confirm gate)
        for key in brief["cards"]:
            client.post("/api/projects/recompute_ok/brief/confirm-card", json={"card_key": key})

        # Confirm all chapters
        for ch in outline["chapters"]:
            client.post(
                "/api/projects/recompute_ok/chapter-outline/confirm-chapter",
                json={"chapter_id": ch["chapter_id"]},
            )

        meta_path = tmp_path / "recompute_ok" / "meta" / "project.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta.get("refinement_state") == "blueprint_ready"

        # Now edit the brief via PUT (this resets all confirmed flags)
        brief["cards"]["core_premise"]["content"] = "Updated premise."
        client.put("/api/projects/recompute_ok/brief", json=brief)

        # State should have drifted back because PUT resets confirmed
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta.get("refinement_state") == "brief_reviewing"

        # Re-confirm all brief cards.  Because the outline is still fully confirmed
        # on disk, the helper must see it and advance straight to blueprint_ready.
        for key in brief["cards"]:
            client.post("/api/projects/recompute_ok/brief/confirm-card", json={"card_key": key})

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta.get("refinement_state") == "blueprint_ready"
