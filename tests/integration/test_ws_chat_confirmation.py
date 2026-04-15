"""Integration test for WebSocket confirmation flow."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from renpy_mcp.web.fastapi_app import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_ws_chat_confirmation_approve(monkeypatch, client: TestClient, tmp_path: Path) -> None:
    """Test a full confirmation-approved turn via WebSocket."""
    from renpy_mcp.chat_engine.providers import AnthropicProvider

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
                            "input": {
                                "project_name": "ws_test",
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
            websocket.send_json({"type": "user_message", "content": "generate a background"})

            # Step 1: awaiting_confirmation
            data = websocket.receive_json()
            assert data["type"] == "awaiting_confirmation"
            confirmation_id = data["confirmation_id"]
            assert confirmation_id.startswith("conf_0_generate_background")

            # Approve
            websocket.send_json(
                {
                    "type": "confirmation_response",
                    "confirmation_id": confirmation_id,
                    "approved": True,
                }
            )

            # Step 2: tool_start (replayed from history)
            data = websocket.receive_json()
            assert data["type"] == "tool_start"
            assert data["tool_name"] == "generate_background"

            # Step 3: tool_result (synthetic confirmation result)
            data = websocket.receive_json()
            assert data["type"] == "tool_result"
            assert data["result"]["success"] is True

            # Step 4: assistant_delta (final text)
            data = websocket.receive_json()
            assert data["type"] == "assistant_delta"
            assert data["delta"] == "Background saved."
