# Kimi 执行 — 自适应摄入对话 v1 (TDD)

**目标**: 将硬编码的 2 轮固定提问替换为 LLM 驱动的"创意搭档"自适应访谈循环。

**设计方**: Claude/DeepSeek
**执行方**: Kimi
**方法论**: TDD — RED → GREEN → REFACTOR

---

## 前置条件

```bash
cd <repository-root>
python -m pytest tests/integration/test_ws_chat_blueprint.py -x -q
# 预期: 41 PASS (基线)
```

---

## Step 1: 创意搭档系统提示词 + 上下文构建器

### 🔴 RED

**新建文件**: `tests/unit/test_interview_system.py`

```python
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
    prompt = _build_interview_system_prompt()
    assert "<CONCLUSION>" in prompt


def test_interview_system_prompt_forbids_single_option():
    """Prompt must forbid giving only one option."""
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
```

运行:
```bash
python -m pytest tests/unit/test_interview_system.py -v
# 必须 ALL FAIL — 三个函数都不存在
```

### 🟢 GREEN

**文件**: `src/renpy_mcp/web/chat_ws.py`

在 `BlueprintOrchestrator` 类中新增以下方法（放在 `_generate_draft_via_llm` 之前，约 line 770）:

#### 1a. `_build_interview_system_prompt()` (静态/独立函数)

```python
INTERVIEW_SYSTEM_PROMPT = """\
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
```

#### 1b. `_build_interview_context()` 方法

```python
def _build_interview_context(self, slots: dict, proposal_history: list, turn_count: int) -> str:
    """Assemble slot state + proposal history for the LLM interview."""
    lines = [f"Interview turn: {turn_count}/25"]

    lines.append("\n## Current Slots")
    for key, value in slots.items():
        if value:
            lines.append(f"  ✅ {key}: {value}")
        else:
            lines.append(f"  ❌ {key}: (empty)")

    if proposal_history:
        lines.append("\n## Proposal History")
        for p in proposal_history:
            status = p.get("user_choice") or "pending"
            lines.append(f"  - {p['proposal_id']} ({p['for_slot']}): "
                        f"{', '.join(p.get('options', []))} → {status}")

    if turn_count >= 25:
        lines.append("\n⚠️  Maximum turns reached. Summarize and output <CONCLUSION> now.")

    return "\n".join(lines)
```

### ✅ 验证

```bash
python -m pytest tests/unit/test_interview_system.py -v  # 6 PASS
python -m pytest tests/integration/test_ws_chat_blueprint.py -x -q  # 无回归
```

---

## Step 2: 响应解析器 + 提案追踪

### 🔴 RED

**追加到** `tests/unit/test_interview_system.py`:

```python
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
```

运行:
```bash
python -m pytest tests/unit/test_interview_system.py -v -k "parse or track"
# 必须 ALL FAIL — 函数不存在
```

### 🟢 GREEN

**文件**: `src/renpy_mcp/web/chat_ws.py`

在 `BlueprintOrchestrator` 类中新增:

```python
@staticmethod
def _parse_interview_response(response: str) -> dict:
    """Extract structured data from LLM interview response."""
    import re
    import json

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


@staticmethod
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
```

### ✅ 验证

```bash
python -m pytest tests/unit/test_interview_system.py -v  # ALL 12 PASS
python -m pytest tests/integration/test_ws_chat_blueprint.py -x -q  # 无回归
```

---

## Step 3: 主循环 — 替换硬编码 turn dispatch

### 🔴 RED

**追加到** `tests/unit/test_interview_system.py`:

```python
# ---------------------------------------------------------------------------
# 3. Interview round integration
# ---------------------------------------------------------------------------

def test_collecting_phase_does_not_use_turn_count_dispatch():
    """In COLLECTING phase, the old turn_count branching is replaced by _conduct_interview_round."""
    import inspect
    from renpy_mcp.web.chat_ws import BlueprintOrchestrator

    source = inspect.getsource(BlueprintOrchestrator.handle_user_message)
    assert "_conduct_interview_round" in source, \
        "handle_user_message must delegate to interview loop"
    # Verify old pattern is gone
    assert "turn_count < 2" not in source or "select_collecting_response" not in source, \
        "Old hardcoded turn dispatch must be removed — interview is LLM-driven from turn 0"
```

运行:
```bash
python -m pytest tests/unit/test_interview_system.py::test_collecting_phase_does_not_use_turn_count_dispatch -v
# 必须 FAIL — 旧代码仍在使用 turn_count < 2 + select_collecting_response
```

### 🟢 GREEN

**文件**: `src/renpy_mcp/web/chat_ws.py` — `handle_user_message()` 方法

修改 line 700-720 的逻辑块。当前:
```python
if self.phase in (PipelineStage.IDLE, PipelineStage.COLLECTING):
    self.phase = PipelineStage.COLLECTING
    if self.turn_count < 2:
        # hardcoded question from select_collecting_response()
        ...
        return [...]
    # turn_count >= 2 → generate draft
```

