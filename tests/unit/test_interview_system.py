"""TDD: adaptive interview system prompt and context builder."""
import pytest


# ---------------------------------------------------------------------------
# 1a. System prompt contains the 5 rules
# ---------------------------------------------------------------------------

def test_interview_system_prompt_contains_five_rules():
    """System prompt must include all 5 behavioral rules."""
    from renpy_mcp.web.chat_ws import _build_interview_system_prompt

    prompt = _build_interview_system_prompt()
    assert "主动提案" in prompt or "propose options" in prompt.lower()
    assert "降维" in prompt or "选择题" in prompt or "guidance" in prompt.lower()
    assert "交叉检查" in prompt or "cross-check" in prompt.lower() or "consistency" in prompt.lower()
    assert "节奏" in prompt or "pace" in prompt.lower() or "one topic" in prompt.lower()
    assert "溯源" in prompt or "source" in prompt.lower() or "user_specified" in prompt


def test_interview_system_prompt_mentions_conclusion_tag():
    """Prompt must instruct LLM to use <CONCLUSION> when done."""
    from renpy_mcp.web.chat_ws import _build_interview_system_prompt

    prompt = _build_interview_system_prompt()
    assert "<CONCLUSION>" in prompt


def test_interview_system_prompt_forbids_single_option():
    """Prompt must forbid giving only one option."""
    from renpy_mcp.web.chat_ws import _build_interview_system_prompt

    prompt = _build_interview_system_prompt()
    assert "one option" in prompt.lower() or "single option" in prompt.lower() or "只给一个" in prompt or "只提供一种" in prompt or "2-4" in prompt or "2～4" in prompt


# ---------------------------------------------------------------------------
# 1b. Context builder correctly formats slot state
# ---------------------------------------------------------------------------

def test_context_builder_shows_filled_and_empty_slots():
    """Context must distinguish filled (✅) from empty (❌) slots."""
    from renpy_mcp.web.chat_ws import _build_interview_context

    slots = {
        "core_premise": "明朝悬疑",
        "audience_genre": "",
        "tone_themes": "",
    }
    proposal_history: list = []

    ctx = _build_interview_context(slots, proposal_history, turn_count=3)
    assert "core_premise" in ctx
    assert "明朝悬疑" in ctx
    # Empty slots should be marked
    assert "audience_genre" in ctx
    assert "tone_themes" in ctx
    assert "3" in ctx or "turn" in ctx.lower()


def test_context_builder_includes_proposal_history():
    """Context must include pending proposals so LLM doesn't repeat them."""
    from renpy_mcp.web.chat_ws import _build_interview_context

    slots = {"core_premise": "test"}
    proposal_history = [
        {
            "proposal_id": "vs_001",
            "for_slot": "visual_style",
            "options": ["A. 水墨", "B. 工笔"],
            "user_choice": None,
        }
    ]
    ctx = _build_interview_context(slots, proposal_history, turn_count=5)
    assert "vs_001" in ctx or "visual_style" in ctx


def test_context_builder_limits_to_25_turns():
    """After 25 turns, context must signal forced conclusion."""
    from renpy_mcp.web.chat_ws import _build_interview_context

    ctx = _build_interview_context({"core_premise": "test"}, [], turn_count=25)
    assert "25" in ctx or "final" in ctx.lower() or "summarize" in ctx.lower() or "汇总" in ctx or "总结" in ctx


