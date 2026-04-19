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
        # collecting message received
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


def test_blueprint_history_contains_structured_entries(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """After reaching reviewing, chat_history.json should contain blueprint_draft and confirmation_request entries."""
    project_name = "bp_history_struct"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: None)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({"type": "user_message", "content": f"turn {turn}", "project_name": project_name})
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                _drain_events(websocket, 3)

    history_path = tmp_path / project_name / "meta" / "chat_history.json"
    assert history_path.exists(), f"History file not found at {history_path}"
    history = json.loads(history_path.read_text(encoding="utf-8"))
    messages = history.get("messages", [])

    draft_entries = [m for m in messages if m.get("message_kind") == "blueprint_draft"]
    confirm_entries = [m for m in messages if m.get("message_kind") == "confirmation_request"]
    assert len(draft_entries) >= 1, f"Expected at least one blueprint_draft entry, got {messages}"
    assert len(confirm_entries) >= 1, f"Expected at least one confirmation_request entry, got {messages}"
    assert draft_entries[0].get("draft", {}).get("title") == project_name
    assert confirm_entries[0].get("confirmation_id")


def test_blueprint_generating_history_contains_progress_and_completion(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """After approving, chat_history.json should contain progress and system completion entries."""
    project_name = "bp_history_gen"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: None)

    with client.websocket_connect("/ws/chat") as websocket:
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

        websocket.send_json({
            "type": "confirmation_response",
            "confirmation_id": confirmation_id,
            "approved": True,
            "project_name": project_name,
        })
        events = []
        while True:
            data = websocket.receive_json()
            events.append(data)
            if data.get("pipeline_stage") == "editing" and data["type"] == "message":
                break

    history_path = tmp_path / project_name / "meta" / "chat_history.json"
    assert history_path.exists()
    history = json.loads(history_path.read_text(encoding="utf-8"))
    messages = history.get("messages", [])

    progress_entries = [m for m in messages if m.get("message_kind") == "progress"]
    system_entries = [m for m in messages if m.get("message_kind") == "system"]
    assert len(progress_entries) >= 1, f"Expected at least one progress entry, got {messages}"
    assert len(system_entries) >= 1, f"Expected at least one system entry, got {messages}"
    assert any("蓝图生成完成" in (m.get("content", "") or "") for m in system_entries)


