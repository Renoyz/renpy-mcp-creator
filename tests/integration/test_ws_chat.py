"""Integration tests for /ws/chat WebSocket endpoint."""

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


def _make_fake_engine():
    class FakeEngine:
        def __init__(self, mcp=None, provider=None):
            pass

        async def run_turn(self, messages):
            from renpy_mcp.config import _current_project_path

            path = _current_project_path.get()
            return {
                "messages": [
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": str(path) if path else "NO_PROJECT"}],
                    }
                ],
            }

    return FakeEngine


def test_ws_chat_uses_session_project(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """WebSocket should pick up the current project from session at connect time."""
    project_name = "session_proj"
    game_dir = tmp_path / project_name / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: type("P", (), {"complete": lambda **kw: []})(),
    )
    monkeypatch.setattr("renpy_mcp.web.chat_ws.ChatEngine", _make_fake_engine())

    # Select project via HTTP so the session cookie is set
    r = client.post("/api/projects/select", json={"name": project_name})
    assert r.status_code == 200

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "hi"})
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert project_name in data["delta"]


def test_ws_chat_switches_project_after_reconnect(
    monkeypatch, client: TestClient, tmp_path: Path
) -> None:
    """After switching the session project, a new WebSocket connection must use the new project."""
    for name in ("proj_a", "proj_b"):
        game_dir = tmp_path / name / "game"
        game_dir.mkdir(parents=True)
        (game_dir / "script.rpy").write_text('label start:\n    "Hello."\n    return\n', encoding="utf-8")

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._get_provider",
        lambda: type("P", (), {"complete": lambda **kw: []})(),
    )
    monkeypatch.setattr("renpy_mcp.web.chat_ws.ChatEngine", _make_fake_engine())

    # Select project A and chat
    r = client.post("/api/projects/select", json={"name": "proj_a"})
    assert r.status_code == 200

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "hi"})
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert "proj_a" in data["delta"]

    # Switch to project B and open a new WebSocket
    r = client.post("/api/projects/select", json={"name": "proj_b"})
    assert r.status_code == 200

    with client.websocket_connect("/ws/chat") as websocket:
        websocket.send_json({"type": "user_message", "content": "hi"})
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert "proj_b" in data["delta"]


def test_ws_chat_mock_provider(monkeypatch, client: TestClient) -> None:
    """Test WebSocket chat with a mock provider to avoid real LLM calls."""
    from renpy_mcp.chat_engine.providers import AnthropicProvider

    class FakeMessages:
        def create(self, **kwargs):
            msg = type("M", (), {"content": [], "stop_reason": "end_turn", "usage": type("U", (), {"input_tokens": 5, "output_tokens": 5})()})()
            msg.content = [type("B", (), {"type": "text", "text": "Hello from mock"})()]
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
        websocket.send_json({"type": "user_message", "content": "hi"})
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert "Hello from mock" in data["delta"]


def test_ws_chat_no_provider(client: TestClient) -> None:
    """Test that WS closes immediately when no provider is configured."""
    import renpy_mcp.web.chat_ws as chat_ws

    original = chat_ws._get_provider
    chat_ws._get_provider = lambda: None
    try:
        with client.websocket_connect("/ws/chat") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "error"
    finally:
        chat_ws._get_provider = original


def test_ws_chat_tool_call(monkeypatch, client: TestClient) -> None:
    """Test a full tool-call turn via WebSocket."""
    from renpy_mcp.chat_engine.providers import AnthropicProvider

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
        websocket.send_json({"type": "user_message", "content": "list projects"})

        # First response: tool_start
        data = websocket.receive_json()
        assert data["type"] == "tool_start"
        assert data["tool_name"] == "list_projects"

        # Second response: tool_result
        data = websocket.receive_json()
        assert data["type"] == "tool_result"
        assert data["result"]["success"] is True

        # Third response: assistant text
        data = websocket.receive_json()
        assert data["type"] == "assistant_delta"
        assert data["delta"] == "Done"
