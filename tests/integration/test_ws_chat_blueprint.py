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


def _make_mock_blueprint_provider(title: str = "DEFAULT", **overrides) -> object:
    """Return a mock LLM provider that returns a fixed JSON blueprint."""
    blueprint = {
        "title": title,
        "genre": "校园恋爱",
        "worldview": "现代日本高中",
        "themes": ["初恋", "成长"],
        "target_audience": "18-25岁视觉小说爱好者",
        "estimated_play_time": "2-3小时",
        "art_style": "日系动漫风格",
        "audio_style": "治愈系钢琴配乐",
        "characters": [
            {"name": "主角A", "role": "主角", "personality": "勇敢", "appearance": "高大"},
        ],
        "chapters": [
            {
                "id": "ch1",
                "name": "第一章",
                "order": 1,
                "scenes": [{"id": "s1", "name": "场景1", "order": 1}],
            }
        ],
    }
    blueprint.update(overrides)

    class MockProvider:
        tool_format = "anthropic"

        def chat(self, messages, tools=None, system=None, model=None, max_tokens=1024, temperature=None):
            from renpy_mcp.chat_engine.providers import LLMResponse
            return LLMResponse(
                content_blocks=[{"type": "text", "text": json.dumps(blueprint, ensure_ascii=False)}],
                stop_reason="end_turn",
            )

    return MockProvider()


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


def _make_mock_smart_provider(title: str = "DEFAULT", **overrides) -> object:
    """Return a mock provider that handles both blueprint and prototype scene generation."""
    blueprint = {
        "title": title,
        "genre": "校园恋爱",
        "worldview": "现代日本高中",
        "themes": ["初恋", "成长"],
        "target_audience": "18-25岁视觉小说爱好者",
        "estimated_play_time": "2-3小时",
        "art_style": "日系动漫风格",
        "audio_style": "治愈系钢琴配乐",
        "characters": [
            {"name": "主角A", "role": "主角", "personality": "勇敢", "appearance": "高大"},
        ],
        "chapters": [
            {
                "id": "ch1",
                "name": "第一章",
                "order": 1,
                "scenes": [{"id": "s1", "name": "场景1", "order": 1}],
            }
        ],
    }
    blueprint.update(overrides)

    class MockSmartProvider:
        tool_format = "anthropic"

        def chat(self, messages, tools=None, system=None, model=None, max_tokens=1024, temperature=None):
            from renpy_mcp.chat_engine.providers import LLMResponse
            prompt = messages[0].get("content", "") if messages else ""

            # Prototype scene generation prompt
            if "Generate a JSON array of scenes" in prompt:
                scenes = [
                    {
                        "scene_id": "proto-s1",
                        "title": "Test Scene",
                        "summary": "Test summary.",
                        "location": "library",
                        "characters_present": ["主角A"],
                        "entry_label": "prototype_ch1_start",
                        "next_scene_id": None,
                    }
                ]
                return LLMResponse(
                    content_blocks=[{"type": "text", "text": json.dumps(scenes, ensure_ascii=False)}],
                    stop_reason="end_turn",
                )

            # Blueprint generation prompt
            return LLMResponse(
                content_blocks=[{"type": "text", "text": json.dumps(blueprint, ensure_ascii=False)}],
                stop_reason="end_turn",
            )

    return MockSmartProvider()


