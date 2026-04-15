"""Confirmation state machine for high-impact tool calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import _current_project_path


@dataclass
class PendingConfirmation:
    """Represents a tool call awaiting user confirmation."""

    confirmation_id: str
    tool_name: str
    arguments: dict[str, Any]
    message: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    project_name: str | None = None
    tool_use_id: str | None = None
    tool_result: dict[str, Any] | None = None


class ConfirmationState:
    """Manages pending confirmations and resumes ReAct loops."""

    HIGH_IMPACT_TOOLS: set[str] = {
        "generate_character",
        "generate_background",
        "delete_project",
        "build_project",
    }

    def __init__(self) -> None:
        self._pending: PendingConfirmation | None = None

    @property
    def is_waiting(self) -> bool:
        return self._pending is not None

    @property
    def pending(self) -> PendingConfirmation | None:
        return self._pending

    def should_confirm(self, tool_name: str) -> bool:
        return tool_name in self.HIGH_IMPACT_TOOLS

    def request_confirmation(
        self,
        confirmation_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        tool_use_id: str | None = None,
        tool_result: dict[str, Any] | None = None,
    ) -> PendingConfirmation:
        """Create a pending confirmation for a tool call."""
        message = self._build_message(tool_name, arguments, tool_result)
        candidates = self._extract_candidates(tool_name, tool_result)

        ctx_path = _current_project_path.get()
        self._pending = PendingConfirmation(
            confirmation_id=confirmation_id,
            tool_name=tool_name,
            arguments=arguments,
            message=message,
            candidates=candidates,
            project_name=ctx_path.name if ctx_path else None,
            tool_use_id=tool_use_id,
            tool_result=tool_result,
        )
        return self._pending

    def resolve(self, approved: bool) -> PendingConfirmation | None:
        """Resolve the pending confirmation. Returns it and clears state."""
        pending = self._pending
        self._pending = None
        return pending

    def _build_message(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        tool_result: dict[str, Any] | None,
    ) -> str:
        if tool_name == "generate_character":
            name = arguments.get("character_name", "角色")
            return f"已生成角色 '{name}'，请确认是否保存。"
        if tool_name == "generate_background":
            return "已生成背景图，请确认是否保存。"
        if tool_name == "delete_project":
            name = arguments.get("name", "项目")
            return f"即将删除项目 '{name}'，是否确认？"
        if tool_name == "build_project":
            name = arguments.get("project_name", "项目")
            return f"即将构建项目 '{name}'，是否确认？"
        return f"即将执行 {tool_name}，是否确认？"

    def _extract_candidates(
        self,
        tool_name: str,
        tool_result: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        if tool_result is None:
            return candidates

        # Try raw result first, then fall back to serialized content
        result_data = tool_result.get("result")
        if result_data is None:
            result_data = tool_result.get("content")

        if isinstance(result_data, str):
            try:
                import json

                result_data = json.loads(result_data)
            except json.JSONDecodeError:
                result_data = {"content": result_data}

        if not isinstance(result_data, dict):
            return candidates

        if tool_name in ("generate_character", "generate_background"):
            files = result_data.get("files") or result_data.get("relative_files")
            if isinstance(files, list):
                for f in files:
                    candidates.append({"type": "image", "path": f})
            elif isinstance(files, str):
                candidates.append({"type": "image", "path": files})

        return candidates
