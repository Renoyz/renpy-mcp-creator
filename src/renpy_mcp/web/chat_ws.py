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
    ChapterSummary,
    PipelineStage,
    ProjectBlueprint,
    ProjectStatus,
    SceneSummary,
)
from ..chat_engine import AnthropicProvider, ChatEngine, OpenAICompatibleProvider
from ..config import get_settings, _current_project_path, resolve_project_dir
from ..server import mcp
from ..services.project_manager import ProjectManager
from ..services.prototype_generation_service import PrototypeGenerationService

router = APIRouter()

logger = logging.getLogger(__name__)


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
                    return LLMResponse(
                        content_blocks=[{"type": "text", "text": json.dumps(blueprint, ensure_ascii=False)}],
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

    # Primary: Anthropic-compatible (Kimi Code)
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY") or settings.anthropic_api_key
    anthropic_base = os.environ.get("ANTHROPIC_BASE_URL", "https://api.kimi.com/coding/")
    anthropic_model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet")
    if anthropic_key:
        return AnthropicProvider(
            api_key=anthropic_key,
            base_url=anthropic_base,
            default_model=anthropic_model,
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
        if content in _START_TRIGGERS and self.turn_count == 0:
            self.phase = PipelineStage.COLLECTING
            assistant_content = _localized_text(
                lang,
                "太好了！让我来帮你把这个想法变成完整的蓝图。首先，你希望这个故事大概有几章？有没有特别想设定的主角人设或故事基调？",
                "Great. I'll help turn this idea into a complete blueprint. To start, roughly how many chapters do you want, and are there any specific protagonist traits or story tone you want to establish?",
            )
            self.messages.append({"role": "assistant", "content": assistant_content})
            self._save_history()
            self._save_session()
            return [
                {
                    "type": "message",
                    "role": "assistant",
                    "message_kind": "text",
                    "content": assistant_content,
                    "pipeline_stage": self.phase.value,
                }
            ]

        self.messages.append({"role": "user", "content": content})
        self.turn_count += 1
        lang = _preferred_output_language_from_messages(self.messages)

        if self.phase in (PipelineStage.IDLE, PipelineStage.COLLECTING):
            self.phase = PipelineStage.COLLECTING

            if self.turn_count < 2:
                if self.turn_count == 1:
                    assistant_content = _localized_text(
                        lang,
                        "收到。为了生成更准确的蓝图，请补充一下：\n1. 世界观或时代背景\n2. 核心角色（1-3位）\n3. 你希望的游戏时长",
                        "Got it. To generate a more accurate blueprint, please add:\n1. The setting or historical era\n2. The core cast (1-3 characters)\n3. The playtime you want for the game",
                    )
                else:
                    assistant_content = _localized_text(
                        lang,
                        "很好。接下来我会用这些信息为你生成一份结构化的项目蓝图。确认后，我们会进入分章生成。\n\n请再简单描述一下游戏的整体氛围（例如：轻松、悬疑、治愈）。",
                        "Good. Next I will use this information to generate a structured project blueprint. After you confirm it, we'll move on to chapter generation.\n\nPlease briefly describe the overall mood of the game as well, for example: lighthearted, suspenseful, or healing.",
                    )

                self.messages.append({"role": "assistant", "content": assistant_content})
                self._save_history()
                self._save_session()
                return [
                    {
                        "type": "message",
                        "role": "assistant",
                        "message_kind": "text",
                        "content": assistant_content,
                        "pipeline_stage": self.phase.value,
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

    async def handle_confirmation_response(self, approved: bool) -> list[dict[str, Any]]:
        self._load_history()
        lang = _preferred_output_language_from_messages(self.messages)

        if self.phase != PipelineStage.REVIEWING:
            return [
                {
                    "type": "error",
                    "message": _localized_text(
                        lang,
                        "当前没有待确认的蓝图草案。",
                        "There is no blueprint draft waiting for confirmation right now.",
                    ),
                    "pipeline_stage": self.phase.value,
                }
            ]

        if approved:
            self.phase = PipelineStage.GENERATING

            steps = [
                {"step": _localized_text(lang, "正在分析创作意图...", "Analyzing your creative goals..."), "percent": 10},
                {"step": _localized_text(lang, "正在设计角色设定...", "Designing the character roster..."), "percent": 30},
                {"step": _localized_text(lang, "正在构建章节大纲...", "Building the chapter outline..."), "percent": 55},
                {"step": _localized_text(lang, "正在编排场景结构...", "Structuring the scene flow..."), "percent": 80},
                {"step": _localized_text(lang, "正在完善分支与结局...", "Polishing branches and endings..."), "percent": 95},
            ]

            events: list[dict[str, Any]] = []
            for step in steps:
                events.append(
                    {"type": "progress", **step, "pipeline_stage": self.phase.value}
                )
                self.messages.append({
                    "role": "assistant",
                    "message_kind": "progress",
                    "content": step["step"],
                    "step": step["step"],
                    "percent": step["percent"],
                })
                self._save_history()
                self._save_session_with_progress(step["step"], step["percent"])
                await asyncio.sleep(0.6)

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

            # Generate prototype scenes and script
            prototype_error: str | None = None
            script_path: str | None = None
            new_scene_ids: list[str] = []
            if self.draft:
                try:
                    provider = _get_provider()
                    service = PrototypeGenerationService(self.pm, provider)
                    chapter = service.select_prototype_chapter(self.draft)
                    service.remove_existing_prototype_artifacts(self.project_name)
                    scenes = await service.generate_scenes(chapter, self.draft)
                    new_scene_ids = [s.scene_id for s in scenes]
                    script_path = service.write_script(self.project_name, chapter, scenes)
                    service.wire_main_script_to_prototype(self.project_name, scenes[0].entry_label)
                    service.update_index(self.project_name, chapter, scenes, script_path)
                except Exception as e:
                    prototype_error = str(e)
                    logger.exception("Prototype generation failed for project %s", self.project_name)
                    # Clean up partial artifacts from this failed round
                    try:
                        if self.pm is not None:
                            cleanup_service = PrototypeGenerationService(self.pm, None)
                            cleanup_service.cleanup_failed_prototype_artifacts(
                                self.project_name, script_path, new_scene_ids
                            )
                    except Exception:
                        logger.exception(
                            "Prototype cleanup also failed for project %s", self.project_name
                        )

            self.phase = PipelineStage.EDITING

            if prototype_error:
                assistant_content = _localized_text(
                    lang,
                    f"蓝图已保存，但原型生成失败：{prototype_error}",
                    f"Blueprint saved, but prototype generation failed: {prototype_error}",
                )
            else:
                assistant_content = _localized_text(
                    lang,
                    "蓝图生成完成！原型也已就绪，你现在可以在工作区中查看和编辑。",
                    "Blueprint generation is complete. The prototype is ready, and you can now review and edit it in the workspace.",
                )
            self.messages.append({
                "role": "assistant",
                "message_kind": "system",
                "content": assistant_content,
            })
            self._save_history()
            _clear_runtime_session(self.project_name)

            events.append(
                {
                    "type": "message",
                    "role": "assistant",
                    "message_kind": "system",
                    "content": assistant_content,
                    "pipeline_stage": self.phase.value,
                }
            )
            return events

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

        return [
            {
                "type": "message",
                "role": "assistant",
                "message_kind": "text",
                "content": assistant_content,
                "pipeline_stage": self.phase.value,
            }
        ]


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
                    events = await orchestrator.handle_confirmation_response(approved)
                    for i, event in enumerate(events):
                        await websocket.send_json(event)
                        # Stagger progress events so the frontend has time to render each stage.
                        if i < len(events) - 1 and event.get("type") == "progress":
                            await asyncio.sleep(0.6)
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