def test_blueprint_start_trigger_returns_first_collecting_message(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Sending start_blueprint_collection should return the first collecting assistant message from backend."""
    project_name = "bp_start"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        events = _drain_events(websocket, 1)
        assert events[0]["type"] == "message"
        assert events[0]["role"] == "assistant"
        assert "让我来帮你把这个想法变成完整的蓝图" in events[0]["content"]
        assert events[0]["pipeline_stage"] == "collecting"


def test_blueprint_user_message_collecting_to_reviewing(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Sending user_message to a project without blueprint should enter collecting and eventually reviewing."""
    project_name = "bp_collect"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

    with client.websocket_connect("/ws/chat") as websocket:
        # Start trigger -> first collecting message (does not consume a turn)
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        events = _drain_events(websocket, 1)
        assert events[0]["type"] == "message"
        assert events[0]["role"] == "assistant"
        assert events[0].get("message_kind") == "text"
        assert "让我来帮你把这个想法变成完整的蓝图" in events[0]["content"]
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

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

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


def test_confirmation_success_creates_prototype_artifacts(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Approving confirmation should generate prototype artifacts and wire main script."""
    from renpy_mcp.services.prototype_generation_service import PrototypeScene

    project_name = "bp_proto_success"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

    mock_scenes = [
        PrototypeScene(
            scene_id="proto-ch1-s1",
            title="开场",
            summary="主角登场。",
            location="classroom",
            characters_present=["主角"],
            entry_label="prototype_ch1_start",
            next_scene_id=None,
        ),
    ]

    async def _mock_generate_scenes(self, chapter, blueprint):
        return mock_scenes

    monkeypatch.setattr(
        "renpy_mcp.services.prototype_generation_service.PrototypeGenerationService.generate_scenes",
        _mock_generate_scenes,
    )

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

    # Verify prototype file exists
    game_dir = tmp_path / project_name / "game"
    proto_files = [p for p in game_dir.glob("prototype*") if p.suffix == ".rpy"]
    assert len(proto_files) == 1, f"Expected exactly one prototype .rpy file, got {list(game_dir.glob('prototype*'))}"

    # Verify main script is wired
    script_path = game_dir / "script.rpy"
    assert script_path.exists()
    content = script_path.read_text(encoding="utf-8")
    assert "call prototype_ch1_start" in content

    # Verify index contains scene mapping
    index_path = tmp_path / project_name / "meta" / "index.json"
    assert index_path.exists()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert "scenes" in index
    assert "proto-ch1-s1" in index["scenes"]


def test_confirmation_failure_surfaces_prototype_generation_error(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Prototype generation failure should be surfaced in the final editing message."""
    project_name = "bp_proto_fail"
    _create_project(client, tmp_path, project_name)

    # Mock blueprint provider works for draft but returns dict instead of scenes list,
    # causing prototype generation to fail
    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

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

    final_message = next(e for e in events if e["type"] == "message" and e.get("pipeline_stage") == "editing")
    content = final_message["content"]
    assert "原型生成失败" in content or "prototype generation failed" in content.lower()

    # Blueprint and meta should still be persisted
    resp = client.get(f"/api/projects/{project_name}/blueprint")
    assert resp.status_code == 200

    resp = client.get(f"/api/projects/{project_name}/meta")
    assert resp.status_code == 200
    assert resp.json()["pipeline_stage"] == "editing"


def test_blueprint_confirmation_reject_returns_to_collecting(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Rejecting confirmation should return to collecting with a new assistant message."""
    project_name = "bp_reject"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

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

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

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

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

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
    assert any("蓝图" in (m.get("content", "") or "") for m in system_entries)


def test_blueprint_generating_history_persists_progress_incrementally(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Progress entries should be written to history incrementally during generating, not just at completion."""
    project_name = "bp_history_incr"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

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

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

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

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

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

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

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

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

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

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: _make_mock_blueprint_provider(title=project_name))

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


# ---------------------------------------------------------------------------
# Blueprint LLM draft generation tests
# ---------------------------------------------------------------------------


def test_blueprint_draft_generation_provider_error_not_misclassified(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Provider.chat raising an exception must produce a provider error, not a schema error, and must not retry."""
    project_name = "bp_provider_err"
    _create_project(client, tmp_path, project_name)

    class ExplodingProvider:
        tool_format = "anthropic"
        _call_count = 0

        def chat(self, messages, tools=None, system=None, model=None, max_tokens=1024, temperature=None):
            self._call_count += 1
            raise RuntimeError("Simulated provider SDK failure (e.g. 401/model not found)")

    provider = ExplodingProvider()
    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: provider)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({"type": "user_message", "content": f"turn {turn}", "project_name": project_name})
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                events = _drain_events(websocket, 1)

    assert provider._call_count == 1, f"Provider error must NOT retry, but chat was called {provider._call_count} times"
    assert events[0]["type"] == "error"
    assert "collecting" in events[0].get("pipeline_stage", "")
    error_msg = events[0].get("message", "")
    # Must contain provider error semantics, NOT schema validation semantics
    assert "provider error" in error_msg.lower() or "蓝图生成失败" in error_msg
    assert "schema validation" not in error_msg.lower()
    # Must NOT have entered reviewing
    assert "reviewing" not in str(events)


def test_blueprint_draft_is_generated_from_provider_not_hardcoded(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Reviewing draft must come from the LLM provider, not hardcoded defaults."""
    project_name = "bp_llm_real"
    _create_project(client, tmp_path, project_name)

    provider = _make_mock_blueprint_provider(
        title="LLM生成标题",
        genre="科幻",
        worldview="未来火星殖民地",
        characters=[
            {"name": "唯一角色名", "role": "主角", "personality": "冷静", "appearance": "机械臂"}
        ],
    )
    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: provider)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({"type": "user_message", "content": f"turn {turn}", "project_name": project_name})
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                events = _drain_events(websocket, 3)

    draft_event = next(e for e in events if e["type"] == "message" and e.get("message_kind") == "blueprint_draft")
    draft = draft_event["draft"]
    assert draft["title"] == "LLM生成标题"
    assert draft["genre"] == "科幻"
    assert draft["worldview"] == "未来火星殖民地"
    assert len(draft["characters"]) == 1
    assert draft["characters"][0]["name"] == "唯一角色名"
    # Must NOT be the old hardcoded defaults
    assert draft["genre"] != "校园恋爱"


def test_blueprint_draft_generation_rejects_invalid_json(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Provider returning non-JSON must produce an error and not enter reviewing."""
    project_name = "bp_bad_json"
    _create_project(client, tmp_path, project_name)

    class BadJsonProvider:
        tool_format = "anthropic"

        def chat(self, messages, tools=None, system=None, model=None, max_tokens=1024, temperature=None):
            from renpy_mcp.chat_engine.providers import LLMResponse
            return LLMResponse(
                content_blocks=[{"type": "text", "text": "This is not JSON at all"}],
                stop_reason="end_turn",
            )

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: BadJsonProvider())

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({"type": "user_message", "content": f"turn {turn}", "project_name": project_name})
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                events = _drain_events(websocket, 1)

    assert events[0]["type"] == "error"
    assert "collecting" in events[0].get("pipeline_stage", "")
    # Must NOT have entered reviewing
    assert "reviewing" not in str(events)


def test_blueprint_draft_generation_rejects_invalid_schema(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Provider returning JSON that fails ProjectBlueprint validation must produce an error."""
    project_name = "bp_bad_schema"
    _create_project(client, tmp_path, project_name)

    class BadSchemaProvider:
        tool_format = "anthropic"

        def chat(self, messages, tools=None, system=None, model=None, max_tokens=1024, temperature=None):
            from renpy_mcp.chat_engine.providers import LLMResponse
            bad_data = {"title": "bad", "genre": "bad"}  # Missing required fields like worldview
            return LLMResponse(
                content_blocks=[{"type": "text", "text": json.dumps(bad_data, ensure_ascii=False)}],
                stop_reason="end_turn",
            )

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: BadSchemaProvider())

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({"type": "user_message", "content": f"turn {turn}", "project_name": project_name})
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                events = _drain_events(websocket, 1)

    assert events[0]["type"] == "error"
    assert "collecting" in events[0].get("pipeline_stage", "")
    assert "reviewing" not in str(events)


def test_get_provider_uses_anthropic_model_env_var(monkeypatch) -> None:
    """_get_provider() must read ANTHROPIC_MODEL and pass it to AnthropicProvider.default_model."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.kimi.com/coding/")
    monkeypatch.setenv("ANTHROPIC_MODEL", "kimi-k2.5")
    # Ensure no mock override is active
    monkeypatch.delenv("RENPY_MCP_MOCK_LLM", raising=False)

    from renpy_mcp.web.chat_ws import _get_provider

    provider = _get_provider()
    assert provider is not None
    assert provider.default_model == "kimi-k2.5"


def test_get_provider_anthropic_model_fallback_to_default(monkeypatch) -> None:
    """When ANTHROPIC_MODEL is not set, _get_provider() must fallback to the default model."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.kimi.com/coding/")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("RENPY_MCP_MOCK_LLM", raising=False)

    from renpy_mcp.web.chat_ws import _get_provider

    provider = _get_provider()
    assert provider is not None
    assert provider.default_model == "claude-3-5-sonnet"


def test_blueprint_draft_generation_retries_then_succeeds(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """First attempt returns invalid JSON, second attempt returns valid blueprint."""
    project_name = "bp_retry"
    _create_project(client, tmp_path, project_name)

    class RetryThenSuccessProvider:
        tool_format = "anthropic"
        _call_count = 0

        def chat(self, messages, tools=None, system=None, model=None, max_tokens=1024, temperature=None):
            self._call_count += 1
            from renpy_mcp.chat_engine.providers import LLMResponse
            if self._call_count == 1:
                return LLMResponse(
                    content_blocks=[{"type": "text", "text": "not valid json"}],
                    stop_reason="end_turn",
                )
            blueprint = {
                "title": "RetrySuccess",
                "genre": "测试",
                "worldview": "测试",
                "themes": ["测试"],
                "target_audience": "测试",
                "estimated_play_time": "1小时",
                "art_style": "测试",
                "audio_style": "测试",
                "characters": [
                    {"name": "测试角色", "role": "主角", "personality": "测试", "appearance": "测试"}
                ],
                "chapters": [
                    {
                        "id": "ch1",
                        "name": "第一章",
                        "order": 1,
                        "scenes": [{"id": "s1", "name": "场景1", "order": 1}],
                    }
                ],
            }
            return LLMResponse(
                content_blocks=[{"type": "text", "text": json.dumps(blueprint, ensure_ascii=False)}],
                stop_reason="end_turn",
            )

    provider = RetryThenSuccessProvider()
    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: provider)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        for turn in range(2):
            websocket.send_json({"type": "user_message", "content": f"turn {turn}", "project_name": project_name})
            if turn < 1:
                _drain_events(websocket, 1)
            else:
                events = _drain_events(websocket, 3)

    assert provider._call_count == 2
    draft_event = next(e for e in events if e["type"] == "message" and e.get("message_kind") == "blueprint_draft")
    assert draft_event["draft"]["title"] == "RetrySuccess"


def test_blueprint_draft_defaults_to_chinese_output_with_mock_provider(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """Mock provider should default blueprint draft content to Chinese."""
    project_name = "bp_lang_zh"
    _create_project(client, tmp_path, project_name)
    monkeypatch.setenv("RENPY_MCP_MOCK_LLM", "1")

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        websocket.send_json({"type": "user_message", "content": "中世纪王国，三位角色，一小时", "project_name": project_name})
        _drain_events(websocket, 1)
        websocket.send_json({"type": "user_message", "content": "整体氛围偏沉郁克制", "project_name": project_name})
        events = _drain_events(websocket, 3)

    draft_event = next(e for e in events if e["type"] == "message" and e.get("message_kind") == "blueprint_draft")
    assert draft_event["draft"]["genre"] == "历史剧 / 中世纪骑士故事"
    assert draft_event["draft"]["characters"][0]["name"] == "Mock主角小明"


def test_blueprint_draft_uses_english_for_clearly_english_input_with_mock_provider(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """Mock provider should switch blueprint draft content to English for clearly English input."""
    project_name = "bp_lang_en"
    _create_project(client, tmp_path, project_name)
    monkeypatch.setenv("RENPY_MCP_MOCK_LLM", "1")

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "start_blueprint_collection", "project_name": project_name})
        _drain_events(websocket, 1)
        websocket.send_json(
            {
                "type": "user_message",
                "content": "A medieval kingdom with three leads and about one hour of playtime.",
                "project_name": project_name,
            }
        )
        _drain_events(websocket, 1)
        websocket.send_json(
            {
                "type": "user_message",
                "content": "The tone should feel restrained, melancholic, and character-driven.",
                "project_name": project_name,
            }
        )
        events = _drain_events(websocket, 3)

    draft_event = next(e for e in events if e["type"] == "message" and e.get("message_kind") == "blueprint_draft")
    assert draft_event["draft"]["genre"] == "Historical Drama / Medieval Knight Story"
    assert draft_event["draft"]["characters"][0]["name"] == "Mock Hero Liam"


# ---------------------------------------------------------------------------
# Phase 5 Round 3: auto-build after blueprint confirmation
# ---------------------------------------------------------------------------


def test_preview_ready_state_survives_refresh_read_path(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """After auto-build success, GET /build/status must recover preview-ready state."""
    project_name = "bp_preview_refresh"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: _make_mock_smart_provider(title=project_name),
    )

    from renpy_mcp.services import build_manager as bm
    from renpy_mcp.models import BuildResult

    async def _mock_build(self, request):
        build_dir = tmp_path / f"{request.project_name}-dists" / f"{request.project_name}-web"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "index.html").write_text("<html>mock</html>", encoding="utf-8")
        return BuildResult(
            project_name=request.project_name,
            target=request.target,
            success=True,
            output_path=build_dir,
        )

    monkeypatch.setattr(bm.BuildManager, "build", _mock_build)

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

    # Simulate refresh: read build status via REST API
    resp = client.get(f"/api/projects/{project_name}/build/status")
    assert resp.status_code == 200
    status = resp.json()
    assert status["status"] == "success"
    assert status["previewable"] is True
    assert status["output_path"] is not None