@pytest.mark.asyncio
async def test_interview_round_context_includes_all_required_slots_when_empty(tmp_path, monkeypatch):
    """The first adaptive interview round must show every required intake slot as empty."""
    from renpy_mcp.config import Settings
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.services.refinement_logic import INTAKE_SLOT_KEYS
    from renpy_mcp.web.chat_ws import BlueprintOrchestrator, PipelineStage
    from renpy_mcp.chat_engine.providers import LLMResponse

    captured: dict[str, str] = {}

    class FakeProvider:
        def chat(self, messages, **kwargs):
            captured["prompt"] = messages[-1]["content"]
            return LLMResponse(
                content_blocks=[{"type": "text", "text": "<QUESTION>继续？</QUESTION><META>{\"slot_updates\": {}}</META>"}],
                stop_reason="end_turn",
            )

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: FakeProvider())
    monkeypatch.setattr("renpy_mcp.web.chat_ws._load_runtime_session", lambda project_name: None)
    settings = Settings().model_copy(update={"workspace": tmp_path / "workspace"})
    pm = ProjectManager(settings)
    pm.ensure_project_dir("slot_context")

    orchestrator = BlueprintOrchestrator("slot_context", pm)
    orchestrator.phase = PipelineStage.COLLECTING
    orchestrator.intake_mode = True
    orchestrator.turn_count = 1

    await orchestrator._conduct_interview_round("我想做明朝悬疑")

    prompt = captured["prompt"]
    for key in INTAKE_SLOT_KEYS:
        assert key in prompt
    assert prompt.count("(empty)") >= len(INTAKE_SLOT_KEYS)


@pytest.mark.asyncio
async def test_interview_round_sends_recent_conversation_history_to_llm(tmp_path, monkeypatch):
    """Adaptive interview turns must include prior chat context, not only the latest user text."""
    from renpy_mcp.config import Settings
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.web.chat_ws import BlueprintOrchestrator, PipelineStage
    from renpy_mcp.chat_engine.providers import LLMResponse

    captured: dict[str, str] = {}

    class FakeProvider:
        def chat(self, messages, **kwargs):
            captured["prompt"] = messages[-1]["content"]
            return LLMResponse(
                content_blocks=[{"type": "text", "text": "<QUESTION>Next?</QUESTION><META>{\"slot_updates\": {}}</META>"}],
                stop_reason="end_turn",
            )

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: FakeProvider())
    monkeypatch.setattr("renpy_mcp.web.chat_ws._load_runtime_session", lambda project_name: None)
    settings = Settings().model_copy(update={"workspace": tmp_path / "workspace"})
    pm = ProjectManager(settings)
    pm.ensure_project_dir("history_context")

    orchestrator = BlueprintOrchestrator("history_context", pm)
    orchestrator.phase = PipelineStage.COLLECTING
    orchestrator.intake_mode = True
    orchestrator.turn_count = 2
    orchestrator.messages = [
        {"role": "assistant", "content": "Opening: share any story idea."},
        {"role": "user", "content": "Ming dynasty vampire story"},
        {"role": "assistant", "content": "Option A: court horror. Option B: river trade mystery."},
        {"role": "user", "content": "Use option A but keep the vampire identity secret."},
    ]

    await orchestrator._conduct_interview_round("Use option A but keep the vampire identity secret.")

    prompt = captured["prompt"]
    assert "## Recent Conversation" in prompt
    assert "Opening: share any story idea." in prompt
    assert "Ming dynasty vampire story" in prompt
    assert "Option A: court horror" in prompt
    assert "## User Message" in prompt
    assert "Use option A but keep the vampire identity secret." in prompt


# ---------------------------------------------------------------------------
# 2a. Response parser extracts structured tags
# ---------------------------------------------------------------------------

def test_parse_interview_response_extracts_options_tag():
    """Parser extracts OPTIONS block content."""
    from renpy_mcp.web.chat_ws import _parse_interview_response

    response = """<PHASE>tone_style</PHASE>
<OPTIONS id="visual_style">
## Visual Style Options
A. 水墨暗调 — dark ink wash style
B. 工笔重彩 — detailed brushwork
</OPTIONS>
<QUESTION>Which direction?</QUESTION>
<META>{"slot_updates": {}}</META>"""

    parsed = _parse_interview_response(response)
    assert parsed["options"] is not None
    assert "visual_style" in parsed["options_id"] or "visual_style" in str(parsed["options"])
    assert parsed["question"] == "Which direction?"


def test_parse_interview_response_extracts_meta_slot_updates():
    """Parser extracts slot_updates from META JSON."""
    from renpy_mcp.web.chat_ws import _parse_interview_response

    response = """<OPTIONS id="test">options here</OPTIONS>
<META>{"slot_updates": {"tone_themes": "dark, suspenseful"}}</META>"""

    parsed = _parse_interview_response(response)
    assert parsed["slot_updates"] == {"tone_themes": "dark, suspenseful"}


