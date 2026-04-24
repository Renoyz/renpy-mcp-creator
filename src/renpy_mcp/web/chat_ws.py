"""WebSocket endpoint for /ws/chat — bridges Dashboard Chat Drawer to ChatEngine."""

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from ..blueprint.models import (
    BlueprintCharacter,
    ChapterIntakeEntry,
    ChapterSummary,
    IntakePhase,
    IntakeSlot,
    PipelineStage,
    ProjectBlueprint,
    ProjectBrief,
    ProjectStatus,
    RefinementIntake,
    SceneSummary,
)
from ..chat_engine import AnthropicProvider, ChatEngine, OpenAICompatibleProvider
from ..config import get_settings, _current_project_path, resolve_project_dir
from ..server import mcp
from ..models import BuildRequest, BuildResult
from ..services.build_manager import BuildManager
from ..services.project_manager import ProjectManager
from ..services.prototype_generation_service import PrototypeGenerationService

router = APIRouter()

logger = logging.getLogger(__name__)


def _is_rate_limited_429(exc: Exception) -> bool:
    """Return True when an exception clearly indicates a 429 rate limit."""
    status_code = getattr(exc, "status_code", None)
    if status_code == 429:
        return True
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True
    text = str(exc).lower()
    return "429" in text and ("too many requests" in text or "rate limit" in text)


def _anthropic_tools_to_openai(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    """Convert Anthropic tool schema to OpenAI function-calling schema."""
    if tools is None:
        return None
    converted: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") == "function" and "function" in tool:
            converted.append(tool)
            continue
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
        )
    return converted


class _Kimi429FallbackProvider:
    """Anthropic-compatible primary with automatic DeepSeek fallback on Kimi 429."""

    tool_format = "anthropic"

    def __init__(self, primary: AnthropicProvider, fallback: OpenAICompatibleProvider) -> None:
        self.primary = primary
        self.fallback = fallback
        self.default_model = getattr(primary, "default_model", None)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float | None = None,
    ):
        try:
            return self.primary.chat(
                messages=messages,
                tools=tools,
                system=system,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception as exc:
            if not _is_rate_limited_429(exc):
                raise
            logger.warning("Kimi provider hit 429 Too Many Requests; falling back to DeepSeek")
            fallback_tools = _anthropic_tools_to_openai(tools)
            return self.fallback.chat(
                messages=messages,
                tools=fallback_tools,
                system=system,
                model=None,
                max_tokens=max_tokens,
                temperature=temperature,
            )


def _chat_history_path(project_name: str) -> Path:
    settings = get_settings()
    return settings.workspace / project_name / "meta" / "chat_history.json"


def _legacy_chat_history_path(project_name: str) -> Path:
    settings = get_settings()
    return settings.workspace / project_name / "logs" / "chat-history.json"


def _write_chat_history(project_name: str, messages: list[dict[str, Any]]) -> None:
    path = _chat_history_path(project_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"messages": messages}, indent=2), encoding="utf-8")


def _write_build_status_for_project(
    project_name: str,
    status: str,
    message: str,
    output_path: Path | None = None,
    target: str = "web",
) -> None:
    """Persist build status to the project's logs/build-status.json."""
    settings = get_settings()
    status_file = settings.workspace / project_name / "logs" / "build-status.json"
    status_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "message": message,
        "output_path": str(output_path) if output_path else None,
        "previewable": output_path is not None and (Path(output_path) / "index.html").exists() if output_path else False,
        "target": target,
        "updated_at": datetime.utcnow().isoformat(),
    }
    status_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Blueprint session state persistence
# ---------------------------------------------------------------------------

def _runtime_session_path(project_name: str) -> Path:
    settings = get_settings()
    return settings.workspace / project_name / "meta" / "blueprint_session.json"