def test_pipeline_failure_does_not_erase_prototype_artifacts(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """Build failure must not destroy already-generated prototype files."""
    project_name = "bp_proto_preserve"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: _make_mock_smart_provider(title=project_name),
    )

    from renpy_mcp.services import build_manager as bm
    from renpy_mcp.models import BuildResult

    async def _mock_build(self, request):
        return BuildResult(
            project_name=request.project_name,
            target=request.target,
            success=False,
            error="Simulated build failure",
        )

    monkeypatch.setattr(bm.BuildManager, "build", _mock_build)

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

    # Prototype artifacts must survive
    game_dir = tmp_path / project_name / "game"
    proto_files = [p for p in game_dir.glob("prototype*") if p.suffix == ".rpy"]
    assert len(proto_files) == 1, f"Expected prototype .rpy to survive build failure, got {list(game_dir.glob('prototype*'))}"

    # Main script wiring must survive
    script_path = game_dir / "script.rpy"
    assert script_path.exists()
    content = script_path.read_text(encoding="utf-8")
    assert "call prototype_ch1_start" in content

    # Index must survive
    index_path = tmp_path / project_name / "meta" / "index.json"
    assert index_path.exists()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert "scenes" in index
    proto_scenes = {k: v for k, v in index["scenes"].items() if isinstance(v, dict) and v.get("source") == "prototype"}
    assert len(proto_scenes) >= 1

    # Build status must reflect failure
    resp = client.get(f"/api/projects/{project_name}/build/status")
    assert resp.status_code == 200
    status = resp.json()
    assert status["status"] == "failed"


