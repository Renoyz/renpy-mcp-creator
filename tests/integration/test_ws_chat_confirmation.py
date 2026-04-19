"""Integration test for WebSocket confirmation flow."""

import json
from pathlib import Path
from unittest.mock import patch

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


def test_ws_chat_confirmation_approve(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Test a full confirmation-approved turn via WebSocket."""
    from renpy_mcp.chat_engine.providers import AnthropicProvider

    project_name = "ws_test"
    game_dir = tmp_path / project_name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    captured = {"second_messages": None}

    class FakeMessages:
        call_count = 0

        def create(self, **kwargs):
            FakeMessages.call_count += 1
            if FakeMessages.call_count == 2:
                captured["second_messages"] = kwargs.get("messages")
            msg = type(
                "M",
                (),
                {
                    "content": [],
                    "stop_reason": "tool_use" if FakeMessages.call_count == 1 else "end_turn",
                    "usage": type("U", (), {"input_tokens": 5, "output_tokens": 5})(),
                },
            )()
            if FakeMessages.call_count == 1:
                msg.content = [
                    type(
                        "B",
                        (),
                        {
                            "type": "tool_use",
                            "id": "call_bg_1",
                            "name": "generate_background",
                            "input": {
                                "project_name": project_name,
                                "description": "a test",
                            },
                        },
                    )()
                ]
            else:
                msg.content = [type("B", (), {"type": "text", "text": "Background saved."})()]
            return msg

    class FakeClient:
        messages = FakeMessages()

    provider = AnthropicProvider(api_key="fake")
    provider.client = FakeClient()

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: provider,
    )

    fake_result = type(
        "R",
        (),
        {
            "success": True,
            "prompt": "a test",
            "image_type": "background",
            "files": [tmp_path / "assets" / "background" / "bg.png"],
            "primary_file": tmp_path / "assets" / "background" / "bg.png",
            "error": None,
        },
    )()
    fake_result.model_dump = lambda mode="json": {
        "success": True,
        "prompt": "a test",
        "image_type": "background",
        "files": [str(tmp_path / "assets" / "background" / "bg.png")],
        "primary_file": str(tmp_path / "assets" / "background" / "bg.png"),
        "error": None,
    }

    with patch("renpy_mcp.tools.assets.image_service.is_available", return_value=True), patch(
        "renpy_mcp.tools.assets.image_service.generate_image",
        return_value=fake_result,
    ), patch(
        "renpy_mcp.tools.assets._project_manager.ensure_project_dir",
        return_value=tmp_path,
    ):
        with client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json({"type": "user_message", "content": "generate a background", "project_name": project_name})

            # Step 1: awaiting_confirmation
            data = websocket.receive_json()
            assert data["type"] == "awaiting_confirmation"
            confirmation_id = data["confirmation_id"]
            assert confirmation_id.startswith("conf_0_generate_background")
            assert data["project_name"] == project_name

            # Approve
            websocket.send_json(
                {
                    "type": "confirmation_response",
                    "confirmation_id": confirmation_id,
                    "approved": True,
                    "project_name": project_name,
                }
            )

            # Step 2: tool_start (replayed from history)
            data = websocket.receive_json()
            assert data["type"] == "tool_start"
            assert data["tool_name"] == "generate_background"

            # Step 3: tool_result (replayed original tool result)
            data = websocket.receive_json()
            assert data["type"] == "tool_result"
            assert data["result"]["success"] is True

            # Step 4: assistant_delta (final text)
            data = websocket.receive_json()
            assert data["type"] == "assistant_delta"
            assert data["delta"] == "Background saved."

    tool_result_blocks = next(
        msg["content"]
        for msg in captured["second_messages"]
        if msg.get("role") == "user" and isinstance(msg.get("content"), list)
    )
    assert tool_result_blocks[0]["tool_use_id"] == "call_bg_1"


def test_ws_chat_confirmation_keeps_original_project(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Approval should bind to the project active when confirmation was created, not the current UI selection."""
    from renpy_mcp.chat_engine.providers import AnthropicProvider
    from renpy_mcp.config import _current_project_path

    for name in ("proj_a", "proj_b"):
        game_dir = tmp_path / name / "game"
        game_dir.mkdir(parents=True)
        (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    class FakeMessages:
        call_count = 0

        def create(self, **kwargs):
            self.call_count += 1
            msg = type(
                "M",
                (),
                {
                    "content": [],
                    "stop_reason": "tool_use" if self.call_count == 1 else "end_turn",
                    "usage": type("U", (), {"input_tokens": 5, "output_tokens": 5})(),
                },
            )()
            if self.call_count == 1:
                msg.content = [
                    type(
                        "B",
                        (),
                        {"type": "tool_use", "id": "call_1", "name": "generate_background", "input": {}},
                    )()
                ]
            else:
                # Return the currently bound project path so we can verify it
                path = _current_project_path.get()
                msg.content = [type("B", (), {"type": "text", "text": str(path) if path else "NO_PROJECT"})()]
            return msg

    class FakeClient:
        messages = FakeMessages()

    provider = AnthropicProvider(api_key="fake")
    provider.client = FakeClient()

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: provider,
    )

    # Start with project A selected
    r = client.post("/api/projects/select", json={"name": "proj_a"})
    assert r.status_code == 200

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "generate a background", "project_name": "proj_a"})

        data = websocket.receive_json()
        assert data["type"] == "awaiting_confirmation"
        confirmation_id = data["confirmation_id"]

        # Switch session to project B before approving
        r = client.post("/api/projects/select", json={"name": "proj_b"})
        assert r.status_code == 200

        # Send confirmation response with project_b in payload (simulating stale frontend state)
        websocket.send_json(
            {
                "type": "confirmation_response",
                "confirmation_id": confirmation_id,
                "approved": True,
                "project_name": "proj_b",
            }
        )

        # The second run_turn should still execute under proj_a because pending.project_name is proj_a
        data = websocket.receive_json()
        assert data["type"] == "tool_start"

        data = websocket.receive_json()
        assert data["type"] == "tool_result"

        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert "proj_a" in data["delta"]