def test_blueprint_generating_history_persists_progress_incrementally(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Progress entries should be written to history incrementally during generating, not just at completion."""
    project_name = "bp_history_incr"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: None)

    import renpy_mcp.web.chat_ws as chat_ws_module
    save_call_count = [0]
    original_save = chat_ws_module.BlueprintOrchestrator._save_history

    def counting_save(self):
        save_call_count[0] += 1
        original_save(self)

    monkeypatch.setattr(chat_ws_module.BlueprintOrchestrator, "_save_history", counting_save)

    with client.websocket_connect("/ws/chat") as websocket:
        # Start + 2 turns to reviewing
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

        # Receive first progress event.
        # At this point handle_confirmation_response has fully executed,
        # so _save_history call count reveals whether saves were incremental.
        first_progress = websocket.receive_json()
        assert first_progress["type"] == "progress"

        # Continue receiving remaining events so the server can finish cleanly
        while True:
            data = websocket.receive_json()
            if data.get("pipeline_stage") == "editing" and data["type"] == "message":
                break

    # After full generating cycle:
    # - Before generating: _save_history called 3 times (start + 2 turns)
    # - With incremental saves: +5 progress + 1 system = 9 total
    # - Without incremental saves: +1 system = 4 total
    assert save_call_count[0] >= 7, f"Expected incremental _save_history calls (>=7), got {save_call_count[0]}"


# ---------------------------------------------------------------------------
# Blueprint session state persistence tests
# ---------------------------------------------------------------------------

def test_blueprint_session_persisted_in_reviewing(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """After reaching reviewing, blueprint_session.json should contain recoverable state."""
    project_name = "bp_session_review"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: None)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({"type": "user_message", "content": f"turn {turn}", "project_name": project_name})
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                _drain_events(websocket, 3)

    session_path = tmp_path / project_name / "meta" / "blueprint_session.json"
    assert session_path.exists(), f"Session file not found at {session_path}"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert session["pipeline_stage"] == "reviewing"
    assert session["awaiting_confirmation"] is True
    assert session["confirmation_id"]
    assert session["draft"]["title"] == project_name


def test_blueprint_session_restores_orchestrator_state(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """After removing in-memory orchestrator, a new one should recover from session and handle confirmation."""
    project_name = "bp_session_restore"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: None)

    confirmation_id = None
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({"type": "user_message", "content": f"turn {turn}", "project_name": project_name})
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                events = _drain_events(websocket, 3)
                req = next(e for e in events if e["type"] == "confirmation_request")
                confirmation_id = req["confirmation_id"]

    # Simulate service restart: remove in-memory orchestrator
    import renpy_mcp.web.chat_ws as chat_ws
    if project_name in chat_ws._orchestrators:
        del chat_ws._orchestrators[project_name]

    # Now send confirmation_response with a fresh connection
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({
            "type": "confirmation_response",
            "confirmation_id": confirmation_id,
            "approved": True,
            "project_name": project_name,
        })
        events = []
        while True:
            data = websocket.receive_json()
            events.append(data)
            if data.get("pipeline_stage") == "editing" and data["type"] == "message":
                break

    progress_events = [e for e in events if e["type"] == "progress"]
    assert len(progress_events) >= 1


def test_blueprint_session_updates_latest_progress(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """During generating, _save_blueprint_session should be called with latest_progress."""
    project_name = "bp_session_progress"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: None)

    import renpy_mcp.web.chat_ws as chat_ws_module
    saved_states: list[dict] = []
    original_save_session = chat_ws_module._save_runtime_session

    def tracking_save_session(project_name_arg: str, state: dict) -> None:
        saved_states.append(state)
        original_save_session(project_name_arg, state)

    monkeypatch.setattr(chat_ws_module, "_save_runtime_session", tracking_save_session)

    confirmation_id = None
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({"type": "user_message", "content": f"turn {turn}", "project_name": project_name})
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                events = _drain_events(websocket, 3)
                req = next(e for e in events if e["type"] == "confirmation_request")
                confirmation_id = req["confirmation_id"]

        websocket.send_json({
            "type": "confirmation_response",
            "confirmation_id": confirmation_id,
            "approved": True,
            "project_name": project_name,
        })
        while True:
            data = websocket.receive_json()
            if data.get("pipeline_stage") == "editing" and data["type"] == "message":
                break

    # At least one saved state should contain latest_progress during generating
    progress_states = [s for s in saved_states if s.get("latest_progress")]
    assert len(progress_states) >= 1, f"Expected at least one state with latest_progress, got {saved_states}"
    assert progress_states[-1]["pipeline_stage"] == "generating"
    assert progress_states[-1]["latest_progress"]["percent"] > 0


def test_blueprint_session_cleared_on_editing(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """After editing completes, blueprint_session.json should be cleared."""
    project_name = "bp_session_cleared"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: None)

    confirmation_id = None
    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({"type": "user_message", "content": f"turn {turn}", "project_name": project_name})
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                events = _drain_events(websocket, 3)
                req = next(e for e in events if e["type"] == "confirmation_request")
                confirmation_id = req["confirmation_id"]

        websocket.send_json({
            "type": "confirmation_response",
            "confirmation_id": confirmation_id,
            "approved": True,
            "project_name": project_name,
        })
        while True:
            data = websocket.receive_json()
            if data.get("pipeline_stage") == "editing" and data["type"] == "message":
                break

    session_path = tmp_path / project_name / "meta" / "blueprint_session.json"
    assert not session_path.exists(), f"Session file should be cleared after editing, but found {session_path.read_text()}"


def test_blueprint_session_api_returns_state(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """GET /api/projects/{name}/blueprint-session should return current session state."""
    project_name = "bp_session_api"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: None)

    # Before any activity, session should indicate idle
    resp = client.get(f"/api/projects/{project_name}/blueprint-session")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pipeline_stage"] == "idle"
    assert data["awaiting_confirmation"] is False

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({"type": "user_message", "content": f"turn {turn}", "project_name": project_name})
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                _drain_events(websocket, 3)

    # After reviewing, API should reflect session
    resp = client.get(f"/api/projects/{project_name}/blueprint-session")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pipeline_stage"] == "reviewing"
    assert data["awaiting_confirmation"] is True
    assert data["confirmation_id"]
    assert data["draft"]["title"] == project_name


def test_blueprint_session_api_returns_404_for_missing_project(client: TestClient) -> None:
    """GET /api/projects/{name}/blueprint-session for a non-existent project should return 404."""
    resp = client.get("/api/projects/nonexistent_project/blueprint-session")
    assert resp.status_code == 404
    data = resp.json()
    assert data["detail"] == "Project not found"