def test_auto_build_mock_output_path_matches_api_endpoint(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """Auto-build mock output path must match the mock path used by fastapi_app.py build endpoints."""
    project_name = "bp_mock_path"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: _make_mock_smart_provider(title=project_name),
    )

    # Force mock build path (no monkeypatch on BuildManager.build)
    monkeypatch.setenv("RENPY_MCP_MOCK_BUILD", "1")

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

    # Verify build status points to the same path shape as fastapi_app.py mock builds:
    # workspace/{project_name}-dists/{project_name}-web
    status_path = tmp_path / project_name / "logs" / "build-status.json"
    assert status_path.exists()
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status.get("status") == "success"
    output_path = status.get("output_path")
    assert output_path is not None
    expected_dir = tmp_path / f"{project_name}-dists" / f"{project_name}-web"
    assert Path(output_path).resolve() == expected_dir.resolve(), (
        f"Auto-build mock path mismatch: {output_path} != {expected_dir}"
    )
    assert (expected_dir / "index.html").exists()


def test_confirmation_triggers_auto_build_pipeline(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """After blueprint approval, prototype generation should auto-trigger build."""
    project_name = "bp_auto_build"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: _make_mock_smart_provider(title=project_name),
    )

    from renpy_mcp.services import build_manager as bm
    from renpy_mcp.models import BuildResult

    build_calls: list[str] = []

    async def _mock_build(self, request):
        build_calls.append(request.project_name)
        build_dir = tmp_path / f"{request.project_name}-dists" / f"{request.project_name}-web"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "index.html").write_text("<html>mock</html>", encoding="utf-8")
        return BuildResult(
            project_name=request.project_name,
            target=request.target,
            success=True,
            output_path=build_dir,
        )

    monkeypatch.setattr(bm.BuildManager, "build", _mock_build)

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

    assert project_name in build_calls, f"BuildManager.build should have been called for {project_name}, got {build_calls}"

    final_msg = events[-1].get("content", "")
    assert "预览" in final_msg or "preview" in final_msg.lower(), f"Expected preview-ready message, got: {final_msg}"

    # Build status should be persisted and previewable
    status_path = tmp_path / project_name / "logs" / "build-status.json"
    assert status_path.exists(), "Build status should be persisted after auto-build"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status.get("status") == "success"
    assert status.get("previewable") is True


def test_build_failure_distinguishes_from_prototype_failure(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """If prototype succeeds but build fails, the final message must mention build failure."""
    project_name = "bp_build_fail"
    _create_project(client, tmp_path, project_name)

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: _make_mock_smart_provider(title=project_name),
    )

    from renpy_mcp.services import build_manager as bm
    from renpy_mcp.models import BuildResult

    async def _mock_build(self, request):
        return BuildResult(
            project_name=request.project_name,
            target=request.target,
            success=False,
            error="Simulated build failure",
        )

    monkeypatch.setattr(bm.BuildManager, "build", _mock_build)

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

    final_msg = events[-1].get("content", "")
    assert "构建失败" in final_msg or "build failed" in final_msg.lower(), f"Expected build failure message, got: {final_msg}"

    # Prototype artifacts must survive build failure
    proto_file = tmp_path / project_name / "game" / "prototype_ch1_第一章.rpy"
    assert proto_file.exists(), "Prototype script should survive build failure"

    # Build status should reflect failure
    status_path = tmp_path / project_name / "logs" / "build-status.json"
    assert status_path.exists(), "Build status should be persisted after build failure"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status.get("status") == "failed"
