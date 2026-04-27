"""WebSocket endpoint for /ws/chat — bridges Dashboard Chat Drawer to ChatEngine."""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..blueprint.models import (
    ChapterIntakeEntry,
    IntakePhase,
    IntakeSlot,
    PipelineStage,
    ProjectBlueprint,
    RefinementIntake,
)
from ..blueprint.outline_derivation import derive_chapter_outline_fields
from ..chat_engine import AnthropicProvider, ChatEngine, OpenAICompatibleProvider
from ..config import get_settings, _current_project_path, resolve_project_dir
from ..server import mcp
from ..services.project_manager import ProjectManager
from .fastapi_app import _write_build_status
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


def _append_refinement_flow_log(project_name: str, level: str, message: str, *args: Any) -> None:
    """Append a diagnostic refinement-flow line to logs/refinement-flow.log."""
    settings = get_settings()
    log_file = settings.workspace / project_name / "logs" / "refinement-flow.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    rendered = message % args if args else message
    line = f"{datetime.utcnow().isoformat()} [{level}] {rendered}\n"
    try:
        with log_file.open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        logger.warning("Failed to append refinement flow log for project %s", project_name)


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


from ..utils.i18n import (
    _contains_cjk,
    _is_clearly_english,
    _language_instruction,
    _localized_confirmation_message,
    _localized_text,
    _preferred_output_language_from_messages,
    _preferred_output_language_from_texts,
    _START_TRIGGERS,
)
from ..utils.json_repair import _extract_json_block, _repair_json_text


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

                # Interview round mock: conclude immediately so tests don't loop forever
                for m in messages:
                    content = m.get("content", "")
                    if isinstance(content, str) and "## Slot State" in content:
                        conclusion_text = (
                            "Interview complete. All required slots are filled.\n"
                            "<CONCLUSION />"
                        )
                        return LLMResponse(
                            content_blocks=[{"type": "text", "text": conclusion_text}],
                            stop_reason="end_turn",
                        )

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

def _build_interview_system_prompt() -> str:
    """Return the system prompt for the LLM-driven adaptive interview."""
    return """\
你是视觉小说项目的创意搭档（creative partner），不是调查问卷填写员。

## 核心职责
帮助作者把模糊的想法变成具体的、可执行的游戏企划。

## 行为准则

### 准则 1: 主动提案
对任何空缺槽位，基于已确定的内容生成 2-4 个有区分度的备选方案。
用 <OPTIONS id="..."> 标签包裹提案内容。每个方案要有独特的定位。

### 准则 2: 降维选择
如果作者说"不确定""没想好""随便"，主动给出该题材最成功的 2-3 种常规做法，
标注推荐理由。把创作决策从"开放式自由创作"降维成"选择题"。

### 准则 3: 交叉检查
每次更新槽位后，检查与其他已填槽位的逻辑一致性。
如果发现矛盾，主动指出并给出两种化解路径。

### 准则 4: 节奏控制
每次只提 1 个话题，给 2-4 个选项。
不要在一条消息里同时讨论视觉风格和角色关系。

### 准则 5: 溯源可溯
每个槽位的值标注来源。
如果用户直接给出了明确答案，不要强行再提案。

## 输出格式
- 提案用 <OPTIONS id="slot_name">...</OPTIONS> 包裹
- 追问用 <QUESTION>...</QUESTION> 包裹
- 槽位更新用 <META>{"slot_updates": {"slot_name": "value"}}</META>
- 所有槽填满且用户确认后输出 <CONCLUSION>

## 绝对不能
- 在作者没参与的情况下替作者做决定
- 只给一个选项
- 跳过必填槽位
"""


