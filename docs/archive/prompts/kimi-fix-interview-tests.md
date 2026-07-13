# Kimi 修复 — 自适应访谈测试卡死

## 问题

`test_ws_chat.py`、`test_ws_chat_confirmation.py`、`test_ws_chat_blueprint.py` 中多个测试卡死/失败。

根因：新访谈路径调用 `provider.chat()` 但测试 mock 的 `_get_provider` 返回 `chat=lambda **kw: []`（空列表）。访谈解析不到 `<CONCLUSION>`，无限循环。

## 修复模式

两种模式，按测试用途选择：

### 模式 A：简单 WS 通信测试（只测 project context 传递）

适用：`test_ws_chat_uses_payload_project_name`、`test_ws_chat_uses_session_project`、`test_ws_chat_switches_project_after_reconnect`、`test_ws_chat_project_isolation`

这类测试不关心访谈内容，只验证项目 context 正确传递。直接 mock `_conduct_interview_round`：

```python
# 删除这两行:
monkeypatch.setattr("renpy_mcp.web.chat_ws._get_provider", lambda: ...)
monkeypatch.setattr("renpy_mcp.web.chat_ws.ChatEngine", _make_fake_engine())

# 替换为:
async def _mock_interview(self, user_message):
    return {
        "content": str(_current_project_path.get() or "NO_PROJECT"),
        "is_conclusion": False,
        "slot_updates": {},
    }
monkeypatch.setattr(
    "renpy_mcp.web.chat_ws.BlueprintOrchestrator._conduct_interview_round",
    _mock_interview,
)

# 断言也改:
assert data["type"] == "message"        # 不再是 "assistant_delta"
assert project_name in data["content"]  # 不再是 data["delta"]
```

### 模式 B：蓝图/确认流程测试（测 orchestrator 完整流程）

适用：`test_ws_chat_blueprint.py` 和 `test_ws_chat_confirmation.py` 中的测试

这类测试需要访谈 → 结论 → 生成草稿的完整流程。已有一个可用的 mock（`_get_provider` 内部的 "## Slot State" 检测 + `<CONCLUSION />` 返回）。只需确保 `_get_provider` 的 mock **不去掉** "## Slot State" 检测。

检查 `_make_mock_blueprint_provider` 和 `_make_mock_smart_provider` 的 `chat` 方法是否包含：
```python
if isinstance(prompt, str) and "## Slot State" in prompt:
    return LLMResponse(
        content_blocks=[{"type": "text", "text": "<CONCLUSION />"}],
        stop_reason="end_turn",
    )
```

如果已有（从 diff 看已加），则这类测试**无需改**。

### 模式 C：空 provider mock（`test_ws_chat_no_project_guardrail` 等）

这类测试 mock `_get_provider` 为 `None` 或空，验证无 provider 时的错误处理。无需修改——无 provider 时访谈会抛异常进入 fallback。

## 需要修改的测试清单

在 `tests/integration/test_ws_chat.py`：

- [ ] `test_ws_chat_uses_payload_project_name` — 已修复（模式 A）
- [ ] `test_ws_chat_uses_session_project` (line ~112) — 模式 A
- [ ] `test_ws_chat_switches_project_after_reconnect` (line ~137) — 模式 A
- [ ] `test_ws_chat_project_isolation` (line ~564) — 模式 A
- [ ] `test_ws_chat_mock_provider` (line ~173) — 模式 C（测 ChatEngine 路径），如果 message 不进 COLLECTING 则无需改
- [ ] `test_ws_chat_injects_current_project_into_system_prompt` (line ~206) — 直接调 `_system_prompt_for_current_project`，不经过 WS，无需改

在 `tests/integration/test_ws_chat_confirmation.py`：

- [ ] `test_ws_chat_confirmation_keeps_original_project` — 检查是否模式 B（已有 mock blueprint provider）或需模式 A

## 验证

每个文件修改后立即运行该文件的测试：

```bash
python -m pytest tests/integration/test_ws_chat.py -v --tb=short
python -m pytest tests/integration/test_ws_chat_confirmation.py -v --tb=short
python -m pytest tests/integration/test_ws_chat_blueprint.py -v --tb=short
```

**不要运行全量 suite** — 单独验证每个文件即可。