def test_tool_confirmation_writes_runtime_session(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Normal tool awaiting_confirmation should persist runtime session with active_workflow='tool'."""
    from renpy_mcp.chat_engine.providers import AnthropicProvider

    project_name = "ws_test_tool_session"
    game_dir = tmp_path / project_name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    class FakeMessages:
        call_count = 0

        def create(self, **kwargs):
            FakeMessages.call_count += 1
            msg = type(
                "M",
                (),
                {
                    "content": [],
                    "stop_reason": "tool_use" if FakeMessages.call_count == 1 else "end_turn",
                    "usage": type("U", (), {"input_tokens": 5, "output_tokens": 5})(),
                },
            )()
            if FakeMessages.call_count == 1:
                msg.content = [
                    type(
                        "B",
                        (),
                        {
                            "type": "tool_use",
                            "id": "call_bg_1",
                            "name": "generate_background",
                            "input": {"project_name": project_name, "description": "a test"},
                        },
                    )()
                ]
            else:
                msg.content = [type("B", (), {"type": "text", "text": "Background saved."})()]
            return msg

    class FakeClient:
        messages = FakeMessages()

    provider = AnthropicProvider(api_key="fake")
    provider.client = FakeClient()

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: provider,
    )

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "generate a background", "project_name": project_name})

        data = websocket.receive_json()
        assert data["type"] == "awaiting_confirmation"
        assert data["confirmation_id"].startswith("conf_0_generate_background")

    # After WS disconnect, session should still be persisted
    session_path = tmp_path / project_name / "meta" / "blueprint_session.json"
    assert session_path.exists(), "Runtime session should be written after awaiting_confirmation"
    session = json.loads(session_path.read_text(encoding="utf-8"))
    assert session["active_workflow"] == "tool"
    assert session["pipeline_stage"] == "awaiting_confirmation"
    assert session["awaiting_confirmation"] is True
    assert session["confirmation_id"].startswith("conf_0_generate_background")
    assert session["confirmation_message"] == "已生成背景图，请确认是否保存。"
    assert session["tool_name"] == "generate_background"
    assert session.get("latest_progress") == {"step": "等待用户确认: generate_background", "percent": 0}


def test_tool_confirmation_response_clears_session(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """After approving/rejecting a normal tool confirmation, runtime session should be cleared."""
    from renpy_mcp.chat_engine.providers import AnthropicProvider

    project_name = "ws_test_tool_clear"
    game_dir = tmp_path / project_name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    class FakeMessages:
        call_count = 0

        def create(self, **kwargs):
            FakeMessages.call_count += 1
            msg = type(
                "M",
                (),
                {
                    "content": [],
                    "stop_reason": "tool_use" if FakeMessages.call_count == 1 else "end_turn",
                    "usage": type("U", (), {"input_tokens": 5, "output_tokens": 5})(),
                },
            )()
            if FakeMessages.call_count == 1:
                msg.content = [
                    type(
                        "B",
                        (),
                        {
                            "type": "tool_use",
                            "id": "call_bg_1",
                            "name": "generate_background",
                            "input": {"project_name": project_name, "description": "a test"},
                        },
                    )()
                ]
            else:
                msg.content = [type("B", (), {"type": "text", "text": "Background saved."})()]
            return msg

    class FakeClient:
        messages = FakeMessages()

    provider = AnthropicProvider(api_key="fake")
    provider.client = FakeClient()

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: provider,
    )

    fake_result = type(
        "R",
        (),
        {
            "success": True,
            "prompt": "a test",
            "image_type": "background",
            "files": [tmp_path / "assets" / "background" / "bg.png"],
            "primary_file": tmp_path / "assets" / "background" / "bg.png",
            "error": None,
        },
    )()
    fake_result.model_dump = lambda mode="json": {
        "success": True,
        "prompt": "a test",
        "image_type": "background",
        "files": [str(tmp_path / "assets" / "background" / "bg.png")],
        "primary_file": str(tmp_path / "assets" / "background" / "bg.png"),
        "error": None,
    }

    with patch("renpy_mcp.tools.assets.image_service.is_available", return_value=True), patch(
        "renpy_mcp.tools.assets.image_service.generate_image",
        return_value=fake_result,
    ), patch(
        "renpy_mcp.tools.assets._project_manager.ensure_project_dir",
        return_value=tmp_path,
    ):
        with client.websocket_connect("/ws/chat") as websocket:
            websocket.send_json({"type": "user_message", "content": "generate a background", "project_name": project_name})

            data = websocket.receive_json()
            assert data["type"] == "awaiting_confirmation"
            confirmation_id = data["confirmation_id"]

            # Session should exist before response
            session_path = tmp_path / project_name / "meta" / "blueprint_session.json"
            assert session_path.exists()

            # Reject the confirmation
            websocket.send_json(
                {
                    "type": "confirmation_response",
                    "confirmation_id": confirmation_id,
                    "approved": False,
                    "project_name": project_name,
                }
            )

            # Consume remaining event (assistant_delta after rejection)
            websocket.receive_json()

    # After rejection, session should be cleared
    assert not session_path.exists(), "Runtime session should be cleared after confirmation response"


def test_runtime_session_api_returns_tool_state(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """GET /api/projects/{name}/blueprint-session should return tool workflow runtime state."""
    from renpy_mcp.chat_engine.providers import AnthropicProvider

    project_name = "ws_test_tool_api"
    game_dir = tmp_path / project_name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    class FakeMessages:
        call_count = 0

        def create(self, **kwargs):
            FakeMessages.call_count += 1
            msg = type(
                "M",
                (),
                {
                    "content": [],
                    "stop_reason": "tool_use" if FakeMessages.call_count == 1 else "end_turn",
                    "usage": type("U", (), {"input_tokens": 5, "output_tokens": 5})(),
                },
            )()
            if FakeMessages.call_count == 1:
                msg.content = [
                    type(
                        "B",
                        (),
                        {
                            "type": "tool_use",
                            "id": "call_bg_1",
                            "name": "generate_background",
                            "input": {"project_name": project_name, "description": "a test"},
                        },
                    )()
                ]
            else:
                msg.content = [type("B", (), {"type": "text", "text": "Done."})()]
            return msg

    class FakeClient:
        messages = FakeMessages()

    provider = AnthropicProvider(api_key="fake")
    provider.client = FakeClient()

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: provider,
    )

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "generate a background", "project_name": project_name})

        data = websocket.receive_json()
        assert data["type"] == "awaiting_confirmation"

    resp = client.get(f"/api/projects/{project_name}/blueprint-session")
    assert resp.status_code == 200
    session = resp.json()
    assert session["active_workflow"] == "tool"
    assert session["pipeline_stage"] == "awaiting_confirmation"
    assert session["awaiting_confirmation"] is True
    assert "confirmation_id" in session
    assert "confirmation_message" in session
    assert session["tool_name"] == "generate_background"
    assert session.get("latest_progress") == {"step": "等待用户确认: generate_background", "percent": 0}


def test_tool_start_updates_runtime_session(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Inline tool_start should persist runtime session with latest_progress."""
    from renpy_mcp.chat_engine.providers import AnthropicProvider
    from renpy_mcp.web.chat_ws import _save_runtime_session

    project_name = "ws_test_tool_start"
    game_dir = tmp_path / project_name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    class FakeMessages:
        call_count = 0

        def create(self, **kwargs):
            self.call_count += 1
            msg = type(
                "M",
                (),
                {
                    "content": [],
                    "stop_reason": "tool_use" if self.call_count == 1 else "end_turn",
                    "usage": type("U", (), {"input_tokens": 5, "output_tokens": 5})(),
                },
            )()
            if self.call_count == 1:
                msg.content = [
                    type(
                        "B",
                        (),
                        {"type": "tool_use", "id": "call_1", "name": "list_projects", "input": {}},
                    )()
                ]
            else:
                msg.content = [type("B", (), {"type": "text", "text": "Done"})()]
            return msg

    class FakeClient:
        messages = FakeMessages()

    provider = AnthropicProvider(api_key="fake")
    provider.client = FakeClient()

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: provider,
    )

    captured_states: list[dict] = []
    original_save = _save_runtime_session

    def _capture_save(project_name_arg: str, state: dict) -> None:
        if project_name_arg == project_name:
            captured_states.append(state)
        original_save(project_name_arg, state)

    monkeypatch.setattr("renpy_mcp.web.chat_ws._save_runtime_session", _capture_save)

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "list projects", "project_name": project_name})

        data = websocket.receive_json()
        assert data["type"] == "tool_start"

        # Verify that _save_runtime_session was called with progress state
        assert len(captured_states) >= 1, "Runtime session should be saved after tool_start"
        session = captured_states[-1]
        assert session["active_workflow"] == "tool"
        assert session["pipeline_stage"] == "tool_running"
        assert session["awaiting_confirmation"] is False
        assert session.get("latest_progress") == {"step": "正在调用 list_projects...", "percent": 0}
        assert session["tool_name"] == "list_projects"

        data = websocket.receive_json()
        assert data["type"] == "tool_result"

        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"