替换为 —— **从 turn 0 就直接进 LLM 自适应访谈**：
```python
if self.phase in (PipelineStage.IDLE, PipelineStage.COLLECTING):
    self.phase = PipelineStage.COLLECTING

    # LLM-driven adaptive interview from the very first user message
    try:
        result = await self._conduct_interview_round(content)
    except Exception as exc:
        logger.warning("Interview round failed, falling back to draft generation: %s", exc)
        result = await self._fallback_generate_draft(lang)

    if result.get("is_conclusion"):
        # Interview complete → generate final draft
        try:
            self.draft = await self._generate_draft_via_llm()
        except Exception as exc:
            ...现有错误处理不变...

        self.phase = PipelineStage.REVIEWING
        ...现有 post_draft 逻辑不变...
    else:
        # Continue interview
        self._save_history()
        self._save_session()
        intake = self._write_refinement_intake()
        return [{
            "type": "message", "role": "assistant",
            "content": result["content"],
            "pipeline_stage": self.phase.value,
            "intake": intake.model_dump(mode="json") if self.intake_mode else None,
        }]
```

#### 3a. 新增 `_conduct_interview_round()` 方法

```python
async def _conduct_interview_round(self, user_message: str) -> dict:
    """One round of the LLM-driven adaptive interview."""
    from ..chat_engine import ChatEngine
    from ..config import get_settings

    # Build slot state from current intake
    slots = {}
    if hasattr(self, '_current_slots'):
        slots = self._current_slots
    else:
        self._current_slots = {}
        slots = self._current_slots

    # Update slots from user message (simple heuristic: if user seems to answer a proposal)
    proposal_history = getattr(self, '_proposal_history', [])
    if not proposal_history:
        self._proposal_history = []
        proposal_history = self._proposal_history

    # Build context
    context = self._build_interview_context(slots, proposal_history, self.turn_count)
    system_prompt = _build_interview_system_prompt()

    # Get provider
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("No LLM provider configured for interview")

    provider = _get_provider()
    if provider is None:
        raise RuntimeError("No LLM provider available")

    # Call LLM
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"## Slot State\n{context}\n\n## User Message\n{user_message}"},
    ]

    response = await asyncio.to_thread(provider.chat, messages=messages, max_tokens=2048)
    text = response.text if hasattr(response, 'text') else str(response)

    # Parse response
    parsed = self._parse_interview_response(text)

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
            self._track_proposal(
                self._proposal_history,
                proposal_id=parsed["options_id"],
                for_slot=parsed["options_id"],
                options=option_labels[:4],
            )

    return {
        "content": text,
        "is_conclusion": parsed["is_conclusion"],
        "slot_updates": parsed["slot_updates"],
    }
```

#### 3b. Fallback 方法

```python
async def _fallback_generate_draft(self, lang: str):
    """Generate draft when interview round fails."""
    self.draft = await self._generate_draft_via_llm()
    self.phase = PipelineStage.REVIEWING
    from ..services.refinement_logic import build_post_draft_result
    intake = self._write_refinement_intake()
    result = build_post_draft_result(
        self.draft, self.intake_mode, self._is_brief_fully_confirmed(),
        lang, self.phase.value, intake.model_dump(mode="json"),
    )
    result["is_conclusion"] = True
    return result
```

注意: `_conduct_interview_round` 需要 `import asyncio` (已在文件顶部)。

### ✅ 验证

```bash
python -m pytest tests/unit/test_interview_system.py -v  # ALL 13 PASS
python -m pytest tests/integration/test_ws_chat_blueprint.py -x -q  # 无回归
```

---

## Step 4: 全量回归 + E2E

```bash
python -m pytest tests/unit/ tests/integration/ --tb=line -q 2>&1 | grep -E "passed|failed"
python -m pytest tests/e2e/test_full_game_creation_real_llm_playwright.py::test_full_game_creation_intake_and_draft_only -v --tb=short -s
```

---

## 禁止事项

- ❌ 不要修改 `_generate_draft_via_llm()` — 访谈结束后仍用它做最终整合
- ❌ 不要在 Step 1 写 Step 2 的代码
- ❌ 不要保留旧的 turn_count < 2 硬编码分发 — 从 turn 0 就直接进 LLM 访谈
- ❌ `select_collecting_response` 旧函数可以保留但不调用（作为 dead code，后续清理）

## 常见问题

**Q: `_write_refinement_intake` 的参数签名是什么？**
A: `def _write_refinement_intake(self, latest_user_content: str | None = None)` — 可选参数

**Q: LLM provider 在访谈期间不可用？**
A: `_get_provider()` 可能返回 None。如果是这样，跳过访谈，直接走 `_fallback_generate_draft`

**Q: 循环中 `_current_slots` 没有初始化？**
A: 在 `BlueprintOrchestrator.__init__` 中加 `self._current_slots = {}` 和 `self._proposal_history = []`

**Q: 测试失败但和我的改动无关？**
A: 报告给我，不要改那个测试。

---

## 完成后输出

```
=== TDD 执行报告 ===

## Step 1: 系统提示词 + 上下文
- RED: X tests FAIL, GREEN: X tests PASS
- 新增: _build_interview_system_prompt(), _build_interview_context()

## Step 2: 解析器 + 追踪
- RED: X tests FAIL, GREEN: X tests PASS
- 新增: _parse_interview_response(), _track_proposal()

## Step 3: 主循环
- RED: X tests FAIL, GREEN: X tests PASS
- 修改: handle_user_message() COLLECTING 分支
- 新增: _conduct_interview_round(), _fallback_generate_draft()

## Step 4: 回归
- 单元+集成: X/X pass
- E2E: PASS/FAIL

## 遇到的问题
```
