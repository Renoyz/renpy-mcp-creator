"""ToolAdapter: converts MCP tools to LLM provider formats."""

from typing import Any

from mcp.server.fastmcp import FastMCP


class ToolAdapter:
    """Adapts FastMCP registered tools to Anthropic / OpenAI tool schemas."""

    def __init__(self, mcp: FastMCP) -> None:
        self.mcp = mcp

    def list_mcp_tools(self) -> list[Any]:
        """Return internal Tool objects from FastMCP."""
        return self.mcp._tool_manager.list_tools()

    def to_anthropic(self) -> list[dict[str, Any]]:
        """Convert all registered MCP tools to Anthropic tool format.

        Anthropic format:
        [
            {
                "name": "create_project",
                "description": "Create a new project...",
                "input_schema": {"type": "object", "properties": {...}, "required": [...]}
            }
        ]
        """
        tools: list[dict[str, Any]] = []
        for tool in self.list_mcp_tools():
            schema = tool.parameters or {"type": "object", "properties": {}}
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description or f"Call the {tool.name} tool.",
                    "input_schema": schema,
                }
            )
        return tools

    def to_openai(self) -> list[dict[str, Any]]:
        """Convert all registered MCP tools to OpenAI function-calling format.

        OpenAI format:
        [
            {
                "type": "function",
                "function": {
                    "name": "create_project",
                    "description": "Create a new project...",
                    "parameters": {"type": "object", "properties": {...}, "required": [...]}
                }
            }
        ]
        """
        tools: list[dict[str, Any]] = []
        for tool in self.list_mcp_tools():
            schema = tool.parameters or {"type": "object", "properties": {}}
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or f"Call the {tool.name} tool.",
                        "parameters": schema,
                    },
                }
            )
        return tools