def test_tool_result_clears_runtime_session(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """After tool_result is streamed, runtime session should be cleared."""
    from renpy_mcp.chat_engine.providers import AnthropicProvider

    project_name = "ws_test_tool_clear_inline"
    game_dir = tmp_path / project_name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    class FakeMessages:
        call_count = 0

        def create(self, **kwargs):
            self.call_count += 1
            msg = type(
                "M",
                (),
                {
                    "content": [],
                    "stop_reason": "tool_use" if self.call_count == 1 else "end_turn",
                    "usage": type("U", (), {"input_tokens": 5, "output_tokens": 5})(),
                },
            )()
            if self.call_count == 1:
                msg.content = [
                    type(
                        "B",
                        (),
                        {"type": "tool_use", "id": "call_1", "name": "list_projects", "input": {}},
                    )()
                ]
            else:
                msg.content = [type("B", (), {"type": "text", "text": "Done"})()]
            return msg

    class FakeClient:
        messages = FakeMessages()

    provider = AnthropicProvider(api_key="fake")
    provider.client = FakeClient()

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: provider,
    )

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "list projects", "project_name": project_name})

        data = websocket.receive_json()
        assert data["type"] == "tool_start"

        data = websocket.receive_json()
        assert data["type"] == "tool_result"

        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"

    # After the full turn completes, session should be cleared
    session_path = tmp_path / project_name / "meta" / "blueprint_session.json"
    assert not session_path.exists(), "Runtime session should be cleared after tool_result"


def test_tool_running_session_api_returns_progress_state(client: TestClient, tmp_path: Path) -> None:
    """GET /blueprint-session should return tool_running state with latest_progress."""
    project_name = "ws_test_tool_running_api"
    game_dir = tmp_path / project_name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    # Inject a tool-running runtime session directly
    session_path = tmp_path / project_name / "meta" / "blueprint_session.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps(
            {
                "active_workflow": "tool",
                "pipeline_stage": "tool_running",
                "awaiting_confirmation": False,
                "latest_progress": {"step": "正在调用 generate_background...", "percent": 0},
                "tool_name": "generate_background",
                "updated_at": "2024-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    resp = client.get(f"/api/projects/{project_name}/blueprint-session")
    assert resp.status_code == 200
    session = resp.json()
    assert session["active_workflow"] == "tool"
    assert session["pipeline_stage"] == "tool_running"
    assert session["awaiting_confirmation"] is False
    assert session.get("latest_progress") == {"step": "正在调用 generate_background...", "percent": 0}
    assert session["tool_name"] == "generate_background"
    # Must NOT be misinterpreted as blueprint state
    assert "confirmation_id" not in session
    assert "draft" not in session