def test_parse_interview_response_detects_conclusion():
    """Parser detects <CONCLUSION> tag."""
    from renpy_mcp.web.chat_ws import _parse_interview_response

    response = """All slots are filled. Here is the summary.
<CONCLUSION />"""

    parsed = _parse_interview_response(response)
    assert parsed["is_conclusion"] is True


def test_parse_interview_response_handles_missing_tags():
    """Parser returns safe defaults when no tags present."""
    from renpy_mcp.web.chat_ws import _parse_interview_response

    response = "Just a normal chat message, no tags here."
    parsed = _parse_interview_response(response)
    assert parsed["options"] is None
    assert parsed["slot_updates"] == {}
    assert parsed["is_conclusion"] is False


def test_display_interview_response_strips_internal_control_tags():
    """Users should see natural interview text, not internal OPTIONS/META wrappers."""
    from renpy_mcp.web.chat_ws import _display_interview_response

    response = '''<OPTIONS id="core_premise">
Option A: court horror
Option B: river trade mystery
</OPTIONS>
<QUESTION>Which direction do you prefer?</QUESTION>
<META>{"slot_updates": {"core_premise": "Ming vampire story"}}</META>'''

    display = _display_interview_response(response)

    assert "<OPTIONS" not in display
    assert "</OPTIONS>" not in display
    assert "<QUESTION>" not in display
    assert "<META>" not in display
    assert "Option A: court horror" in display
    assert "Which direction do you prefer?" in display
    assert "slot_updates" not in display


@pytest.mark.asyncio
async def test_interview_round_returns_display_content_without_control_tags(tmp_path, monkeypatch):
    """Interview parsing should use raw provider text, but returned chat content should be display-safe."""
    from renpy_mcp.config import Settings
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.web.chat_ws import BlueprintOrchestrator, PipelineStage
    from renpy_mcp.chat_engine.providers import LLMResponse

    class FakeProvider:
        def chat(self, messages, **kwargs):
            return LLMResponse(
                content_blocks=[{
                    "type": "text",
                    "text": '''<OPTIONS id="core_premise">
Option A: court horror
</OPTIONS>
<META>{"slot_updates": {"core_premise": "Ming vampire story"}}</META>''',
                }],
                stop_reason="end_turn",
            )

    monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: FakeProvider())
    monkeypatch.setattr("renpy_mcp.web.chat_ws._load_runtime_session", lambda project_name: None)
    settings = Settings().model_copy(update={"workspace": tmp_path / "workspace"})
    pm = ProjectManager(settings)
    pm.ensure_project_dir("display_safe")

    orchestrator = BlueprintOrchestrator("display_safe", pm)
    orchestrator.phase = PipelineStage.COLLECTING
    orchestrator.intake_mode = True
    orchestrator.turn_count = 1

    result = await orchestrator._conduct_interview_round("Ming vampire story")

    assert result["content"] == "Option A: court horror"
    assert result["slot_updates"] == {"core_premise": "Ming vampire story"}


# ---------------------------------------------------------------------------
# 2b. Proposal tracking
# ---------------------------------------------------------------------------

def test_track_proposal_records_options_and_slot():
    """Proposal is tracked with id, slot, options, and pending status."""
    from renpy_mcp.web.chat_ws import _track_proposal

    history: list = []
    _track_proposal(history, proposal_id="vs_001", for_slot="visual_style",
                    options=["A. 水墨", "B. 工笔", "C. 浮世绘"])
    assert len(history) == 1
    assert history[0]["proposal_id"] == "vs_001"
    assert history[0]["for_slot"] == "visual_style"
    assert history[0]["user_choice"] is None  # pending


def test_track_proposal_updates_existing():
    """Updating an existing proposal sets user_choice."""
    from renpy_mcp.web.chat_ws import _track_proposal

    history = [{"proposal_id": "vs_001", "for_slot": "visual_style",
                "options": ["A", "B"], "user_choice": None}]
    _track_proposal(history, proposal_id="vs_001", for_slot="visual_style",
                    user_choice="A")
    assert history[0]["user_choice"] == "A"


