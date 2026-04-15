"""Integration tests for /ws/chat WebSocket endpoint."""

import pytest
from fastapi.testclient import TestClient

from renpy_mcp.web.fastapi_app import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_ws_chat_mock_provider(monkeypatch, client: TestClient) -> None:
    """Test WebSocket chat with a mock provider to avoid real LLM calls."""
    from renpy_mcp.chat_engine.providers import AnthropicProvider, LLMResponse

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
    from renpy_mcp.chat_engine.providers import AnthropicProvider, LLMResponse

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
