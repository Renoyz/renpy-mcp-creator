"""Tests for ChatEngine ReAct loop and self-correction."""

from typing import Optional

import pytest
from mcp.server.fastmcp import FastMCP

from renpy_mcp.chat_engine import ChatEngine
from renpy_mcp.chat_engine.providers import BaseProvider, LLMResponse


class FakeProvider(BaseProvider):
    """Mock provider that returns pre-programmed responses."""

    tool_format = "anthropic"

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = responses
        self.call_index = 0
        self.last_messages: list[dict] = []
        self.last_tools: list[dict] | None = None

    def chat(
        self,
        messages,
        tools=None,
        system=None,
        model=None,
        max_tokens=1024,
        temperature=None,
    ) -> LLMResponse:
        self.last_messages = messages
        self.last_tools = tools
        resp = self.responses[self.call_index]
        self.call_index += 1
        return resp


@pytest.fixture
def mock_mcp() -> FastMCP:
    mcp = FastMCP("test-mcp")

    @mcp.tool()
    async def create_project(name: str, template: Optional[str] = None) -> dict:
        """Create a project."""
        return {"success": True, "name": name, "template": template or "basic"}

    @mcp.tool()
    async def fail_always() -> dict:
        """Always fails."""
        raise ValueError("intentional failure")

    return mcp


@pytest.mark.asyncio
async def test_chat_engine_end_turn_no_tools(mock_mcp: FastMCP) -> None:
    provider = FakeProvider(
        responses=[
            LLMResponse(
                content_blocks=[{"type": "text", "text": "Hello there"}],
                stop_reason="end_turn",
            )
        ]
    )
    engine = ChatEngine(mock_mcp, provider)
    result = await engine.run_turn(messages=[{"role": "user", "content": "hi"}])

    assert result["type"] == "success"
    assert result["final_text"] == "Hello there"
    assert result["tool_calls"] == []
    assert len(result["messages"]) == 2  # user + assistant


@pytest.mark.asyncio
async def test_chat_engine_single_tool_call(mock_mcp: FastMCP) -> None:
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
                content_blocks=[{"type": "text", "text": "Created test_vn"}],
                stop_reason="end_turn",
            ),
        ]
    )
    engine = ChatEngine(mock_mcp, provider)
    result = await engine.run_turn(messages=[{"role": "user", "content": "create project"}])

    assert result["type"] == "success"
    assert result["final_text"] == "Created test_vn"
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["name"] == "create_project"
    assert result["tool_calls"][0]["success"] is True
    # messages: user, assistant(tool), user(tool_result), assistant(text)
    assert len(result["messages"]) == 4


@pytest.mark.asyncio
async def test_chat_engine_tool_error_then_retry(mock_mcp: FastMCP) -> None:
    provider = FakeProvider(
        responses=[
            LLMResponse(
                content_blocks=[
                    {
                        "type": "tool_use",
                        "id": "call_1",
                        "name": "fail_always",
                        "input": {},
                    }
                ],
                stop_reason="tool_use",
            ),
            LLMResponse(
                content_blocks=[{"type": "text", "text": "Sorry, that failed."}],
                stop_reason="end_turn",
            ),
        ]
    )
    engine = ChatEngine(mock_mcp, provider, max_retries=1)
    result = await engine.run_turn(messages=[{"role": "user", "content": "fail"}])

    assert result["type"] == "success"
    assert result["final_text"] == "Sorry, that failed."
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["success"] is False


@pytest.mark.asyncio
async def test_chat_engine_respects_max_iterations(mock_mcp: FastMCP) -> None:
    # Provider always returns a tool call, never end_turn
    provider = FakeProvider(
        responses=[
            LLMResponse(
                content_blocks=[
                    {
                        "type": "tool_use",
                        "id": f"call_{i}",
                        "name": "create_project",
                        "input": {"name": f"proj_{i}"},
                    }
                ],
                stop_reason="tool_use",
            )
            for i in range(10)
        ]
    )
    engine = ChatEngine(mock_mcp, provider, max_react_iterations=3)
    result = await engine.run_turn(messages=[{"role": "user", "content": "loop"}])

    assert result["type"] == "error"
    assert "maximum ReAct iterations" in result["error"]
    assert len(result["tool_calls"]) == 3
