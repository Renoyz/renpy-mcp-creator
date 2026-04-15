"""Tests for chat_engine ToolAdapter and providers."""

from typing import Optional

import pytest
from mcp.server.fastmcp import FastMCP

from renpy_mcp.chat_engine import AnthropicProvider, OpenAICompatibleProvider, ToolAdapter


@pytest.fixture
def mock_mcp() -> FastMCP:
    mcp = FastMCP("test-mcp")

    @mcp.tool()
    async def create_project(name: str, template: Optional[str] = None) -> str:
        """Create a new project directory.

        Args:
            name: Project name (used as directory name).
            template: Template name to use (default: basic).
        """
        return f"Created {name}"

    @mcp.tool()
    async def delete_project(name: str) -> str:
        """Delete a project directory."""
        return f"Deleted {name}"

    return mcp


def test_tool_adapter_lists_tools(mock_mcp: FastMCP) -> None:
    adapter = ToolAdapter(mock_mcp)
    tools = adapter.list_mcp_tools()
    names = {t.name for t in tools}
    assert names == {"create_project", "delete_project"}


def test_tool_adapter_to_anthropic(mock_mcp: FastMCP) -> None:
    adapter = ToolAdapter(mock_mcp)
    tools = adapter.to_anthropic()
    assert len(tools) == 2

    by_name = {t["name"]: t for t in tools}
    create = by_name["create_project"]
    assert create["name"] == "create_project"
    assert "Create a new project directory" in create["description"]
    assert create["input_schema"]["type"] == "object"
    assert "name" in create["input_schema"]["properties"]
    assert "template" in create["input_schema"]["properties"]


def test_tool_adapter_to_openai(mock_mcp: FastMCP) -> None:
    adapter = ToolAdapter(mock_mcp)
    tools = adapter.to_openai()
    assert len(tools) == 2

    by_name = {t["function"]["name"]: t for t in tools}
    create = by_name["create_project"]
    assert create["type"] == "function"
    assert create["function"]["name"] == "create_project"
    assert "Create a new project directory" in create["function"]["description"]
    assert create["function"]["parameters"]["type"] == "object"


def test_anthropic_provider_chat_with_tools(monkeypatch) -> None:
    """Mock Anthropic client to verify message formatting."""

    class FakeMessage:
        def __init__(self):
            self.content = []
            self.stop_reason = "end_turn"
            self.usage = type("U", (), {"input_tokens": 10, "output_tokens": 5})()

    class FakeMessages:
        def create(self, **kwargs):
            assert kwargs["model"] == "claude-test"
            assert len(kwargs["tools"]) == 1
            assert kwargs["system"] == "sys"
            msg = FakeMessage()
            msg.content = [type("B", (), {"type": "text", "text": "hello"})()]
            return msg

    class FakeClient:
        messages = FakeMessages()

    provider = AnthropicProvider(api_key="fake", default_model="claude-test")
    provider.client = FakeClient()

    resp = provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"name": "test", "description": "d", "input_schema": {"type": "object"}}],
        system="sys",
    )
    assert resp.text == "hello"
    assert resp.stop_reason == "end_turn"


def test_openai_provider_chat_with_tools(monkeypatch) -> None:
    """Mock OpenAI client to verify message formatting."""

    class FakeChoice:
        def __init__(self):
            self.finish_reason = "stop"
            self.message = type(
                "M",
                (),
                {
                    "content": "hi there",
                    "tool_calls": None,
                },
            )()

    class FakeUsage:
        prompt_tokens = 10
        completion_tokens = 5
        total_tokens = 15

    class FakeResponse:
        def __init__(self):
            self.choices = [FakeChoice()]
            self.usage = FakeUsage()

    class FakeCompletions:
        def create(self, **kwargs):
            assert kwargs["model"] == "gpt-test"
            assert kwargs["messages"][0]["role"] == "system"
            assert kwargs["messages"][0]["content"] == "sys"
            return FakeResponse()

    class FakeClient:
        chat = type("C", (), {"completions": FakeCompletions()})()

    provider = OpenAICompatibleProvider(api_key="fake", default_model="gpt-test")
    provider.client = FakeClient()

    resp = provider.chat(
        messages=[{"role": "user", "content": "hello"}],
        system="sys",
    )
    assert resp.text == "hi there"
    assert resp.stop_reason == "stop"
