# Kimi 修复 — 5个 WS 测试偶发失败

## 问题

在全量 `tests/unit/ tests/integration/` 下，5 个 WebSocket 测试因 `_current_project_path.get()` 返回 `None` 而失败，FakeEngine 返回 `"NO_PROJECT"` 导致断言失败。

根因：其他测试模块永久修改了全局 `settings.workspace`，导致 `_bind_project_context` → `resolve_project_dir` 在 websocket handler 中找不到项目。

## 修复模式

对照 `test_ws_chat_uses_payload_project_name`（已修复，可作为参考）。每个测试在 `websocket_connect` 前加 `_current_project_path.set()`，finally 中 reset。

## 要修复的 5 个测试

### 1. `tests/integration/test_ws_chat.py::test_ws_chat_uses_session_project` (line 113)

```python
def test_ws_chat_uses_session_project(monkeypatch, client, tmp_path):
    from renpy_mcp.config import _current_project_path  # 新增

    project_name = "session_proj"
    project_dir = tmp_path / project_name                     # 新增
    game_dir = project_dir / "game"
    ...

    token = _current_project_path.set(project_dir)            # 新增
    try:                                                      # 新增
        with client.websocket_connect("/ws/chat") as websocket:
            ...现有代码不变...
    finally:                                                  # 新增
        _current_project_path.reset(token)                    # 新增
```

### 2. `tests/integration/test_ws_chat.py::test_ws_chat_switches_project_after_reconnect` (line 137)

同样是两处 `websocket_connect`，需要分别设置。在 `with` 之前：
```python
token_a = _current_project_path.set(tmp_path / "proj_a")
try:
    with client.websocket_connect(...):
        ...
finally:
    _current_project_path.reset(token_a)

# 切换后
token_b = _current_project_path.set(tmp_path / "proj_b")
try:
    with client.websocket_connect(...):
        ...
finally:
    _current_project_path.reset(token_b)
```

### 3. `tests/integration/test_ws_chat.py::test_ws_chat_injects_current_project_into_system_prompt` (line 206)

已有 `_current_project_path.set()` 和 reset。检查是否正确（应该已经 OK，但如果失败需要确保 `project_dir` 在 try 块外构造好了）。

### 4. `tests/integration/test_ws_chat.py::test_ws_chat_project_isolation` (line 564)

FakeEngine 中使用 `_current_project_path.get()`。需要在 `client.websocket_connect` 前加 set。按照模式 1 应用。

### 5. `tests/integration/test_ws_chat_confirmation.py::test_ws_chat_confirmation_keeps_original_project`

检查是否也需要 `_current_project_path.set()`。如果是同样的 FakeEngine 模式，同样处理。

## 验证

```bash
# 每个修复后立即验证
python -m pytest tests/unit/ tests/integration/test_ws_chat.py::<test_name> -x --tb=short

# 最终全量验证 (3 次, 必须全部 0 fail)
for i in 1 2 3; do
  python -m pytest tests/unit/ tests/integration/ --tb=line -q 2>&1 | grep -E "passed|failed"
done
```

## 参考

已修复的 `test_ws_chat_uses_payload_project_name` 在 `tests/integration/test_ws_chat.py` line 47-70，可直接对照。