# ---------------------------------------------------------------------------
# 3. Interview round integration
# ---------------------------------------------------------------------------

def test_collecting_phase_uses_adaptive_interview_without_legacy_env_flag():
    """Default collecting flow must use adaptive interview, not a legacy env-gated path."""
    import inspect
    from renpy_mcp.web.chat_ws import BlueprintOrchestrator

    source = inspect.getsource(BlueprintOrchestrator.handle_user_message)
    assert "_conduct_interview_round" in source, \
        "handle_user_message must delegate to interview loop"
    assert "RENPY_MCP_LEGACY_INTAKE" not in source, \
        "RENPY_MCP_LEGACY_INTAKE must not exist in production code"
    assert "legacy_mode" not in source, \
        "legacy_mode must not exist in production code"


# ---------------------------------------------------------------------------
# 3a. Default path calls interview (spy test)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_collecting_user_message_calls_adaptive_interview_by_default(tmp_path, monkeypatch):
    """Collecting phase must call _conduct_interview_round by default, no legacy flag."""
    from renpy_mcp.config import get_settings
    from renpy_mcp.web.chat_ws import BlueprintOrchestrator, PipelineStage
    from renpy_mcp.services.project_manager import ProjectManager

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)
    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._read_chat_history",
        lambda project_name: [],
    )
    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._write_chat_history",
        lambda project_name, messages: None,
    )
    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._load_runtime_session",
        lambda project_name: None,
    )
    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._save_runtime_session",
        lambda project_name, state: None,
    )
    pm = ProjectManager(settings)
    calls = []

    async def fake_interview(self, user_message):
        calls.append(user_message)
        return {
            "content": "Adaptive question",
            "is_conclusion": False,
            "slot_updates": {},
        }

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws.BlueprintOrchestrator._write_refinement_intake",
        lambda self, latest_user_content=None: type("Intake", (), {"model_dump": lambda self, mode=None: {}})(),
    )
    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws.BlueprintOrchestrator._conduct_interview_round",
        fake_interview,
    )

    orchestrator = BlueprintOrchestrator("adaptive_default", pm)
    orchestrator.phase = PipelineStage.COLLECTING
    orchestrator.intake_mode = True

    events = await orchestrator.handle_user_message("我想做明朝悬疑")

    assert calls == ["我想做明朝悬疑"]
    assert events[0]["type"] == "message"
    assert events[0]["content"] == "Adaptive question"


# ---------------------------------------------------------------------------
# 4. IntakeSlot source field
# ---------------------------------------------------------------------------

def test_intake_slot_accepts_optional_source():
    from renpy_mcp.blueprint.models import IntakeSlot

    slot = IntakeSlot(value="水墨暗调", complete=True, source="user_specified")

    assert slot.source == "user_specified"
    assert slot.model_dump()["source"] == "user_specified"


# ---------------------------------------------------------------------------
# 5. LLM slot updates written to refinement_intake.json
# ---------------------------------------------------------------------------

def test_write_refinement_intake_uses_interview_slot_updates(tmp_path, monkeypatch):
    from renpy_mcp.blueprint.models import IntakeSlot
    from renpy_mcp.config import Settings
    from renpy_mcp.web.chat_ws import BlueprintOrchestrator
    from renpy_mcp.services.project_manager import ProjectManager

    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._load_runtime_session",
        lambda project_name: None,
    )
    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._save_runtime_session",
        lambda project_name, state: None,
    )

    settings = Settings().model_copy(update={"workspace": tmp_path / "workspace"})
    pm = ProjectManager(settings)
    pm.ensure_project_dir("tier3_slots")

    orchestrator = BlueprintOrchestrator("tier3_slots", pm)
    orchestrator.intake_mode = True
    orchestrator._current_slots = {
        "core_premise": {
            "value": "明朝悬疑",
            "source": "user_specified",
        },
        "visual_style": {
            "value": "水墨暗调",
            "source": "system_recommended",
        },
    }

    intake = orchestrator._write_refinement_intake()

    assert intake.slots["core_premise"].value == "明朝悬疑"
    assert intake.slots["core_premise"].complete is True
    assert intake.slots["core_premise"].source == "user_specified"
    assert intake.slots["visual_style"].value == "水墨暗调"
    assert intake.slots["visual_style"].source == "system_recommended"


