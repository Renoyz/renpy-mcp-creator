"""WebSocket endpoint for /ws/chat — bridges Dashboard Chat Drawer to ChatEngine."""

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..chat_engine import AnthropicProvider, ChatEngine, OpenAICompatibleProvider
from ..config import get_settings, _current_project_path, resolve_project_dir
from ..server import mcp

router = APIRouter()


def _chat_history_path(project_name: str) -> Path:
    settings = get_settings()
    return settings.workspace / project_name / "logs" / "chat-history.json"


def _write_chat_history(project_name: str, messages: list[dict[str, Any]]) -> None:
    path = _chat_history_path(project_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"messages": messages}, indent=2), encoding="utf-8")


def _read_chat_history(project_name: str) -> list[dict[str, Any]]:
    path = _chat_history_path(project_name)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("messages", [])
    except (json.JSONDecodeError, OSError):
        return []


def _active_project_name(websocket: WebSocket, payload_project_name: str | None = None) -> str | None:
    """Resolve the currently-bound project name from contextvar, session, or payload."""
    path = _current_project_path.get()
    if path is not None:
        return path.name
    if payload_project_name:
        return payload_project_name
    session = websocket.scope.get("session", {})
    return session.get("current_project_name")


# General chat queries that do not require an active project.
# Intentionally conservative: only greetings and help/introduction intents.
_NO_PROJECT_WHITELIST = frozenset(
    [
        "hello",
        "hi",
        "hey",
        "help",
        "what can you do",
        "who are you",
        "你好",
        "您好",
        "在吗",
        "帮助",
        "你能做什么",
        "你是谁",
    ]
)


def _allowed_without_project(content: str) -> bool:
    stripped = content.strip().lower()
    for phrase in _NO_PROJECT_WHITELIST:
        if stripped.startswith(phrase):
            return True
    return False


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


def _bind_project_context(websocket: WebSocket, token_holder: list, project_name: str | None = None):
    """Re-read session/payload and update the request-scoped project path contextvar."""
    if token_holder[0] is not None:
        _current_project_path.reset(token_holder[0])
        token_holder[0] = None
    if project_name is None:
        session = websocket.scope.get("session", {})
        project_name = session.get("current_project_name")
    if project_name:
        project_dir = resolve_project_dir(project_name)
        if project_dir:
            token_holder[0] = _current_project_path.set(project_dir)


def _system_prompt_for_current_project(engine: ChatEngine) -> str:
    """Augment the base prompt with the currently selected project context."""
    base_prompt = getattr(
        engine,
        "system_prompt",
        (
            "You are an AI assistant for Ren'Py visual novel development. "
            "When the user asks about the current workspace, rely on the selected project context."
        ),
    )
    project_path = _current_project_path.get()
    if project_path is None:
        return base_prompt

    return (
        f"{base_prompt}\n\n"
        "The user is already working inside a selected Ren'Py project.\n"
        f"- Current project name: {project_path.name}\n"
        f"- Current project path: {project_path}\n"
        "You already know the current project from the workspace context. "
        "Use it as the default target for project-scoped requests. "
        "Do not ask the user to repeat the current project name or path unless they explicitly want to operate on a different project.\n"
        "For any request that modifies project content or files (backgrounds, characters, dialogue, choices, options, or scripts), "
        "read the relevant project file(s) first, then apply concrete tool-based edits to those files.\n"
        "Do not claim a project file was modified unless a tool_result has just confirmed success.\n"
        "When updating existing script content, replace conflicting statements instead of appending duplicates."
    )


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    await websocket.accept()

    token_holder: list = [None]
    _bind_project_context(websocket, token_holder)

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
        sent_message_count = 0

        async def _send_turn_result(result: dict[str, Any]) -> None:
            """Stream a turn result over the WebSocket."""
            nonlocal sent_message_count
            if result.get("type") == "awaiting_confirmation":
                confirmation = result.get("confirmation", {})
                await websocket.send_json(
                    {
                        "type": "awaiting_confirmation",
                        "confirmation_id": confirmation.get("confirmation_id"),
                        "message": confirmation.get("message"),
                        "candidates": confirmation.get("candidates", []),
                        "project_name": confirmation.get("project_name"),
                    }
                )
                return

            if result.get("error"):
                await websocket.send_json({"type": "error", "message": result["error"]})
                return

            result_messages = result.get("messages", [])

            # Stream only newly-added messages so earlier assistant replies are
            # not replayed on subsequent turns. Some tests and lightweight
            # adapters return only the latest turn instead of cumulative
            # history; fall back to replaying the whole result in that case.
            start_index = sent_message_count if len(result_messages) > sent_message_count else 0
            for msg in result_messages[start_index:]:
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
            sent_message_count = len(result_messages)

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                    continue

                msg_type = payload.get("type")
                project_name = payload.get("project_name")

                # Refresh project context before handling every message so that
                # subsequent turns pick up a newly-selected project.  (If the
                # underlying session store was updated out-of-band, the frontend
                # is expected to reconnect the WebSocket so the handshake picks
                # up the new cookie.  Re-binding here is defensive for any
                # future session backend that supports mid-connection refresh.)
                _bind_project_context(websocket, token_holder, project_name)

                if msg_type == "user_message":
                    content = payload.get("content", "")
                    if _current_project_path.get() is None and not _allowed_without_project(content):
                        await websocket.send_json(
                            {"type": "error", "message": "No active project selected."}
                        )
                        continue
                    messages.append({"role": "user", "content": content})

                    engine.system_prompt = _system_prompt_for_current_project(engine)
                    result = await engine.run_turn(messages)
                    await _send_turn_result(result)
                    messages = result.get("messages", messages)
                    active_project = _active_project_name(websocket, project_name)
                    if active_project:
                        _write_chat_history(active_project, messages)

                elif msg_type == "confirmation_response":
                    confirmation_id = payload.get("confirmation_id", "")
                    approved = payload.get("approved", False)

                    pending = engine.confirmation.pending
                    if pending is None or pending.confirmation_id != confirmation_id:
                        await websocket.send_json(
                            {"type": "error", "message": "No matching pending confirmation."}
                        )
                        continue

                    # Bind to the project that was active when the confirmation was created,
                    # regardless of what the frontend currently thinks the active project is.
                    if pending.project_name:
                        _bind_project_context(websocket, token_holder, pending.project_name)

                    if approved:
                        # Append the original tool_result so the LLM can continue with the
                        # correct tool_use_id and full result payload.
                        approved_result = pending.tool_result or {}
                        messages.append(
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": pending.tool_use_id or confirmation_id,
                                        "content": approved_result.get(
                                            "content",
                                            f"Tool {pending.tool_name} confirmed and executed.",
                                        ),
                                        "success": approved_result.get("success", True),
                                    }
                                ],
                            }
                        )
                        engine.confirmation.resolve(approved=True)
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

                    engine.system_prompt = _system_prompt_for_current_project(engine)
                    result = await engine.run_turn(messages)
                    await _send_turn_result(result)
                    messages = result.get("messages", messages)
                    active_project = pending.project_name or _active_project_name(websocket, project_name)
                    if active_project:
                        _write_chat_history(active_project, messages)
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
        if token_holder[0] is not None:
            _current_project_path.reset(token_holder[0])