def _load_runtime_session(project_name: str) -> dict[str, Any] | None:
    path = _runtime_session_path(project_name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _save_runtime_session(project_name: str, state: dict[str, Any]) -> None:
    path = _runtime_session_path(project_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _clear_runtime_session(project_name: str) -> None:
    path = _runtime_session_path(project_name)
    if path.exists():
        path.unlink()


def _read_chat_history(project_name: str) -> list[dict[str, Any]]:
    path = _chat_history_path(project_name)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("messages", [])
        except (json.JSONDecodeError, OSError):
            return []
    # Backward compatibility: fall back to the old logs path.
    legacy_path = _legacy_chat_history_path(project_name)
    if not legacy_path.exists():
        return []
    try:
        return json.loads(legacy_path.read_text(encoding="utf-8")).get("messages", [])
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


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _is_clearly_english(text: str) -> bool:
    if not text.strip() or _contains_cjk(text):
        return False
    words = re.findall(r"[A-Za-z]{2,}", text)
    letters = sum(len(word) for word in words)
    return len(words) >= 3 or letters >= 18


def _preferred_output_language_from_texts(texts: list[str]) -> str:
    for text in reversed(texts):
        stripped = text.strip()
        if not stripped or stripped in _START_TRIGGERS:
            continue
        if _contains_cjk(stripped):
            return "zh"
        if _is_clearly_english(stripped):
            return "en"
    return "zh"


def _preferred_output_language_from_messages(messages: list[dict[str, Any]]) -> str:
    texts: list[str] = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            texts.append(content)
    return _preferred_output_language_from_texts(texts)


def _localized_text(lang: str, zh: str, en: str) -> str:
    return en if lang == "en" else zh


def _language_instruction(lang: str) -> str:
    return _localized_text(
        lang,
        "Preferred output language for all user-visible content: Simplified Chinese.",
        "Preferred output language for all user-visible content: English.",
    )


def _localized_confirmation_message(tool_name: str | None, lang: str, fallback: str) -> str:
    if lang != "en":
        return fallback
    if tool_name == "generate_background":
        return "Generated a background image. Save it?"
    if tool_name == "generate_character":
        return "Generated a character image. Save it?"
    if tool_name == "delete_project":
        return "Delete this project?"
    if tool_name == "build_project":
        return "Build this project now?"
    return f"Run {tool_name or 'this action'}?"


def _extract_json_block(text: str) -> str | None:
    """Extract the outermost JSON object or array from mixed text."""
    text = text.strip()
    start = -1
    for i, ch in enumerate(text):
        if ch in "{[":
            start = i
            break
    if start == -1:
        return None
    stack = []
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch == "}":
            if stack and stack[-1] == "{":
                stack.pop()
            else:
                return None  # mismatched
            if not stack:
                return text[start : i + 1]
        elif ch == "]":
            if stack and stack[-1] == "[":
                stack.pop()
            else:
                return None
            if not stack:
                return text[start : i + 1]
    return None


def _repair_json_text(text: str) -> str:
    """Attempt to repair common LLM JSON output errors.

    Fixes:
    - Extracts JSON from surrounding text
    - Removes trailing commas before ] and }
    - Strips C++-style comments
    - Normalizes stray whitespace around structural commas
    """
    block = _extract_json_block(text)
    if block is None:
        return text

    # Remove single-line comments (// ...)
    lines = []
    for line in block.splitlines():
        # Be careful not to strip // inside strings
        cleaned = []
        in_str = False
        esc = False
        for i, ch in enumerate(line):
            if esc:
                esc = False
                cleaned.append(ch)
                continue
            if ch == "\\":
                esc = True
                cleaned.append(ch)
                continue
            if ch == '"':
                in_str = not in_str
                cleaned.append(ch)
                continue
            if not in_str and ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                break
            cleaned.append(ch)
        lines.append("".join(cleaned))
    block = "\n".join(lines)

    # Remove trailing commas before } or ]
    # Use a stateful pass so we don't affect commas inside strings
    result_chars: list[str] = []
    i = 0
    while i < len(block):
        ch = block[i]
        if ch == '"':
            # Copy whole string literal
            result_chars.append(ch)
            i += 1
            esc = False
            while i < len(block):
                c2 = block[i]
                result_chars.append(c2)
                if esc:
                    esc = False
                elif c2 == "\\":
                    esc = True
                elif c2 == '"':
                    i += 1
                    break
                i += 1
            continue
        if ch == ",":
            # Peek ahead for whitespace then } or ]
            j = i + 1
            while j < len(block) and block[j] in " \t\n\r":
                j += 1
            if j < len(block) and block[j] in "}]":
                # Skip the comma (and whitespace) — just advance i to j
                i = j
                continue
        result_chars.append(ch)
        i += 1

    return "".join(result_chars)


def _get_provider():
    """Resolve LLM provider from settings/environment."""
    if os.environ.get("RENPY_MCP_MOCK_LLM"):
        from ..chat_engine.providers import BaseProvider, LLMResponse

        class MockE2EProvider(BaseProvider):
            tool_format = "anthropic"
            _turn_count = 0

            def _is_blueprint_prompt(self, messages):
                for m in messages:
                    content = m.get("content", "")
                    if isinstance(content, str):
                        if "Project Name:" in content and "Interview Transcript:" in content:
                            return True
                return False

            def _extract_project_name(self, messages):
                import re as _re
                for m in messages:
                    content = m.get("content", "")
                    if isinstance(content, str):
                        match = _re.search(r"Project Name:\s*(.+)", content)
                        if match:
                            return match.group(1).strip()
                return "MockLLM校园恋爱"

            def _preferred_output_language(self, messages, system):
                combined_parts: list[str] = []
                if isinstance(system, str):
                    combined_parts.append(system)
                for m in messages:
                    content = m.get("content", "")
                    if isinstance(content, str):
                        combined_parts.append(content)
                combined = "\n".join(combined_parts)
                if "Preferred output language for all user-visible content: English." in combined:
                    return "en"
                return "zh"

            def chat(self, messages, tools=None, system=None, model=None, max_tokens=1024, temperature=None):
                self._turn_count += 1
                lang = self._preferred_output_language(messages, system)

                # Blueprint generation mock
                if self._is_blueprint_prompt(messages):
                    project_name = self._extract_project_name(messages)
                    if lang == "en":
                        blueprint = {
                            "title": project_name,
                            "genre": "Historical Drama / Medieval Knight Story",
                            "worldview": "A declining medieval kingdom torn by war and plague.",
                            "themes": ["Honor", "Redemption"],
                            "target_audience": "Players who enjoy character-driven visual novels",
                            "estimated_play_time": "1 hour",
                            "art_style": "Muted watercolor anime style",
                            "audio_style": "Sparse orchestral and lute arrangements",
                            "characters": [
                                {"name": "Mock Hero Liam", "role": "Protagonist", "personality": "Quiet and determined", "appearance": "Worn knight armor"},
                                {"name": "Mock Heroine Elara", "role": "Companion", "personality": "Warm and perceptive", "appearance": "Short hair and a scholar's cloak"},
                            ],
                            "chapters": [
                                {"id": "ch1", "name": "The Fallen Oath", "order": 1, "scenes": [
                                    {"id": "s1-1", "name": "Ruined Chapel", "order": 1},
                                    {"id": "s1-2", "name": "A Roadside Promise", "order": 2},
                                ]},
                                {"id": "ch2", "name": "Ashes of the Keep", "order": 2, "scenes": [
                                    {"id": "s2-1", "name": "Campfire Confession", "order": 1},
                                    {"id": "s2-2", "name": "The Last Gate", "order": 2},
                                ]},
                            ],
                        }
                    else:
                        blueprint = {
                            "title": project_name,
                            "genre": "历史剧 / 中世纪骑士故事",
                            "worldview": "一个在战乱与瘟疫中走向衰败的中世纪王国。",
                            "themes": ["荣誉", "救赎"],
                            "target_audience": "喜欢角色驱动视觉小说的玩家",
                            "estimated_play_time": "1小时",
                            "art_style": "低饱和水彩日系风格",
                            "audio_style": "稀疏的弦乐与鲁特琴配乐",
                            "characters": [
                                {"name": "Mock主角小明", "role": "主角", "personality": "沉默坚定", "appearance": "磨损的骑士铠甲"},
                                {"name": "Mock女主小樱", "role": "同伴", "personality": "温和敏锐", "appearance": "短发与学者披风"},
                            ],
                            "chapters": [
                                {"id": "ch1", "name": "坠落的誓言", "order": 1, "scenes": [
                                    {"id": "s1-1", "name": "废弃礼拜堂", "order": 1},
                                    {"id": "s1-2", "name": "路边约定", "order": 2},
                                ]},
                                {"id": "ch2", "name": "城堡余烬", "order": 2, "scenes": [
                                    {"id": "s2-1", "name": "篝火告白", "order": 1},
                                    {"id": "s2-2", "name": "最后的城门", "order": 2},
                                ]},
                            ],
                        }
                    text = json.dumps(blueprint, ensure_ascii=False)
                    if os.environ.get("RENPY_MCP_MOCK_LLM_MALFORMED_JSON"):
                        # Inject trailing commas to simulate common LLM output bug.
                        # Add a comma to the end of any line that precedes a lone ] or }.
                        lines = text.split("\n")
                        new_lines: list[str] = []
                        for line in lines:
                            stripped = line.strip()
                            if stripped in ("]", "}") and new_lines:
                                prev = new_lines[-1].rstrip()
                                if not prev.endswith(","):
                                    new_lines[-1] = prev + ","
                            new_lines.append(line)
                        text = "\n".join(new_lines)
                    return LLMResponse(
                        content_blocks=[{"type": "text", "text": text}],
                        stop_reason="end_turn",
                    )

                # Prototype scene generation mock
                prompt = messages[0].get("content", "") if messages else ""
                if "Generate a JSON array of scenes" in prompt:
                    scenes = [
                        {
                            "scene_id": "proto-ch1-s1",
                            "title": "初次相遇",
                            "summary": "主角在图书馆遇到配角。",
                            "location": "library",
                            "characters_present": ["Mock主角小明"],
                            "entry_label": "prototype_ch1_start",
                            "next_scene_id": "proto-ch1-s2",
                        },
                        {
                            "scene_id": "proto-ch1-s2",
                            "title": "深夜对话",
                            "summary": "两人在咖啡厅讨论未来。",
                            "location": "cafe",
                            "characters_present": ["Mock主角小明", "Mock女主小樱"],
                            "entry_label": "prototype_ch1_scene2",
                            "next_scene_id": None,
                        },
                    ]
                    return LLMResponse(
                        content_blocks=[{"type": "text", "text": json.dumps(scenes, ensure_ascii=False)}],
                        stop_reason="end_turn",
                    )

                # Tool workflow mock
                if self._turn_count == 1:
                    return LLMResponse(
                        content_blocks=[{
                            "type": "tool_use",
                            "id": "mock_tool_1",
                            "name": "generate_background",
                            "input": {"description": "courtyard", "image_type": "background", "style": "anime"},
                        }],
                        stop_reason="tool_use",
                    )
                return LLMResponse(
                    content_blocks=[{
                        "type": "text",
                        "text": _localized_text(lang, "背景图已生成成功。", "Background generated successfully."),
                    }],
                    stop_reason="end_turn",
                )

        return MockE2EProvider()

    settings = get_settings()

    # Helper: detect OpenAI-compatible endpoint by URL pattern
    def _is_openai_compatible_url(url: str | None) -> bool:
        if not url:
            return False
        url_lower = url.lower()
        openai_markers = ("moonshot", "deepseek", "dashscope", "openai", "siliconflow", "groq")
        return any(m in url_lower for m in openai_markers)

    # Primary: Anthropic-compatible (Kimi Code)
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY") or settings.anthropic_api_key
    anthropic_base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.kimi.com/coding/")
    anthropic_model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet")
    if anthropic_key and not _is_openai_compatible_url(anthropic_base):
        primary = AnthropicProvider(
            api_key=anthropic_key,
            base_url=anthropic_base,
            default_model=anthropic_model,
        )
        if settings.deepseek_api_key:
            fallback = OpenAICompatibleProvider(
                api_key=settings.deepseek_api_key,
                base_url="https://api.deepseek.com/v1",
                default_model="deepseek-chat",
            )
            return _Kimi429FallbackProvider(primary=primary, fallback=fallback)
        return primary

    # OpenAI-compatible primary (Moonshot, DeepSeek, custom OpenAI proxy, etc.)
    openai_key = os.environ.get("OPENAI_API_KEY") or settings.anthropic_api_key
    openai_base = os.environ.get("OPENAI_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL")
    openai_model = os.environ.get("OPENAI_MODEL", "moonshot-v1-8k")
    if openai_key and openai_base and _is_openai_compatible_url(openai_base):
        return OpenAICompatibleProvider(
            api_key=openai_key,
            base_url=openai_base,
            default_model=openai_model,
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


# ---------------------------------------------------------------------------
# Blueprint interview orchestrator
# ---------------------------------------------------------------------------

_orchestrators: dict[str, "BlueprintOrchestrator"] = {}

_START_TRIGGERS = frozenset([
    "start_blueprint_collection",
    "让 AI 生成蓝图",
])

_INTAKE_START_TRIGGERS = frozenset([
    "start_refinement_intake",
])


class BlueprintOrchestrator:
    """Minimal backend-driven orchestrator for the blueprint interview flow.

    Manages phase transitions:
        idle -> collecting -> reviewing -> generating -> editing
    """

    def __init__(self, project_name: str, pm: ProjectManager) -> None:
        self.project_name = project_name
        self.pm = pm
        self.phase = PipelineStage.IDLE
        self.turn_count = 0
        self.draft: ProjectBlueprint | None = None
        self.confirmation_id: str | None = None
        self.intake_mode = False
        self.messages: list[dict[str, Any]] = []
        self._try_restore_session()

    def _try_restore_session(self) -> None:
        session = _load_runtime_session(self.project_name)
        if not session:
            return
        stage = session.get("pipeline_stage")
        if stage in (PipelineStage.IDLE.value, PipelineStage.COLLECTING.value,
                     PipelineStage.REVIEWING.value, PipelineStage.GENERATING.value):
            self.phase = PipelineStage(stage)
        self.turn_count = session.get("turn_count", 0)
        self.confirmation_id = session.get("confirmation_id")
        self.intake_mode = bool(session.get("intake_mode", False))
        if session.get("draft"):
            try:
                self.draft = ProjectBlueprint(**session["draft"])
            except Exception:
                self.draft = None

    def _save_session(self) -> None:
        state: dict[str, Any] = {
            "active_workflow": "blueprint",
            "pipeline_stage": self.phase.value,
            "turn_count": self.turn_count,
            "awaiting_confirmation": self.phase == PipelineStage.REVIEWING and self.confirmation_id is not None,
            "confirmation_id": self.confirmation_id,
            "intake_mode": self.intake_mode,
        }
        if self.draft:
            state["draft"] = self.draft.model_dump(mode="json")
        _save_runtime_session(self.project_name, state)

    def _save_session_with_progress(self, step: str, percent: int) -> None:
        state: dict[str, Any] = {
            "active_workflow": "blueprint",
            "pipeline_stage": self.phase.value,
            "turn_count": self.turn_count,
            "awaiting_confirmation": False,
            "confirmation_id": None,
            "latest_progress": {"step": step, "percent": percent},
        }
        if self.draft:
            state["draft"] = self.draft.model_dump(mode="json")
        _save_runtime_session(self.project_name, state)

    def _load_history(self) -> None:
        self.messages = _read_chat_history(self.project_name)

    def _save_history(self) -> None:
        _write_chat_history(self.project_name, self.messages)

    def _project_intake_slot_keys(self) -> list[str]:
        return [
            "core_premise",
            "audience_genre",
            "tone_themes",
            "visual_style",
            "world_rules",
            "core_cast",
            "character_identity",
            "relationship_baselines",
            "constraints",
        ]

    def _build_chapter_intake_entry(self, chapter) -> ChapterIntakeEntry:
        scene_names = [scene.name for scene in chapter.scenes if scene.name]
        first_scene_name = scene_names[0] if scene_names else chapter.name
        last_scene_name = scene_names[-1] if scene_names else chapter.name

        character_focus: list[str] = []
        for scene in chapter.scenes:
            for character in scene.characters:
                if character and character not in character_focus:
                    character_focus.append(character)

        chapter_goal = (
            f"Advance {chapter.name} through {first_scene_name}"
            if first_scene_name
            else f"Advance {chapter.name}"
        )
        key_conflict = (
            f"Pressure escalates around {last_scene_name}"
            if last_scene_name
            else f"Core conflict in {chapter.name}"
        )
        emotional_arc = "setup -> escalation" if len(scene_names) > 1 else "setup -> turn"
        reveals = last_scene_name or chapter.name
        end_state = last_scene_name or chapter.name
        mood_or_pacing_bias = "measured" if len(scene_names) <= 2 else "escalating"
        relationship_shift = ""
        if len(character_focus) >= 2:
            relationship_shift = f"{character_focus[0]} and {character_focus[1]} face new pressure together"
        character_presentation_notes = (
            f"Keep visual focus on {', '.join(character_focus)}"
            if character_focus
            else f"Carry forward the chapter identity of {chapter.name}"
        )

        return ChapterIntakeEntry(
            chapter_id=chapter.id,
            order=chapter.order,
            chapter_name=chapter.name,
            chapter_goal=chapter_goal,
            key_conflict=key_conflict,
            emotional_arc=emotional_arc,
            reveals=reveals,
            end_state=end_state,
            mood_or_pacing_bias=mood_or_pacing_bias,
            character_focus=character_focus,
            relationship_shift=relationship_shift,
            character_presentation_notes=character_presentation_notes,
        )

    def _is_brief_fully_confirmed(self) -> bool:
        """Check whether the project's brief is fully confirmed on disk."""
        try:
            brief = self.pm.read_project_brief(self.project_name)
        except Exception:
            return False
        if brief is None or not brief.cards:
            return False
        for card_key, card in brief.cards.items():
            if not card.confirmed:
                return False
            if card_key == "character_identity":
                if not isinstance(card.content, dict):
                    return False
                characters = card.content.get("characters", [])
                if not characters:
                    return False
                for entry in characters:
                    has_substance = bool(
                        entry.get("story_role", "").strip()
                        or entry.get("core_motivation", "").strip()
                        or entry.get("personality_anchors", [])
                        or entry.get("visual_identity_anchors", [])
                        or entry.get("forbidden_drift", [])
                    )
                    if not has_substance:
                        return False
        return True

    def _write_refinement_intake(self, *, latest_user_content: str | None = None) -> RefinementIntake:
        brief_confirmed = self._is_brief_fully_confirmed()

        if self.phase == PipelineStage.REVIEWING and self.draft is not None:
            if brief_confirmed:
                # Chapter-level outline draft ready
                chapter_draft = [self._build_chapter_intake_entry(ch) for ch in self.draft.chapters]
                current_summary = f"Chapter outline draft ready with {len(chapter_draft)} chapters"
                phase = IntakePhase.OUTLINE_READY
                brief_draft_ready = True
                outline_draft_ready = True
            else:
                # Project-level brief draft ready
                characters = [
                    {
                        "character_id": re.sub(r"[^a-z0-9]+", "_", ch.name.lower()).strip("_") or f"char_{idx + 1}",
                        "name": ch.name,
                        "story_role": ch.role,
                        "core_motivation": "",
                        "personality_anchors": [ch.personality] if ch.personality else [],
                        "visual_identity_anchors": [ch.appearance] if ch.appearance else [],
                        "forbidden_drift": [],
                    }
                    for idx, ch in enumerate(self.draft.characters)
                ]
                slots = {
                    "core_premise": IntakeSlot(
                        value=f"{self.draft.genre} story in {self.draft.worldview}".strip(),
                        complete=bool(self.draft.genre or self.draft.worldview),
                    ),
                    "audience_genre": IntakeSlot(value=self.draft.genre, complete=bool(self.draft.genre)),
                    "tone_themes": IntakeSlot(value=", ".join(self.draft.themes), complete=bool(self.draft.themes)),
                    "visual_style": IntakeSlot(value=self.draft.art_style, complete=bool(self.draft.art_style)),
                    "world_rules": IntakeSlot(value=self.draft.worldview, complete=bool(self.draft.worldview)),
                    "core_cast": IntakeSlot(
                        value=", ".join(ch.name for ch in self.draft.characters),
                        complete=bool(self.draft.characters),
                    ),
                    "character_identity": IntakeSlot(
                        value={"characters": characters},
                        complete=bool(characters),
                    ),
                    "relationship_baselines": IntakeSlot(value={"relationships": []}, complete=False),
                    "constraints": IntakeSlot(value="", complete=False),
                }
                current_summary = f"{self.draft.genre} in {self.draft.worldview}".strip()
                phase = IntakePhase.BRIEF_READY
                brief_draft_ready = True
                outline_draft_ready = False
                chapter_draft = []
        else:
            latest = (latest_user_content or "").strip()
            if brief_confirmed:
                # Chapter-level collecting
                slots = {}
                current_summary = latest
                phase = IntakePhase.CHAPTER
                brief_draft_ready = True
                outline_draft_ready = False
                chapter_draft = []
            else:
                # Project-level collecting
                slots = {key: IntakeSlot() for key in self._project_intake_slot_keys()}
                if latest:
                    slots["core_premise"] = IntakeSlot(value=latest, complete=True)
                current_summary = latest
                phase = IntakePhase.PROJECT
                brief_draft_ready = False
                outline_draft_ready = False
                chapter_draft = []

        missing_slots = [key for key, slot in slots.items() if not slot.complete] if "slots" in dir() else []
        # Build intake with whatever state we determined
        kwargs: dict[str, Any] = {
            "phase": phase,
            "current_summary": current_summary,
            "missing_slots": missing_slots,
            "slots": slots if "slots" in dir() else {},
            "brief_draft_ready": brief_draft_ready,
            "outline_draft_ready": outline_draft_ready,
            "chapter_draft": chapter_draft,
            "updated_at": datetime.utcnow().isoformat(),
        }
        intake = RefinementIntake(**kwargs)
        self.pm.write_refinement_intake(self.project_name, intake)
        return intake

    async def _generate_draft_via_llm(self) -> ProjectBlueprint:
        """Generate a blueprint draft by calling the LLM provider.

        Builds a prompt from the interview transcript, calls the provider,
        extracts JSON, and validates against ProjectBlueprint schema.
        Retries up to 2 times on parse/validation errors.
        """
        provider = _get_provider()
        if provider is None:
            raise RuntimeError("No LLM provider configured. Set ANTHROPIC_API_KEY or deepseek/qwen API key.")

        # Build transcript from string-content messages only
        transcript_lines: list[str] = []
        for m in self.messages:
            content = m.get("content", "")
            if isinstance(content, str) and content.strip():
                role_label = "User" if m["role"] == "user" else "Assistant"
                transcript_lines.append(f"{role_label}: {content}")
        transcript = "\n".join(transcript_lines)

        lang = _preferred_output_language_from_messages(self.messages)

        system_prompt = (
            "You are an expert visual novel blueprint designer. "
            "You create structured project blueprints based on user interviews. "
            "You MUST respond with ONLY a valid JSON object. No markdown, no explanations. "
            f"{_language_instruction(lang)}"
        )

        prompt = f"""Based on the following interview, design a complete visual novel blueprint.

Project Name: {self.project_name}

Interview Transcript:
{transcript}

Respond with ONLY a JSON object matching this exact structure:
{{
  "title": "string (use project name or a creative title)",
  "genre": "string",
  "worldview": "string",
  "themes": ["string"],
  "target_audience": "string",
  "estimated_play_time": "string",
  "art_style": "string",
  "audio_style": "string",
  "characters": [
    {{
      "name": "string",
      "role": "string",
      "personality": "string",
      "appearance": "string"
    }}
  ],
  "chapters": [
    {{
      "id": "string",
      "name": "string",
      "order": 1,
      "scenes": [
        {{
          "id": "string",
          "name": "string",
          "order": 1
        }}
      ]
    }}
  ]
}}

Requirements:
- 2-4 chapters, each with 2-4 scenes
- At least 2 well-defined characters
- Themes must match the described tone
- All user-visible string values in the JSON must be written in {_localized_text(lang, "Simplified Chinese", "English")}
- Output ONLY the JSON object, nothing else.
"""

        max_retries = 2
        last_error: str | None = None

        for attempt in range(max_retries + 1):
            try:
                response = await asyncio.to_thread(
                    provider.chat,
                    messages=[{"role": "user", "content": prompt}],
                    system=system_prompt,
                    max_tokens=4096,
                )
            except Exception as e:
                raise RuntimeError(f"Blueprint generation provider error: {e}") from e

            try:
                text = response.text.strip()

                # Extract JSON from markdown code blocks if present
                if text.startswith("```"):
                    lines = text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    text = "\n".join(lines).strip()

                data = json.loads(text)
            except json.JSONDecodeError as e:
                # Attempt repair for common LLM JSON issues (trailing commas, comments, etc.)
                repaired = _repair_json_text(text)
                try:
                    data = json.loads(repaired)
                except json.JSONDecodeError:
                    last_error = f"JSON parse error: {e}"
                    prompt += f"\n\nERROR: Your previous response was not valid JSON ({e}). Return ONLY valid JSON."
                    continue

            try:
                blueprint = ProjectBlueprint(**data)
                return blueprint
            except ValidationError as e:
                last_error = f"Schema validation error: {e}"
                prompt += f"\n\nERROR: Your previous response did not match the required schema ({e}). Fix and return valid JSON."
                continue

        raise RuntimeError(
            f"Blueprint generation failed after {max_retries + 1} attempts. {last_error}"
        )

    async def handle_user_message(self, content: str) -> list[dict[str, Any]]:
        self._load_history()
        lang = _preferred_output_language_from_messages(self.messages)

        # Handle explicit start trigger without consuming a turn
        if (content in _START_TRIGGERS or content in _INTAKE_START_TRIGGERS) and self.turn_count == 0:
            self.intake_mode = content in _INTAKE_START_TRIGGERS
            self.phase = PipelineStage.COLLECTING
            if self.intake_mode:
                assistant_content = _localized_text(
                    lang,
                    "太好了！我会先帮你整理 Project Brief 草稿。首先，请告诉我：故事大概有几章？题材、时代或世界观是什么？主要角色和整体基调是什么？",
                    "Great. I'll first help you prepare a Project Brief draft. To start, roughly how many chapters do you want, what genre/setting/world rules should it use, and who are the main characters and tone?",
                )
                message_kind = "intake_text"
            else:
                assistant_content = _localized_text(
                    lang,
                    "太好了！让我来帮你把这个想法变成完整的蓝图。首先，你希望这个故事大概有几章？有没有特别想设定的主角人设或故事基调？",
                    "Great. I'll help turn this idea into a complete blueprint. To start, roughly how many chapters do you want, and are there any specific protagonist traits or story tone you want to establish?",
                )
                message_kind = "text"
            self.messages.append({"role": "assistant", "message_kind": message_kind, "content": assistant_content})
            self._save_history()
            intake = self._write_refinement_intake()
            self._save_session()
            return [
                {
                    "type": "message",
                    "role": "assistant",
                    "message_kind": message_kind,
                    "content": assistant_content,
                    "pipeline_stage": self.phase.value,
                    "intake": intake.model_dump(mode="json") if self.intake_mode else None,
                }
            ]

        self.messages.append({"role": "user", "content": content})
        self.turn_count += 1
        lang = _preferred_output_language_from_messages(self.messages)

        if self.phase in (PipelineStage.IDLE, PipelineStage.COLLECTING):
            self.phase = PipelineStage.COLLECTING

            if self.turn_count < 2:
                if self.intake_mode:
                    assistant_content = _localized_text(
                        lang,
                        "收到。为了让 Project Brief 更完整，请再补充：\n1. 主角的核心动机\n2. 主要人物的视觉特征\n3. 角色之间的关系基线\n4. 不希望角色发生哪些形象偏移",
                        "Got it. To make the Project Brief more complete, please add:\n1. The protagonist's core motivation\n2. Key visual traits for the main characters\n3. Relationship baselines between characters\n4. Any character drift you want to forbid",
                    )
                    message_kind = "intake_text"
                elif self.turn_count == 1:
                    assistant_content = _localized_text(
                        lang,
                        "收到。为了生成更准确的蓝图，请补充一下：\n1. 世界观或时代背景\n2. 核心角色（1-3位）\n3. 你希望的游戏时长",
                        "Got it. To generate a more accurate blueprint, please add:\n1. The setting or historical era\n2. The core cast (1-3 characters)\n3. The playtime you want for the game",
                    )
                    message_kind = "text"
                else:
                    assistant_content = _localized_text(
                        lang,
                        "很好。接下来我会用这些信息为你生成一份结构化的项目蓝图。确认后，我们会进入分章生成。\n\n请再简单描述一下游戏的整体氛围（例如：轻松、悬疑、治愈）。",
                        "Good. Next I will use this information to generate a structured project blueprint. After you confirm it, we'll move on to chapter generation.\n\nPlease briefly describe the overall mood of the game as well, for example: lighthearted, suspenseful, or healing.",
                    )
                    message_kind = "text"

                self.messages.append({"role": "assistant", "message_kind": message_kind, "content": assistant_content})
                self._save_history()
                intake = self._write_refinement_intake(latest_user_content=content)
                self._save_session()
                return [
                    {
                        "type": "message",
                        "role": "assistant",
                        "message_kind": message_kind,
                        "content": assistant_content,
                        "pipeline_stage": self.phase.value,
                        "intake": intake.model_dump(mode="json") if self.intake_mode else None,
                    }
                ]

            # Second turn -> generate draft via LLM and transition to reviewing
            try:
                self.draft = await self._generate_draft_via_llm()
            except Exception as exc:
                self.phase = PipelineStage.COLLECTING
                error_msg = _localized_text(
                    lang,
                    f"蓝图生成失败：{exc}",
                    f"Blueprint generation failed: {exc}",
                )
                self.messages.append({"role": "assistant", "content": error_msg})
                self._save_history()
                self._save_session()
                return [
                    {
                        "type": "error",
                        "message": error_msg,
                        "pipeline_stage": self.phase.value,
                    }
                ]

            self.phase = PipelineStage.REVIEWING

            if self.intake_mode:
                brief_confirmed = self._is_brief_fully_confirmed()
                intake = self._write_refinement_intake()
                self.phase = PipelineStage.IDLE
                self.confirmation_id = None

                if brief_confirmed:
                    assistant_content = _localized_text(
                        lang,
                        "章节大纲草稿已经整理好。请在 Intake 面板点击 Enter Outline Review，进入章节大纲确认。",
                        "Chapter outline draft is ready. Open the Intake panel and click Enter Outline Review.",
                    )
                    ready_kind = "outline_draft_ready"
                else:
                    assistant_content = _localized_text(
                        lang,
                        "项目简报草稿已经整理好。请在 Intake 面板点击 Enter Brief Review，进入结构化确认。",
                        "Project Brief draft is ready. Open the Intake panel and click Enter Brief Review.",
                    )
                    ready_kind = "brief_draft_ready"

                self.messages.append({"role": "assistant", "content": assistant_content})
                self.messages.append({
                    "role": "assistant",
                    "message_kind": ready_kind,
                    "content": assistant_content,
                })
                self._save_history()
                self._save_session()

                return [
                    {
                        "type": "message",
                        "role": "assistant",
                        "message_kind": "text",
                        "content": assistant_content,
                        "pipeline_stage": self.phase.value,
                        "intake": intake.model_dump(mode="json"),
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "message_kind": ready_kind,
                        "content": assistant_content,
                        "pipeline_stage": self.phase.value,
                        "intake": intake.model_dump(mode="json"),
                    },
                ]

            self.confirmation_id = f"conf_{uuid.uuid4().hex[:8]}"

            assistant_content = _localized_text(
                lang,
                "信息已经足够丰富了。我现在为你整理一份蓝图草案，你可以在右侧查看。",
                "We have enough information now. I'm organizing a blueprint draft for you, and you can review it on the right.",
            )
            draft_notice = _localized_text(
                lang,
                "蓝图草案已生成，请查看并确认。",
                "The blueprint draft is ready. Please review and confirm it.",
            )
            confirm_notice = _localized_text(
                lang,
                "请确认以下蓝图草案，确认后我们将开始正式生成。",
                "Please confirm the blueprint draft below. Once confirmed, we'll begin full generation.",
            )
            draft_dict = self.draft.model_dump(mode="json")
            self.messages.append({"role": "assistant", "content": assistant_content})
            self.messages.append({
                "role": "assistant",
                "message_kind": "blueprint_draft",
                "content": draft_notice,
                "draft": draft_dict,
            })
            self.messages.append({
                "role": "assistant",
                "message_kind": "confirmation_request",
                "content": confirm_notice,
                "draft": draft_dict,
                "confirmation_id": self.confirmation_id,
            })
            self._save_history()
            self._write_refinement_intake()
            self._save_session()

            return [
                {
                    "type": "message",
                    "role": "assistant",
                    "message_kind": "text",
                    "content": assistant_content,
                    "pipeline_stage": self.phase.value,
                },
                {
                    "type": "message",
                    "role": "assistant",
                    "message_kind": "blueprint_draft",
                    "content": draft_notice,
                    "draft": draft_dict,
                    "pipeline_stage": self.phase.value,
                },
                {
                    "type": "confirmation_request",
                    "confirmation_id": self.confirmation_id,
                    "message": confirm_notice,
                    "draft": draft_dict,
                    "pipeline_stage": self.phase.value,
                },
            ]

        if self.phase == PipelineStage.REVIEWING:
            return [
                {
                    "type": "error",
                    "message": _localized_text(
                        lang,
                        "请先确认或拒绝当前蓝图草案。",
                        "Please confirm or reject the current blueprint draft first.",
                    ),
                    "pipeline_stage": self.phase.value,
                }
            ]

        return [
            {
                "type": "error",
                "message": _localized_text(
                    lang,
                    "当前阶段不支持此操作。",
                    "This action is not supported in the current stage.",
                ),
                "pipeline_stage": self.phase.value,
            }
        ]

    async def handle_confirmation_response(self, approved: bool):
        """Handle blueprint confirmation. Yields events as an async generator.

        Progress events are streamed immediately rather than batched at the end.
        """
        self._load_history()
        lang = _preferred_output_language_from_messages(self.messages)

        if self.phase != PipelineStage.REVIEWING:
            yield {
                "type": "error",
                "message": _localized_text(
                    lang,
                    "当前没有待确认的蓝图草案。",
                    "There is no blueprint draft waiting for confirmation right now.",
                ),
                "pipeline_stage": self.phase.value,
            }
            return

        if approved:
            self.phase = PipelineStage.GENERATING

            # Stream the first progress event immediately so the frontend
            # enters generating state without waiting for the whole pipeline.
            first_step = {
                "step": _localized_text(lang, "正在准备生成原型...", "Preparing prototype generation..."),
                "percent": 1,
            }
            self.messages.append({
                "role": "assistant",
                "message_kind": "progress",
                "content": first_step["step"],
                "step": first_step["step"],
                "percent": first_step["percent"],
            })
            self._save_history()
            self._save_session_with_progress(first_step["step"], first_step["percent"])
            yield {"type": "progress", **first_step, "pipeline_stage": self.phase.value}

            # Persist blueprint
            if self.draft:
                await asyncio.to_thread(self.pm.write_blueprint, self.project_name, self.draft)

            # Update meta
            meta = self.pm.read_project_meta(self.project_name)
            if meta:
                meta.pipeline_stage = PipelineStage.EDITING
                meta.status = ProjectStatus.BLUEPRINTED
                if self.draft:
                    meta.chapter_count = len(self.draft.chapters)
                    meta.scene_count = sum(len(ch.scenes) for ch in self.draft.chapters)
                await asyncio.to_thread(self.pm.write_project_meta, self.project_name, meta)

            # Generate prototype scenes and script (staged replace)
            prototype_error: str | None = None
            build_error: str | None = None
            staging_path: str | None = None
            final_path: str | None = None
            new_scene_ids: list[str] = []
            old_script_content: str | None = None
            bg_assets: dict | None = None
            char_assets: dict | None = None
            cjk_font_config: dict | None = None
            round_id: str | None = None

            if self.draft:
                try:
                    provider = _get_provider()
                    service = PrototypeGenerationService(self.pm, provider)
                    chapter = service.select_prototype_chapter(self.draft)
                    round_id = f"r{uuid.uuid4().hex[:8]}"

                    # Build generation contract so that project-level style
                    # constraints are respected across scene/asset generation.
                    contract = service.build_generation_contract(
                        self.project_name, self.draft, chapter
                    )

                    # Step 1: generate scenes
                    step = {
                        "step": _localized_text(lang, "正在生成场景...", "Generating scenes..."),
                        "percent": 15,
                    }
                    self.messages.append({
                        "role": "assistant",
                        "message_kind": "progress",
                        "content": step["step"],
                        "step": step["step"],
                        "percent": step["percent"],
                    })
                    self._save_history()
                    self._save_session_with_progress(step["step"], step["percent"])
                    yield {"type": "progress", **step, "pipeline_stage": self.phase.value}
                    scenes = await service.generate_scenes(chapter, self.draft, contract=contract)
                    new_scene_ids = [s.scene_id for s in scenes]

                    # Step 2: generate background assets
                    step = {
                        "step": _localized_text(lang, "正在生成背景...", "Generating backgrounds..."),
                        "percent": 35,
                    }
                    self.messages.append({
                        "role": "assistant",
                        "message_kind": "progress",
                        "content": step["step"],
                        "step": step["step"],
                        "percent": step["percent"],
                    })
                    self._save_history()
                    self._save_session_with_progress(step["step"], step["percent"])
                    yield {"type": "progress", **step, "pipeline_stage": self.phase.value}
                    bg_assets = await service.generate_background_assets(
                        self.project_name, scenes, round_id=round_id, contract=contract
                    )

                    # Step 3: generate character sprite assets
                    step = {
                        "step": _localized_text(lang, "正在生成角色...", "Generating characters..."),
                        "percent": 55,
                    }
                    self.messages.append({
                        "role": "assistant",
                        "message_kind": "progress",
                        "content": step["step"],
                        "step": step["step"],
                        "percent": step["percent"],
                    })
                    self._save_history()
                    self._save_session_with_progress(step["step"], step["percent"])
                    yield {"type": "progress", **step, "pipeline_stage": self.phase.value}
                    char_assets = await service.generate_character_assets(
                        self.project_name, self.draft, scenes, round_id=round_id, contract=contract
                    )

                    # Step 4: build sprite plans for each scene
                    service.build_sprite_plan(scenes, char_assets, project_name=self.project_name)

                    # Step 5: ensure CJK-safe font configuration
                    cjk_font_config = service.ensure_cjk_font_config(self.project_name, round_id=round_id)

                    # Step 6: write new prototype script to staging file
                    step = {
                        "step": _localized_text(lang, "正在写脚本...", "Writing script..."),
                        "percent": 75,
                    }
                    self.messages.append({
                        "role": "assistant",
                        "message_kind": "progress",
                        "content": step["step"],
                        "step": step["step"],
                        "percent": step["percent"],
                    })
                    self._save_history()
                    self._save_session_with_progress(step["step"], step["percent"])
                    yield {"type": "progress", **step, "pipeline_stage": self.phase.value}
                    staging_path = service.write_script(
                        self.project_name, chapter, scenes,
                        background_assets=bg_assets, character_assets=char_assets,
                        cjk_font_config=cjk_font_config,
                    )
                    final_path = service._final_path_from_staging(staging_path)

                    # Step 7: backup main script before rewiring
                    old_script_content = service.backup_main_script(self.project_name)

                    # Step 8: wire main script to new prototype entry
                    service.wire_main_script_to_prototype(self.project_name, scenes[0].entry_label)

                    # Step 9: write new prototype index entries
                    service.update_index(
                        self.project_name, chapter, scenes, final_path,
                        background_assets=bg_assets, character_assets=char_assets,
                        cjk_font_config=cjk_font_config,
                    )

                    # Step 10: commit
                    step = {
                        "step": _localized_text(lang, "正在提交原型...", "Committing prototype..."),
                        "percent": 90,
                    }
                    self.messages.append({
                        "role": "assistant",
                        "message_kind": "progress",
                        "content": step["step"],
                        "step": step["step"],
                        "percent": step["percent"],
                    })
                    self._save_history()
                    self._save_session_with_progress(step["step"], step["percent"])
                    yield {"type": "progress", **step, "pipeline_stage": self.phase.value}
                    service.commit_prototype_replacement(
                        self.project_name, new_scene_ids, staging_path, round_id=round_id
                    )

                    # Step 10b: update manifest to reflect active single-chapter mode
                    service.activate_single_chapter_prototype(
                        self.project_name,
                        entry_label=scenes[0].entry_label,
                        entry_file=final_path,
                        chapter_ids=[chapter.id],
                        script_files=[final_path],
                    )

                except Exception as e:
                    prototype_error = str(e)
                    logger.exception("Prototype generation failed for project %s", self.project_name)
                    # Rollback partial artifacts
                    try:
                        if self.pm is not None:
                            new_asset_paths: list[str] = []
                            if bg_assets:
                                for info in bg_assets.values():
                                    if info.get("is_new_file") and info.get("path"):
                                        new_asset_paths.append(str(info["path"]))
                            if char_assets:
                                for info in char_assets.values():
                                    if info.get("is_new_file") and info.get("path"):
                                        new_asset_paths.append(info["path"])
                                    if info.get("intermediate_paths"):
                                        new_asset_paths.extend(info["intermediate_paths"])
                            if cjk_font_config:
                                new_asset_paths.extend(cjk_font_config.get("new_files", []))

                            rollback_service = PrototypeGenerationService(self.pm, None)
                            rollback_service.rollback_prototype_generation(
                                self.project_name, staging_path, new_scene_ids, old_script_content,
                                generated_asset_paths=new_asset_paths,
                                round_id=round_id,
                            )
                    except Exception:
                        logger.exception(
                            "Prototype rollback also failed for project %s", self.project_name
                        )

                # Auto-build prototype if generation succeeded
                if not prototype_error and self.pm is not None:
                    try:
                        _write_build_status_for_project(
                            self.project_name,
                            "building",
                            _localized_text(lang, "正在构建可预览原型...", "Building playable prototype..."),
                        )

                        if os.environ.get("RENPY_MCP_MOCK_BUILD"):
                            settings = get_settings()
                            build_dir = (
                                settings.workspace
                                / f"{self.project_name}-dists"
                                / f"{self.project_name}-web"
                            )
                            build_dir.mkdir(parents=True, exist_ok=True)
                            (build_dir / "index.html").write_text(
                                "<html><body>mock preview</body></html>", encoding="utf-8"
                            )
                            build_result = BuildResult(
                                project_name=self.project_name,
                                target="web",
                                success=True,
                                output_path=build_dir,
                            )
                        else:
                            build_manager = BuildManager(get_settings())
                            build_result = await build_manager.build(
                                BuildRequest(project_name=self.project_name, target="web")
                            )

                        if not build_result.success:
                            build_error = build_result.error or _localized_text(
                                lang, "构建失败", "Build failed"
                            )
                            _write_build_status_for_project(
                                self.project_name,
                                "failed",
                                build_error,
                            )
                        else:
                            _write_build_status_for_project(
                                self.project_name,
                                "success",
                                _localized_text(
                                    lang,
                                    f"原型构建完成：{build_result.output_path}",
                                    f"Prototype built to {build_result.output_path}",
                                ),
                                build_result.output_path,
                            )
                    except Exception as e:
                        build_error = str(e)
                        logger.exception("Prototype auto-build failed for project %s", self.project_name)
                        _write_build_status_for_project(
                            self.project_name,
                            "failed",
                            build_error,
                        )

            self.phase = PipelineStage.EDITING

            if prototype_error:
                assistant_content = _localized_text(
                    lang,
                    f"蓝图已保存，但原型生成失败：{prototype_error}",
                    f"Blueprint saved, but prototype generation failed: {prototype_error}",
                )
            elif build_error:
                assistant_content = _localized_text(
                    lang,
                    f"蓝图已保存，原型已生成，但构建失败：{build_error}",
                    f"Blueprint saved, prototype generated, but build failed: {build_error}",
                )
            else:
                assistant_content = _localized_text(
                    lang,
                    "蓝图生成完成！原型已构建完毕，可以预览了。",
                    "Blueprint generation is complete. The prototype is built and ready for preview.",
                )
            self.messages.append({
                "role": "assistant",
                "message_kind": "system",
                "content": assistant_content,
            })
            self._save_history()
            _clear_runtime_session(self.project_name)

            yield {
                "type": "message",
                "role": "assistant",
                "message_kind": "system",
                "content": assistant_content,
                "pipeline_stage": self.phase.value,
            }
            return

        # Rejected -> back to collecting
        self.phase = PipelineStage.COLLECTING
        self.turn_count = 0

        assistant_content = _localized_text(
            lang,
            "好的，我们继续调整蓝图。你希望优先修改角色、章节还是整体基调？",
            "Understood. Let's keep refining the blueprint. Would you like to adjust the characters, the chapter structure, or the overall tone first?",
        )
        self.messages.append({"role": "assistant", "content": assistant_content})
        self._save_history()
        self._save_session()

        yield {
            "type": "message",
            "role": "assistant",
            "message_kind": "text",
            "content": assistant_content,
            "pipeline_stage": self.phase.value,
        }


def _get_orchestrator(project_name: str) -> BlueprintOrchestrator:
    if project_name not in _orchestrators:
        pm = ProjectManager(get_settings())
        _orchestrators[project_name] = BlueprintOrchestrator(project_name, pm)
    return _orchestrators[project_name]


def _should_use_orchestrator(project_name: str, content: str) -> bool:
    """Determine whether the blueprint orchestrator should handle this message.

    Orchestrator is active only for projects that have explicit meta
    (i.e. were created through the new project API) and are in a non-editing
    pipeline stage without a persisted blueprint.
    """
    pm = ProjectManager(get_settings())
    blueprint = pm.read_blueprint(project_name)
    if blueprint is not None:
        return False

    meta = pm.read_project_meta(project_name)
    if meta is None:
        # Legacy project without meta: don't force orchestrator
        return False

    if meta.pipeline_stage in (
        PipelineStage.IDLE,
        PipelineStage.COLLECTING,
        PipelineStage.REVIEWING,
        PipelineStage.GENERATING,
    ):
        return True

    # Also check session file for in-progress states (e.g. after restart)
    session = _load_runtime_session(project_name)
    if session:
        stage = session.get("pipeline_stage")
        if stage in (PipelineStage.IDLE.value, PipelineStage.COLLECTING.value,
                     PipelineStage.REVIEWING.value, PipelineStage.GENERATING.value):
            return True

    return False


def _orchestrator_has_confirmation(project_name: str, confirmation_id: str) -> bool:
    orch = _orchestrators.get(project_name)
    if orch is not None:
        return orch.confirmation_id == confirmation_id
    # Check session file for recovery after restart
    session = _load_runtime_session(project_name)
    if session:
        return (
            session.get("active_workflow") == "blueprint"
            and session.get("confirmation_id") == confirmation_id
        )
    return False


# ---------------------------------------------------------------------------
# System prompt helper
# ---------------------------------------------------------------------------

def _system_prompt_for_current_project(engine: ChatEngine, output_language: str = "zh") -> str:
    """Augment the base prompt with the currently selected project context."""
    base_prompt = getattr(
        engine,
        "system_prompt",
        (
            "You are an AI assistant for Ren'Py visual novel development. "
            "When the user asks about the current workspace, rely on the selected project context."
        ),
    )
    base_prompt = f"{base_prompt}\n\n{_language_instruction(output_language)}"
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

    # Lazy-initialise ChatEngine only when a regular (non-orchestrator) turn is needed.
    engine: ChatEngine | None = None
    provider = None
    messages: list[dict[str, Any]] = []
    sent_message_count = 0

    async def _ensure_engine() -> ChatEngine | None:
        nonlocal engine, provider
        if engine is not None:
            return engine
        provider = _get_provider()
        if provider is None:
            return None
        engine = ChatEngine(mcp=mcp, provider=provider)
        return engine

    async def _send_turn_result(result: dict[str, Any]) -> None:
        """Stream a turn result over the WebSocket."""
        nonlocal sent_message_count
        if result.get("type") == "awaiting_confirmation":
            confirmation = result.get("confirmation", {})
            lang = _preferred_output_language_from_messages(messages)
            tool_name = (
                engine.confirmation.pending.tool_name
                if engine and engine.confirmation.pending
                else None
            )
            confirmation_message = _localized_confirmation_message(
                tool_name,
                lang,
                confirmation.get("message") or "",
            )
            await websocket.send_json(
                {
                    "type": "awaiting_confirmation",
                    "confirmation_id": confirmation.get("confirmation_id"),
                    "message": confirmation_message,
                    "candidates": confirmation.get("candidates", []),
                    "project_name": confirmation.get("project_name"),
                }
            )
            # Persist runtime session for tool workflow recovery
            active_project = _active_project_name(websocket, None)
            if active_project:
                _save_runtime_session(
                    active_project,
                    {
                        "active_workflow": "tool",
                        "pipeline_stage": "awaiting_confirmation",
                        "awaiting_confirmation": True,
                        "confirmation_id": confirmation.get("confirmation_id"),
                        "confirmation_message": confirmation_message,
                        "confirmation_candidates": confirmation.get("candidates", []),
                        "tool_name": tool_name,
                        "project_name": confirmation.get("project_name"),
                        "latest_progress": {
                            "step": _localized_text(
                                lang,
                                f"等待用户确认: {tool_name or '操作'}",
                                f"Waiting for user confirmation: {tool_name or 'action'}",
                            ),
                            "percent": 0,
                        },
                        "updated_at": datetime.utcnow().isoformat(),
                    },
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
                            tool_name = block.get("name", "")
                            lang = _preferred_output_language_from_messages(messages)
                            await websocket.send_json(
                                {
                                    "type": "tool_start",
                                    "tool_name": tool_name,
                                }
                            )
                            active_project = _active_project_name(websocket, None)
                            if active_project:
                                _save_runtime_session(
                                    active_project,
                                    {
                                        "active_workflow": "tool",
                                        "pipeline_stage": "tool_running",
                                        "awaiting_confirmation": False,
                                        "latest_progress": {
                                            "step": _localized_text(
                                                lang,
                                                f"正在调用 {tool_name}...",
                                                f"Calling {tool_name}...",
                                            ),
                                            "percent": 0,
                                        },
                                        "tool_name": tool_name,
                                        "updated_at": datetime.utcnow().isoformat(),
                                    },
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
                            active_project = _active_project_name(websocket, None)
                            if active_project:
                                _clear_runtime_session(active_project)
        sent_message_count = len(result_messages)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": _localized_text(
                            _preferred_output_language_from_messages(messages),
                            "无效的 JSON。",
                            "Invalid JSON.",
                        ),
                    }
                )
                continue

            msg_type = payload.get("type")
            project_name = payload.get("project_name")

            # Refresh project context before handling every message so that
            # subsequent turns pick up a newly-selected project.
            _bind_project_context(websocket, token_holder, project_name)

            if msg_type == "user_message":
                content = payload.get("content", "")
                active_project = _active_project_name(websocket, project_name)

                # --- Blueprint orchestrator path --------------------------------
                if active_project and _should_use_orchestrator(active_project, content):
                    orchestrator = _get_orchestrator(active_project)
                    events = await orchestrator.handle_user_message(content)
                    for event in events:
                        event.setdefault("project_name", active_project)
                        await websocket.send_json(event)
                    _write_chat_history(active_project, orchestrator.messages)
                    continue

                # --- Regular ChatEngine path ------------------------------------
                if _current_project_path.get() is None and not _allowed_without_project(content):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": _localized_text(
                                _preferred_output_language_from_texts([content]),
                                "当前没有选中的项目。",
                                "No active project selected.",
                            ),
                        }
                    )
                    continue

                engine = await _ensure_engine()
                if engine is None:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": _localized_text(
                                _preferred_output_language_from_texts([content]),
                                "未配置可用的 LLM provider。请设置 ANTHROPIC_API_KEY 或 DeepSeek/Qwen 的 API key。",
                                "No LLM provider configured. Set ANTHROPIC_API_KEY or deepseek/qwen API key.",
                            ),
                        }
                    )
                    continue

                messages.append({"role": "user", "content": content})
                engine.system_prompt = _system_prompt_for_current_project(
                    engine,
                    _preferred_output_language_from_messages(messages),
                )
                result = await engine.run_turn(messages)
                await _send_turn_result(result)
                messages = result.get("messages", messages)
                if active_project:
                    _write_chat_history(active_project, messages)

            elif msg_type == "confirmation_response":
                confirmation_id = payload.get("confirmation_id", "")
                approved = payload.get("approved", False)
                active_project = _active_project_name(websocket, project_name)

                # --- Blueprint orchestrator confirmation path -------------------
                if active_project and _orchestrator_has_confirmation(active_project, confirmation_id):
                    orchestrator = _get_orchestrator(active_project)
                    async for event in orchestrator.handle_confirmation_response(approved):
                        await websocket.send_json(event)
                    continue

                # --- Regular ChatEngine confirmation path -----------------------
                engine = await _ensure_engine()
                if engine is None:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": _localized_text(
                                _preferred_output_language_from_messages(messages),
                                "未配置可用的 LLM provider。",
                                "No LLM provider configured.",
                            ),
                        }
                    )
                    continue

                pending = engine.confirmation.pending
                if pending is None or pending.confirmation_id != confirmation_id:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": _localized_text(
                                _preferred_output_language_from_messages(messages),
                                "未找到匹配的待确认操作。",
                                "No matching pending confirmation.",
                            ),
                        }
                    )
                    continue

                # Bind to the project that was active when the confirmation was created,
                # regardless of what the frontend currently thinks the active project is.
                if pending.project_name:
                    _bind_project_context(websocket, token_holder, pending.project_name)

                if approved:
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
                                        _localized_text(
                                            _preferred_output_language_from_messages(messages),
                                            f"已确认并执行工具 {pending.tool_name}。",
                                            f"Tool {pending.tool_name} confirmed and executed.",
                                        ),
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
                                    "content": _localized_text(
                                        _preferred_output_language_from_messages(messages),
                                        f"用户已取消 {pending.tool_name}。",
                                        f"User cancelled {pending.tool_name}.",
                                    ),
                                    "success": False,
                                }
                            ],
                        }
                    )

                # Clear runtime session after confirmation is resolved
                active_project = pending.project_name or _active_project_name(websocket, project_name)
                if active_project:
                    _clear_runtime_session(active_project)

                engine.system_prompt = _system_prompt_for_current_project(
                    engine,
                    _preferred_output_language_from_messages(messages),
                )
                result = await engine.run_turn(messages)
                await _send_turn_result(result)
                messages = result.get("messages", messages)
                active_project = pending.project_name or _active_project_name(websocket, project_name)
                if active_project:
                    _write_chat_history(active_project, messages)
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": _localized_text(
                            _preferred_output_language_from_messages(messages),
                            f"未知的消息类型：{msg_type}",
                            f"Unknown message type: {msg_type}",
                        ),
                    }
                )

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": _localized_text(
                        _preferred_output_language_from_messages(messages),
                        f"服务端错误：{exc}",
                        f"Server error: {exc}",
                    ),
                }
            )
            await websocket.close()
        except Exception:
            pass
    finally:
        if token_holder[0] is not None:
            _current_project_path.reset(token_holder[0])