def test_empty_interview_slots_do_not_overwrite_latest_user_content(tmp_path, monkeypatch):
    from renpy_mcp.config import Settings
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.services.refinement_logic import INTAKE_SLOT_KEYS
    from renpy_mcp.web.chat_ws import BlueprintOrchestrator

    monkeypatch.setattr("renpy_mcp.web.chat_ws._load_runtime_session", lambda project_name: None)
    monkeypatch.setattr("renpy_mcp.web.chat_ws._save_runtime_session", lambda project_name, state: None)

    settings = Settings().model_copy(update={"workspace": tmp_path / "workspace"})
    pm = ProjectManager(settings)
    pm.ensure_project_dir("empty_slots")

    orchestrator = BlueprintOrchestrator("empty_slots", pm)
    orchestrator.intake_mode = True
    orchestrator._current_slots = {key: "" for key in INTAKE_SLOT_KEYS}

    intake = orchestrator._write_refinement_intake(latest_user_content="明朝悬疑")

    assert intake.slots["core_premise"].value == "明朝悬疑"
    assert intake.slots["core_premise"].complete is True


# ---------------------------------------------------------------------------
# 6. Pending proposal user choice recording
# ---------------------------------------------------------------------------

def test_pending_proposal_records_next_user_choice():
    from renpy_mcp.web.chat_ws import _record_user_choice_for_pending_proposal

    history = [
        {
            "proposal_id": "visual_style",
            "for_slot": "visual_style",
            "options": ["A. 水墨", "B. 工笔"],
            "user_choice": None,
        }
    ]

    _record_user_choice_for_pending_proposal(history, "A 和 B 结合")

    assert history[0]["user_choice"] == "A 和 B 结合"


# ---------------------------------------------------------------------------
# 7. Parser preserves nested slot source info
# ---------------------------------------------------------------------------

def test_parse_interview_response_preserves_slot_sources():
    from renpy_mcp.web.chat_ws import _parse_interview_response

    response = '''<META>{
  "slot_updates": {
    "visual_style": {
      "value": "水墨暗调",
      "source": "system_recommended"
    }
  }
}</META>
'''

    parsed = _parse_interview_response(response)

    assert parsed["slot_updates"]["visual_style"]["value"] == "水墨暗调"
    assert parsed["slot_updates"]["visual_style"]["source"] == "system_recommended"


# ---------------------------------------------------------------------------
# 8. Interview runtime session persistence
# ---------------------------------------------------------------------------

def test_interview_slots_and_proposal_history_roundtrip_runtime_session(monkeypatch):
    from renpy_mcp.config import Settings
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.web.chat_ws import BlueprintOrchestrator

    saved: dict = {}

    monkeypatch.setattr("renpy_mcp.web.chat_ws._load_runtime_session", lambda project_name: None)
    monkeypatch.setattr(
        "renpy_mcp.web.chat_ws._save_runtime_session",
        lambda project_name, state: saved.update(state),
    )

    settings = Settings()
    pm = ProjectManager(settings)
    orchestrator = BlueprintOrchestrator("persist_interview", pm)
    orchestrator.intake_mode = True
    orchestrator._current_slots = {
        "core_premise": {"value": "明朝悬疑", "source": "user_specified"},
    }
    orchestrator._proposal_history = [
        {
            "proposal_id": "visual_style",
            "for_slot": "visual_style",
            "options": ["A. 水墨", "B. 工笔"],
            "user_choice": "A",
        }
    ]

    orchestrator._save_session()

    assert saved["interview_slots"] == orchestrator._current_slots
    assert saved["proposal_history"] == orchestrator._proposal_history

    monkeypatch.setattr("renpy_mcp.web.chat_ws._load_runtime_session", lambda project_name: saved)
    restored = BlueprintOrchestrator("persist_interview", pm)

    assert restored._current_slots == orchestrator._current_slots
    assert restored._proposal_history == orchestrator._proposal_history
