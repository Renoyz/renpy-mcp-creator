"""Integration tests for blueprint interview orchestration over /ws/chat."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
    """Helper to create a project with minimal game structure."""
    game_dir = tmp_path / name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")
    r = client.post("/api/projects", json={"name": name})
    assert r.status_code == 200


def _drain_events(websocket, expected_count: int) -> list[dict]:
    """Read exactly expected_count JSON messages from the WebSocket."""
    events = []
    for _ in range(expected_count):
        events.append(websocket.receive_json())
    return events


def test_blueprint_start_trigger_returns_first_collecting_message(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Sending start_blueprint_collection should return the first collecting assistant message from backend."""
    project_name = "bp_start"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: None)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        events = _drain_events(websocket, 1)
        assert events[0]["type"] == "message"
        assert events[0]["role"] == "assistant"
        assert "太棒了" in events[0]["content"]
        assert events[0]["pipeline_stage"] == "collecting"


def test_blueprint_user_message_collecting_to_reviewing(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Sending user_message to a project without blueprint should enter collecting and eventually reviewing."""
    project_name = "bp_collect"
    _create_project(client, tmp_path, project_name)

    # Disable real ChatEngine so we only test orchestrator
    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: None)

    with client.websocket_connect("/ws/chat") as websocket:
        # Start trigger -> first collecting message (does not consume a turn)
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        events = _drain_events(websocket, 1)
        assert events[0]["type"] == "message"
        assert events[0]["role"] == "assistant"
        assert events[0].get("message_kind") == "text"
        assert "太棒了" in events[0]["content"]
        assert events[0]["pipeline_stage"] == "collecting"

        # Turn 1 -> collecting
        websocket.send_json({"type": "user_message", "content": "hello", "project_name": project_name})
        events = _drain_events(websocket, 1)
        print("DEBUG EVENT:", events[0])
        assert events[0]["type"] == "message"
        assert events[0]["role"] == "assistant"
        assert events[0]["pipeline_stage"] == "collecting"

        # Turn 2 -> reviewing (text message + blueprint_draft message + confirmation_request)
        websocket.send_json({"type": "user_message", "content": "final info", "project_name": project_name})
        events = _drain_events(websocket, 3)

        types = [e["type"] for e in events]
        assert types.count("message") == 2
        assert "confirmation_request" in types

        draft_event = next(e for e in events if e["type"] == "message" and e.get("message_kind") == "blueprint_draft")
        assert draft_event["draft"]["title"] == project_name
        assert draft_event["pipeline_stage"] == "reviewing"

        req_event = next(e for e in events if e["type"] == "confirmation_request")
        assert req_event["confirmation_id"]
        assert req_event["pipeline_stage"] == "reviewing"


def test_blueprint_confirmation_approve_generates_and_edits(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Approving confirmation should drive generating -> editing and persist blueprint."""
    project_name = "bp_approve"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: None)

    with client.websocket_connect("/ws/chat") as websocket:
        # Start trigger (1 event) + get to reviewing (2 turns, last turn emits 3 events)
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({"type": "user_message", "content": f"turn {turn}", "project_name": project_name})
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                events = _drain_events(websocket, 3)
                req_event = next(e for e in events if e["type"] == "confirmation_request")
                confirmation_id = req_event["confirmation_id"]

        # Approve
        websocket.send_json({
            "type": "confirmation_response",
            "confirmation_id": confirmation_id,
            "approved": True,
            "project_name": project_name,
        })

        # Expect: progress events + final editing message
        events = []
        while True:
            data = websocket.receive_json()
            events.append(data)
            if data.get("pipeline_stage") == "editing" and data["type"] == "message":
                break

        progress_events = [e for e in events if e["type"] == "progress"]
        assert len(progress_events) >= 1

        # Verify blueprint was persisted
        resp = client.get(f"/api/projects/{project_name}/blueprint")
        assert resp.status_code == 200
        bp = resp.json()
        assert bp["title"] == project_name
        assert len(bp["chapters"]) > 0

        # Verify meta was updated
        resp = client.get(f"/api/projects/{project_name}/meta")
        assert resp.status_code == 200
        meta = resp.json()
        assert meta["pipeline_stage"] == "editing"


def test_blueprint_confirmation_reject_returns_to_collecting(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Rejecting confirmation should return to collecting with a new assistant message."""
    project_name = "bp_reject"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: None)

    with client.websocket_connect("/ws/chat") as websocket:
        # Start trigger + get to reviewing
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({"type": "user_message", "content": f"turn {turn}", "project_name": project_name})
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                events = _drain_events(websocket, 3)
                req_event = next(e for e in events if e["type"] == "confirmation_request")
                confirmation_id = req_event["confirmation_id"]

        # Reject
        websocket.send_json({
            "type": "confirmation_response",
            "confirmation_id": confirmation_id,
            "approved": False,
            "project_name": project_name,
        })

        events = _drain_events(websocket, 1)
        assert events[0]["type"] == "message"
        assert events[0]["role"] == "assistant"
        assert events[0]["pipeline_stage"] == "collecting"

        # Should be able to continue collecting
        websocket.send_json({"type": "user_message", "content": "adjustment", "project_name": project_name})
        events = _drain_events(websocket, 1)
        assert events[0]["type"] == "message"
        assert events[0]["pipeline_stage"] == "collecting"
