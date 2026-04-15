"""WebSocket endpoint for /ws/chat — bridges Dashboard Chat Drawer to ChatEngine."""

import json
import os
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..chat_engine import AnthropicProvider, ChatEngine, OpenAICompatibleProvider
from ..config import get_settings, _current_project_path, resolve_project_dir
from ..server import mcp

router = APIRouter()


def _get_provider():
    """Resolve LLM provider from settings/environment."""
    settings = get_settings()

    # Primary: Anthropic-compatible (Kimi Code)
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY") or settings.anthropic_api_key
    anthropic_base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.kimi.com/coding/")
    if anthropic_key:
        return AnthropicProvider(
            api_key=anthropic_key,
            base_url=anthropic_base,
            default_model="claude-3-5-sonnet",
        )

    # Fallback 1: DeepSeek (OpenAI-compatible)
    if settings.deepseek_api_key:
        return OpenAICompatibleProvider(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com/v1",
            default_model="deepseek-chat",
        )

    # Fallback 2: Qwen (OpenAI-compatible)
    if settings.qwen_api_key:
        return OpenAICompatibleProvider(
            api_key=settings.qwen_api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            default_model="qwen-plus",
        )

    return None


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    await websocket.accept()

    session = websocket.scope.get("session", {})
    project_name = session.get("current_project_name")
    ctx_token = None
    if project_name:
        project_dir = resolve_project_dir(project_name)
        if project_dir:
            ctx_token = _current_project_path.set(project_dir)

    try:
        provider = _get_provider()
        if provider is None:
            await websocket.send_json(
                {"type": "error", "message": "No LLM provider configured. Set ANTHROPIC_API_KEY or deepseek/qwen API key."}
            )
            await websocket.close()
            return

        engine = ChatEngine(mcp=mcp, provider=provider)
        messages: list[dict[str, Any]] = []

        async def _send_turn_result(result: dict[str, Any]) -> None:
            """Stream a turn result over the WebSocket."""
            if result.get("type") == "awaiting_confirmation":
                confirmation = result.get("confirmation", {})
                await websocket.send_json(
                    {
                        "type": "awaiting_confirmation",
                        "confirmation_id": confirmation.get("confirmation_id"),
                        "message": confirmation.get("message"),
                        "candidates": confirmation.get("candidates", []),
                    }
                )
                return

            if result.get("error"):
                await websocket.send_json({"type": "error", "message": result["error"]})
                return

            # Replay messages in chronological order
            for msg in result.get("messages", []):
                role = msg.get("role")
                if role == "assistant":
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                await websocket.send_json(
                                    {"type": "assistant_delta", "delta": block.get("text", "")}
                                )
                            elif isinstance(block, dict) and block.get("type") == "tool_use":
                                await websocket.send_json(
                                    {
                                        "type": "tool_start",
                                        "tool_name": block.get("name", ""),
                                    }
                                )
                elif role == "user":
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_result":
                                await websocket.send_json(
                                    {
                                        "type": "tool_result",
                                        "result": {
                                            "content": block.get("content", ""),
                                            "success": block.get("success", False),
                                        },
                                    }
                                )

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                    continue

                msg_type = payload.get("type")
                if msg_type == "user_message":
                    content = payload.get("content", "")
                    messages.append({"role": "user", "content": content})

                    result = await engine.run_turn(messages)
                    await _send_turn_result(result)
                    messages = result.get("messages", messages)

                elif msg_type == "confirmation_response":
                    confirmation_id = payload.get("confirmation_id", "")
                    approved = payload.get("approved", False)

                    pending = engine.confirmation.pending
                    if pending is None or pending.confirmation_id != confirmation_id:
                        await websocket.send_json(
                            {"type": "error", "message": "No matching pending confirmation."}
                        )
                        continue

                    if approved:
                        # Append a synthetic tool_result so the LLM can continue
                        messages.append(
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": confirmation_id,
                                        "content": f"Tool {pending.tool_name} confirmed and executed.",
                                        "success": True,
                                    }
                                ],
                            }
                        )
                    else:
                        engine.confirmation.resolve(approved=False)
                        messages.append(
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": confirmation_id,
                                        "content": f"User cancelled {pending.tool_name}.",
                                        "success": False,
                                    }
                                ],
                            }
                        )

                    result = await engine.run_turn(messages)
                    await _send_turn_result(result)
                    messages = result.get("messages", messages)
                else:
                    await websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})

        except WebSocketDisconnect:
            pass
        except Exception as exc:
            try:
                await websocket.send_json({"type": "error", "message": f"Server error: {exc}"})
                await websocket.close()
            except Exception:
                pass
    finally:
        if ctx_token is not None:
            _current_project_path.reset(ctx_token)