def _build_interview_context(slots: dict, proposal_history: list, turn_count: int) -> str:
    """Assemble slot state + proposal history for the LLM interview."""
    lines = [f"Interview turn: {turn_count}/25"]

    lines.append("\n## Current Slots")
    for key, value in slots.items():
        source = None
        display_value = value
        if isinstance(value, dict):
            display_value = value.get("value")
            source = value.get("source")
        if display_value:
            source_suffix = f" ({source})" if source else ""
            lines.append(f"  ✅ {key}: {display_value}{source_suffix}")
        else:
            lines.append(f"  ❌ {key}: (empty)")

    if proposal_history:
        lines.append("\n## Proposal History")
        for p in proposal_history:
            status = p.get("user_choice") or "pending"
            lines.append(
                f"  - {p['proposal_id']} ({p['for_slot']}): "
                f"{', '.join(p.get('options', []))} → {status}"
            )

    if turn_count >= 25:
        lines.append("\n⚠️  Maximum turns reached. Summarize and output <CONCLUSION> now.")

    return "\n".join(lines)


def _message_text_for_interview_history(content: Any) -> str:
    """Extract user-visible text from a stored chat message."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _format_recent_interview_history(
    messages: list[dict[str, Any]],
    *,
    max_messages: int = 8,
    max_chars_per_message: int = 1200,
) -> str:
    """Format recent chat history so the interview LLM can continue coherently."""
    rows: list[str] = []
    for msg in messages[-max_messages:]:
        role = msg.get("role")
        if role not in {"user", "assistant"}:
            continue
        text = _message_text_for_interview_history(msg.get("content")).strip()
        if not text:
            continue
        if len(text) > max_chars_per_message:
            text = text[:max_chars_per_message].rstrip() + "..."
        label = "User" if role == "user" else "Assistant"
        rows.append(f"{label}: {text}")
    return "\n".join(rows)


def _parse_interview_response(response: str) -> dict:
    """Extract structured data from LLM interview response."""
    import re

    result: dict = {
        "options": None,
        "options_id": None,
        "question": None,
        "slot_updates": {},
        "is_conclusion": False,
    }

    # Extract <OPTIONS id="...">...</OPTIONS>
    opt_match = re.search(
        r'<OPTIONS\s+id="([^"]+)"\s*>(.*?)</OPTIONS>',
        response, re.DOTALL
    )
    if opt_match:
        result["options_id"] = opt_match.group(1)
        result["options"] = opt_match.group(2).strip()

    # Extract <QUESTION>...</QUESTION>
    q_match = re.search(r'<QUESTION>(.*?)</QUESTION>', response, re.DOTALL)
    if q_match:
        result["question"] = q_match.group(1).strip()

    # Extract <META>...</META>
    meta_match = re.search(r'<META>(.*?)</META>', response, re.DOTALL)
    if meta_match:
        try:
            meta = json.loads(meta_match.group(1))
            result["slot_updates"] = meta.get("slot_updates", {})
        except json.JSONDecodeError:
            pass

    # Check for <CONCLUSION>
    if "<CONCLUSION" in response:
        result["is_conclusion"] = True

    return result


def _is_user_auto_conclusion_intent(user_message: str) -> bool:
    """Return True when the user wants the assistant to continue autonomously."""
    if not user_message:
        return False

    import re

    message = user_message.lower().strip()
    chinese_patterns = (
        "授权自主决定",
        "剩下你决定",
        "剩下你来",
        "其余你来",
        "你自己决定",
        "你决定吧",
        "你来定吧",
        "后面你来定",
    )
    for phrase in chinese_patterns:
        if phrase in message:
            return True

    # English shorthand where user delegates the rest.
    return bool(re.search(r"\byou\s+decide\b", message) or re.search(r"\bdecide the rest\b", message))


def _display_interview_response(response: str) -> str:
    """Remove internal interview control tags before showing text to users."""
    import re

    text = re.sub(r"<META>.*?</META>", "", response, flags=re.DOTALL)
    text = re.sub(r"<PHASE>.*?</PHASE>", "", text, flags=re.DOTALL)
    text = re.sub(r"</?OPTIONS\b[^>]*>", "", text)
    text = re.sub(r"</?QUESTION>", "", text)
    text = re.sub(r"<CONCLUSION\b[^>]*>", "", text)
    text = re.sub(r"</CONCLUSION>", "", text)

    lines = [line.rstrip() for line in text.splitlines()]
    cleaned = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", cleaned)


def _track_proposal(
    history: list,
    *,
    proposal_id: str,
    for_slot: str,
    options: list[str] | None = None,
    user_choice: str | None = None,
) -> None:
    """Record or update a proposal in the tracking history."""
    for entry in history:
        if entry["proposal_id"] == proposal_id:
            if user_choice is not None:
                entry["user_choice"] = user_choice
            if options is not None:
                entry["options"] = options
            return
    # New proposal
    history.append({
        "proposal_id": proposal_id,
        "for_slot": for_slot,
        "options": options or [],
        "user_choice": user_choice,
    })


def _record_user_choice_for_pending_proposal(history: list, user_message: str) -> None:
    """Attach the latest user response to the oldest pending proposal."""
    choice = (user_message or "").strip()
    if not choice:
        return
    for entry in history:
        if entry.get("user_choice") is None:
            entry["user_choice"] = choice
            return


_orchestrators: dict[str, "BlueprintOrchestrator"] = {}
_orchestrators_lock = asyncio.Lock()

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
        self._current_slots: dict[str, str] = {}
        self._proposal_history: list[dict[str, Any]] = []
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
        if isinstance(session.get("interview_slots"), dict):
            self._current_slots = session["interview_slots"]
        if isinstance(session.get("proposal_history"), list):
            self._proposal_history = session["proposal_history"]
        if session.get("draft"):
            old_draft = self.draft
            try:
                self.draft = ProjectBlueprint(**session["draft"])
            except Exception:
                logger.warning(
                    "Failed to restore draft from session for project %s; keeping previous draft",
                    self.project_name,
                    exc_info=True,
                )
                if old_draft is None:
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
        if self._current_slots:
            state["interview_slots"] = self._current_slots
        if self._proposal_history:
            state["proposal_history"] = self._proposal_history
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
        if self._current_slots:
            state["interview_slots"] = self._current_slots
        if self._proposal_history:
            state["proposal_history"] = self._proposal_history
        if self.draft:
            state["draft"] = self.draft.model_dump(mode="json")
        _save_runtime_session(self.project_name, state)

    def _load_history(self) -> None:
        self.messages = _read_chat_history(self.project_name)

    def _save_history(self) -> None:
        _write_chat_history(self.project_name, self.messages)

    def _project_intake_slot_keys(self) -> list[str]:
        from ..services.refinement_logic import INTAKE_SLOT_KEYS
        return INTAKE_SLOT_KEYS

    def _build_chapter_intake_entry(self, chapter) -> ChapterIntakeEntry:
        total_chapters = len(self.draft.chapters) if self.draft else 1
        fallback_characters = (
            [character.name for character in self.draft.characters if character.name]
            if self.draft
            else None
        )
        fields = derive_chapter_outline_fields(
            chapter,
            total_chapters=total_chapters,
            fallback_character_names=fallback_characters,
        )
        return ChapterIntakeEntry(
            chapter_id=chapter.id,
            order=chapter.order,
            chapter_name=chapter.name,
            **fields,
        )

    def _is_brief_fully_confirmed(self) -> bool:
        """Check whether the project's brief is fully confirmed on disk."""
        try:
            brief = self.pm.read_project_brief(self.project_name)
        except Exception:
            logger.warning(
                "Failed to read project brief for %s",
                self.project_name,
                exc_info=True,
            )
            return False
        if brief is None:
            return False
        from ..services.refinement_logic import is_brief_fully_confirmed
        return is_brief_fully_confirmed(brief)

    def _write_refinement_intake(self, *, latest_user_content: str | None = None) -> RefinementIntake:
        from ..services.refinement_logic import compute_refinement_intake

        brief_confirmed = self._is_brief_fully_confirmed()
        intake = compute_refinement_intake(
            orchestrator_phase=self.phase,
            draft=self.draft,
            brief_confirmed=brief_confirmed,
            latest_user_content=latest_user_content,
        )

        if self.intake_mode and self._current_slots and intake.phase == IntakePhase.PROJECT:
            from ..services.refinement_logic import INTAKE_SLOT_KEYS
            for key in INTAKE_SLOT_KEYS:
                if key not in self._current_slots:
                    continue
                raw = self._current_slots[key]
                if isinstance(raw, dict):
                    value = raw.get("value")
                    source = raw.get("source")
                    if not value:
                        continue
                    intake.slots[key] = IntakeSlot(
                        value=value, complete=bool(value), source=source
                    )
                else:
                    if not raw:
                        continue
                    intake.slots[key] = IntakeSlot(value=raw, complete=bool(raw))

        self.pm.write_refinement_intake(self.project_name, intake)
        if intake.phase == IntakePhase.OUTLINE_READY:
            logger.info(
                "Refinement intake advanced to outline_ready for project %s with %d chapter draft entries",
                self.project_name,
                len(intake.chapter_draft),
            )
            _append_refinement_flow_log(
                self.project_name,
                "INFO",
                "Refinement intake advanced to outline_ready for project %s with %d chapter draft entries",
                self.project_name,
                len(intake.chapter_draft),
            )
        elif intake.phase == IntakePhase.BRIEF_READY:
            logger.info("Refinement intake advanced to brief_ready for project %s", self.project_name)
            _append_refinement_flow_log(
                self.project_name,
                "INFO",
                "Refinement intake advanced to brief_ready for project %s",
                self.project_name,
            )
        elif intake.phase == IntakePhase.CHAPTER:
            logger.info(
                "Refinement intake remains in chapter collecting for project %s (latest_summary=%r)",
                self.project_name,
                intake.current_summary,
            )
            _append_refinement_flow_log(
                self.project_name,
                "INFO",
                "Refinement intake remains in chapter collecting for project %s (latest_summary=%r)",
                self.project_name,
                intake.current_summary,
            )
        return intake

    async def _generate_draft_via_llm(self) -> ProjectBlueprint:
        """Generate a blueprint draft by calling the LLM provider.

        Delegates to BlueprintGenerationService for the actual LLM interaction,
        JSON extraction, repair, and schema validation.
        """
        from ..services.blueprint_generation import BlueprintGenerationService

        provider = _get_provider()
        service = BlueprintGenerationService(provider)
        return await service.generate_draft(
            self.project_name, self.messages,
            intake_mode=self.intake_mode, turn_count=self.turn_count,
        )

    async def _conduct_interview_round(self, user_message: str) -> dict:
        """One round of the LLM-driven adaptive interview."""
        # Build slot state from current intake
        if not hasattr(self, '_current_slots'):
            self._current_slots = {}
        if not hasattr(self, '_proposal_history'):
            self._proposal_history = []

        if self.intake_mode:
            from ..services.refinement_logic import INTAKE_SLOT_KEYS

            for key in INTAKE_SLOT_KEYS:
                self._current_slots.setdefault(key, "")

        _record_user_choice_for_pending_proposal(self._proposal_history, user_message)

        if _is_user_auto_conclusion_intent(user_message):
            return {
                "content": "",
                "is_conclusion": True,
                "slot_updates": {},
            }

        # Update slots from user message (simple heuristic: if user seems to answer a proposal)
        proposal_history = self._proposal_history

        # Build context
        context = _build_interview_context(self._current_slots, proposal_history, self.turn_count)
        system_prompt = _build_interview_system_prompt()
        history_messages = self.messages
        if history_messages:
            last = history_messages[-1]
            if last.get("role") == "user" and _message_text_for_interview_history(last.get("content")).strip() == user_message.strip():
                history_messages = history_messages[:-1]
        recent_history = _format_recent_interview_history(history_messages)

        # Get provider
        provider = _get_provider()
        if provider is None:
            raise RuntimeError("No LLM provider available")

        # Call LLM
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"## Slot State\n{context}\n\n"
                    f"## Recent Conversation\n{recent_history or '(none)'}\n\n"
                    f"## User Message\n{user_message}"
                ),
            },
        ]

        response = await asyncio.to_thread(provider.chat, messages=messages, max_tokens=2048)
        text = response.text if hasattr(response, 'text') else str(response)

        # Parse response
        parsed = _parse_interview_response(text)
        display_text = _display_interview_response(text) or text

        # Apply slot updates from META
        for slot_name, value in parsed["slot_updates"].items():
            self._current_slots[slot_name] = value

        # Track any new proposals
        if parsed["options"] and parsed["options_id"]:
            # Extract option labels from the options text
            option_labels = [
                line.strip() for line in parsed["options"].split("\n")
                if line.strip() and (line.strip()[0].isupper() or "─" in line)
            ]
            if option_labels:
                _track_proposal(
                    self._proposal_history,
                    proposal_id=parsed["options_id"],
                    for_slot=parsed["options_id"],
                    options=option_labels[:4],
                )

        return {
            "content": display_text,
            "is_conclusion": parsed["is_conclusion"],
            "slot_updates": parsed["slot_updates"],
        }

    async def _fallback_generate_draft(self, lang: str) -> list[dict[str, Any]]:
        """Generate draft when interview round fails."""
        try:
            self.draft = await self._generate_draft_via_llm()
        except Exception as exc:
            self.phase = PipelineStage.COLLECTING
            logger.exception("Draft generation failed for project %s", self.project_name)
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

        from ..services.refinement_logic import build_post_draft_result

        intake = self._write_refinement_intake()
        brief_confirmed = self._is_brief_fully_confirmed()
        intake_dump = intake.model_dump(mode="json") if self.intake_mode else None

        post_result = build_post_draft_result(
            self.draft, self.intake_mode, brief_confirmed, lang,
            self.phase.value, intake_dump,
        )
        self.phase = post_result.next_phase
        self.confirmation_id = post_result.confirmation_id
        self.messages.extend(post_result.history_entries)
        self._save_history()
        self._save_session()
        return post_result.ws_events

    async def handle_user_message(self, content: str) -> list[dict[str, Any]]:
        self._load_history()
        lang = _preferred_output_language_from_messages(self.messages)

        from ..services.dev_test_command import (
            dev_test_command_event,
            dev_test_commands_enabled,
            disabled_dev_test_command_event,
            is_dev_test_command,
        )

        if is_dev_test_command(content):
            if not dev_test_commands_enabled():
                event = disabled_dev_test_command_event()
                self.messages.append({"role": "assistant", "message_kind": event["message_kind"], "content": event["content"]})
                self._save_history()
                return [event]
            event = dev_test_command_event(self.project_name, self.pm)
            self.phase = PipelineStage.EDITING
            self.turn_count = 0
            self.draft = self.pm.read_blueprint(self.project_name)
            self.confirmation_id = None
            self.intake_mode = False
            self.messages.append({"role": "assistant", "message_kind": event["message_kind"], "content": event["content"]})
            self._save_history()
            self._save_session()
            return [event]

        # Handle explicit start trigger without consuming a turn
        if (content in _START_TRIGGERS or content in _INTAKE_START_TRIGGERS) and self.turn_count == 0:
            self.intake_mode = content in _INTAKE_START_TRIGGERS
            self.phase = PipelineStage.COLLECTING
            logger.info(
                "Starting blueprint chat workflow for project %s with trigger %s (intake_mode=%s)",
                self.project_name,
                content,
                self.intake_mode,
            )
            _append_refinement_flow_log(
                self.project_name,
                "INFO",
                "Starting blueprint chat workflow for project %s with trigger %s (intake_mode=%s)",
                self.project_name,
                content,
                self.intake_mode,
            )
            from ..services.refinement_logic import select_collecting_response

            assistant_content, message_kind = select_collecting_response(0, self.intake_mode, lang)
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

            # Adaptive interview from the very first user message
            try:
                result = await self._conduct_interview_round(content)
            except Exception as exc:
                logger.warning("Interview round failed, falling back to draft generation: %s", exc)
                return await self._fallback_generate_draft(lang)

            if not result.get("is_conclusion"):
                # Continue interview
                assistant_entry = {"role": "assistant", "content": result["content"]}
                if result.get("message_kind"):
                    assistant_entry["message_kind"] = result["message_kind"]
                self.messages.append(assistant_entry)
                self._save_history()
                self._save_session()
                intake = self._write_refinement_intake(latest_user_content=content)
                event = {
                    "type": "message",
                    "role": "assistant",
                    "content": result["content"],
                    "pipeline_stage": self.phase.value,
                    "intake": intake.model_dump(mode="json") if self.intake_mode else None,
                }
                if result.get("message_kind"):
                    event["message_kind"] = result["message_kind"]
                return [event]

            # Interview conclusion → generate draft
            try:
                logger.info(
                    "Triggering draft generation for project %s after interview conclusion (turn_count=%d, intake_mode=%s)",
                    self.project_name,
                    self.turn_count,
                    self.intake_mode,
                )
                _append_refinement_flow_log(
                    self.project_name,
                    "INFO",
                    "Triggering draft generation for project %s after interview conclusion (turn_count=%d, intake_mode=%s)",
                    self.project_name,
                    self.turn_count,
                    self.intake_mode,
                )
                self.draft = await self._generate_draft_via_llm()
            except Exception as exc:
                self.phase = PipelineStage.COLLECTING
                logger.exception("Draft generation failed for project %s", self.project_name)
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

            from ..services.refinement_logic import build_post_draft_result

            intake = self._write_refinement_intake()
            brief_confirmed = self._is_brief_fully_confirmed()
            intake_dump = intake.model_dump(mode="json") if self.intake_mode else None

            post_result = build_post_draft_result(
                self.draft, self.intake_mode, brief_confirmed, lang,
                self.phase.value, intake_dump,
            )
            self.phase = post_result.next_phase
            self.confirmation_id = post_result.confirmation_id
            self.messages.extend(post_result.history_entries)
            self._save_history()
            self._save_session()
            return post_result.ws_events

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
        Delegates the 10-step prototype pipeline to PrototypeOrchestrationService.
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
            from ..services.refinement_logic import build_first_progress_entry

            first_entry = build_first_progress_entry(lang)
            first_step = {"step": first_entry["step"], "percent": first_entry["percent"]}
            self.messages.append(first_entry)
            self._save_history()
            self._save_session_with_progress(first_step["step"], first_step["percent"])
            yield {"type": "progress", **first_step, "pipeline_stage": self.phase.value}

            # Persist blueprint
            if self.draft:
                await asyncio.to_thread(self.pm.write_blueprint, self.project_name, self.draft)

            # Update meta
            from ..services.refinement_logic import update_project_meta_after_confirmation

            await asyncio.to_thread(
                update_project_meta_after_confirmation,
                self.pm, self.project_name, self.draft,
            )

            # Run prototype generation + auto-build pipeline via service
            prototype_error: str | None = None
            build_error: str | None = None

            if self.draft:
                from ..services.prototype_orchestration import PrototypeOrchestrationService

                pipeline_svc = PrototypeOrchestrationService(self.pm)

                # Collect progress events and yield after pipeline completes,
                # since we can't yield inside the callback.
                progress_events: list[dict] = []

                async def _on_progress_collect(step_text: str, percent: int) -> None:
                    self.messages.append({
                        "role": "assistant",
                        "message_kind": "progress",
                        "content": step_text,
                        "step": step_text,
                        "percent": percent,
                    })
                    self._save_history()
                    self._save_session_with_progress(step_text, percent)
                    progress_events.append({
                        "type": "progress",
                        "step": step_text,
                        "percent": percent,
                        "pipeline_stage": self.phase.value,
                    })

                result = await pipeline_svc.run_pipeline(
                    self.project_name, self.draft,
                    on_progress=_on_progress_collect,
                )

                # Yield collected progress events
                for evt in progress_events:
                    yield evt

                prototype_error = result.prototype_error
                build_error = result.build_error

            self.phase = PipelineStage.EDITING

            from ..services.refinement_logic import select_confirmation_result_message

            assistant_content = select_confirmation_result_message(
                lang, prototype_error, build_error,
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

        from ..services.refinement_logic import select_confirmation_rejection_message

        assistant_content = select_confirmation_rejection_message(lang)
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


async def _get_orchestrator(project_name: str) -> BlueprintOrchestrator:
    if project_name not in _orchestrators:
        async with _orchestrators_lock:
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
                    orchestrator = await _get_orchestrator(active_project)
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
                    orchestrator = await _get_orchestrator(active_project)
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
            logger.debug("WebSocket close after error response failed", exc_info=True)
    finally:
        if token_holder[0] is not None:
            _current_project_path.reset(token_holder[0])
