"""Tests for ConfirmationState and ChatEngine confirmation flow."""

from typing import Optional

import pytest
from mcp.server.fastmcp import FastMCP

from renpy_mcp.chat_engine import ChatEngine, ConfirmationState
from renpy_mcp.chat_engine.providers import BaseProvider, LLMResponse


class FakeProvider(BaseProvider):
    """Mock provider that returns pre-programmed responses."""

    tool_format = "anthropic"

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = responses
        self.call_index = 0

    def chat(
        self,
        messages,
        tools=None,
        system=None,
        model=None,
        max_tokens=1024,
        temperature=None,
    ) -> LLMResponse:
        resp = self.responses[self.call_index]
        self.call_index += 1
        return resp


@pytest.fixture
def mock_mcp() -> FastMCP:
    mcp = FastMCP("test-mcp")

    @mcp.tool()
    async def generate_character(character_name: str, description: Optional[str] = None) -> dict:
        """Generate a character."""
        return {
            "success": True,
            "files": [f"{character_name}_neutral.png"],
            "relative_files": [f"{character_name}_neutral.png"],
        }

    @mcp.tool()
    async def create_project(name: str) -> dict:
        """Create a project."""
        return {"success": True, "name": name}

    return mcp


@pytest.mark.asyncio
async def test_chat_engine_pauses_for_confirmation(mock_mcp: FastMCP) -> None:
    provider = FakeProvider(
        responses=[
            LLMResponse(
                content_blocks=[
                    {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "generate_character",
                        "input": {"character_name": "Amy"},
                    }
                ],
                stop_reason="tool_use",
            )
        ]
    )
    engine = ChatEngine(mock_mcp, provider)
    result = await engine.run_turn(messages=[{"role": "user", "content": "generate Amy"}])

    assert result["type"] == "awaiting_confirmation"
    assert engine.confirmation.is_waiting is True
    assert result["confirmation"]["confirmation_id"].startswith("conf_")
    assert "Amy" in result["confirmation"]["message"]
    assert len(result["confirmation"]["candidates"]) == 1


@pytest.mark.asyncio
async def test_chat_engine_skips_confirmation_for_low_impact(mock_mcp: FastMCP) -> None:
    provider = FakeProvider(
        responses=[
            LLMResponse(
                content_blocks=[
                    {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "create_project",
                        "input": {"name": "test_vn"},
                    }
                ],
                stop_reason="tool_use",
            ),
            LLMResponse(
                content_blocks=[{"type": "text", "text": "Done"}],
                stop_reason="end_turn",
            ),
        ]
    )
    engine = ChatEngine(mock_mcp, provider)
    result = await engine.run_turn(messages=[{"role": "user", "content": "create project"}])

    assert result["type"] == "success"
    assert engine.confirmation.is_waiting is False
    assert result["tool_calls"][0]["name"] == "create_project"


def test_confirmation_state_resolve() -> None:
    state = ConfirmationState()
    state.request_confirmation(
        confirmation_id="c1",
        tool_name="delete_project",
        arguments={"name": "old_vn"},
        tool_result=None,
    )
    assert state.is_waiting is True

    pending = state.resolve(approved=True)
    assert state.is_waiting is False
    assert pending.tool_name == "delete_project"
