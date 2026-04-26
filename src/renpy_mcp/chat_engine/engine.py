"""ChatEngine: ReAct loop for LLM-driven MCP tool invocation."""

import asyncio
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from .adapter import ToolAdapter
from .confirmation import ConfirmationState
from .providers import BaseProvider, LLMResponse


class ChatEngine:
    """ReAct chat engine that turns natural language into MCP tool calls."""

    def __init__(
        self,
        mcp: FastMCP,
        provider: BaseProvider,
        system_prompt: str | None = None,
        max_react_iterations: int = 5,
        max_retries: int = 2,
    ) -> None:
        self.mcp = mcp
        self.provider = provider
        self.adapter = ToolAdapter(mcp)
        self.confirmation = ConfirmationState()
        self.max_react_iterations = max_react_iterations
        self.max_retries = max_retries
        self.system_prompt = system_prompt or (
            "You are an AI assistant for Ren'Py visual novel development. "
            "You have access to a set of tools that can create projects, generate scripts, "
            "create images, build games, and more. "
            "When the user asks you to perform an action, use the appropriate tool. "
            "If the user's request is unclear or unrelated, respond naturally without calling tools."
        )

    async def run_turn(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Run a single ReAct turn.

        Returns a dict with:
            - type: "success" | "error"
            - messages: list of conversation messages (including assistant and tool results)
            - final_text: str | None
            - tool_calls: list of executed tool calls
            - error: str | None
        """
        tools = (
            self.adapter.to_anthropic()
            if getattr(self.provider, "tool_format", "openai") == "anthropic"
            else self.adapter.to_openai()
        )

        executed_tools: list[dict[str, Any]] = []
        iteration = 0

        while iteration < self.max_react_iterations:
            iteration += 1
            response = await asyncio.to_thread(
                self.provider.chat,
                messages=messages,
                tools=tools if tools else None,
                system=self.system_prompt,
                max_tokens=2048,
            )

            # Append assistant response to message history
            assistant_content = self._response_to_content_blocks(response)
            messages.append({"role": "assistant", "content": assistant_content})

            if not response.tool_calls:
                # No tools requested — we're done
                return {
                    "type": "success",
                    "messages": messages,
                    "final_text": response.text,
                    "tool_calls": executed_tools,
                    "error": None,
                }

            # Execute requested tools with retry logic for parameter errors
            tool_results: list[dict[str, Any]] = []
            for call in response.tool_calls:
                # Check if this tool requires user confirmation
                if self.confirmation.should_confirm(call["name"]):
                    confirmation_id = f"conf_{len(executed_tools)}_{call['name']}"
                    # Execute the tool first so we have results to show
                    result = await self._execute_tool(call)
                    executed_tools.append(
                        {
                            "name": call["name"],
                            "arguments": call["arguments"],
                            "result": result.get("output"),
                            "success": result.get("success", False),
                        }
                    )
                    self.confirmation.request_confirmation(
                        confirmation_id=confirmation_id,
                        tool_name=call["name"],
                        arguments=call.get("arguments", {}),
                        tool_use_id=call.get("id"),
                        tool_result=result if result.get("success") else None,
                    )
                    # Pause ReAct loop — return pending confirmation to caller
                    return {
                        "type": "awaiting_confirmation",
                        "messages": messages,
                        "final_text": None,
                        "tool_calls": executed_tools,
                        "confirmation": {
                            "confirmation_id": confirmation_id,
                            "message": self.confirmation.pending.message if self.confirmation.pending else "",
                            "candidates": self.confirmation.pending.candidates if self.confirmation.pending else [],
                            "project_name": self.confirmation.pending.project_name if self.confirmation.pending else None,
                        },
                        "error": None,
                    }

                result = await self._execute_tool(call)
                tool_results.append(result)
                executed_tools.append(
                    {
                        "name": call["name"],
                        "arguments": call["arguments"],
                        "result": result.get("output"),
                        "success": result.get("success", False),
                    }
                )

            # Append tool results to message history
            messages.append({"role": "user", "content": tool_results})

        # Hit iteration limit
        return {
            "type": "error",
            "messages": messages,
            "final_text": None,
            "tool_calls": executed_tools,
            "error": "Reached maximum ReAct iterations without a final answer.",
        }

    def _response_to_content_blocks(self, response: LLMResponse) -> list[dict[str, Any]]:
        """Convert normalized LLMResponse back to content blocks for message history."""
        blocks: list[dict[str, Any]] = []
        for block in response.content_blocks:
            if block.get("type") == "text":
                blocks.append({"type": "text", "text": block.get("text", "")})
            elif block.get("type") == "tool_use":
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "input": block.get("input"),
                    }
                )
            elif block.get("type") == "function_call":
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "input": block.get("arguments", {}),
                    }
                )
        return blocks

    async def _execute_tool(self, call: dict[str, Any]) -> dict[str, Any]:
        """Execute a single tool call and return the result to the LLM.

        On failure, returns a structured error result with ``is_retryable=True``
        so the LLM can self-correct and retry with corrected parameters.
        This does NOT automatically re-invoke the tool — retry is delegated
        to the LLM ReAct loop.
        """
        tool_name = call["name"]
        arguments = call.get("arguments", {})
        tool_id = call.get("id", "")

        for attempt in range(self.max_retries + 1):
            try:
                output = await self.mcp.call_tool(tool_name, arguments)
                return {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": self._serialize_output(output),
                    "success": True,
                }
            except Exception as exc:
                error_msg = f"Error calling {tool_name}: {exc}"
                if attempt < self.max_retries:
                    return {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": f"{error_msg}\nPlease correct the parameters and try again.",
                        "success": False,
                        "is_retryable": True,
                    }
                return {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": error_msg,
                    "success": False,
                }

    def _serialize_output(self, output: Any) -> str:
        """Serialize tool output to a string for the LLM."""
        if isinstance(output, str):
            return output
        # FastMCP call_tool commonly returns a tuple of:
        #   ([TextContent(...)], {"result": "<raw tool string>"})
        # Prefer the structured "result" payload so downstream clients can
        # parse JSON tool outputs instead of receiving a Python repr.
        if isinstance(output, tuple) and len(output) >= 2:
            _, structured = output[0], output[1]
            if isinstance(structured, dict) and "result" in structured:
                return self._serialize_output(structured["result"])
            output = output[0]
        if isinstance(output, dict) and "result" in output and len(output) == 1:
            return self._serialize_output(output["result"])
        if hasattr(output, "model_dump"):
            return json.dumps(output.model_dump(mode="json"), ensure_ascii=False)
        # Handle MCP content blocks (list of TextContent/ImageContent)
        if isinstance(output, list):
            texts = []
            for item in output:
                if hasattr(item, "text"):
                    texts.append(item.text)
                elif hasattr(item, "model_dump"):
                    texts.append(json.dumps(item.model_dump(mode="json"), ensure_ascii=False))
                else:
                    texts.append(str(item))
            return "\n".join(texts)
        try:
            return json.dumps(output, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(output)
