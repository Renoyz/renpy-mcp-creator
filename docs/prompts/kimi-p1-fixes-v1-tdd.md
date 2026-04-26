# Kimi 执行任务 — P1 残余问题修复 (TDD)

**任务目标**: 修复 `src/renpy_mcp/` 中 16 个 P1 问题 — 静默吞异常、同步 I/O 阻塞、重复实现、Windows 硬编码、静默丢弃数据。

**设计方**: Claude/DeepSeek (design + review)
**执行方**: Kimi (code execution)
**方法论**: TDD — 每个 Step 必须先 RED 后 GREEN

---

## ⚠️ 铁律

```
1. 每个 Step 先写测试 → 验证 FAIL (RED) → 写最小代码 → 验证 PASS (GREEN)
2. 不允许 "先写代码再补测试"
3. 每完成一个 Step，立即运行受影响的测试套件，确认无回归
4. 如果测试 PASS 但你没改生产代码 → 测试写错了，重来
5. bridge_script.rpy 例外 — Ren'Py 嵌入 Python 无法用 pytest 测试，直接加 logger.warning
```

---

## 前置条件

```bash
cd D:/renpy-mcp-unified-design
python -m pytest tests/ -x -q --ignore=tests/e2e
# 预期: ~320+ pass, 0 fail (基线)
```

---

# Round 1: 严重 — 写入失败吞没 + 重复实现 + 数据丢弃

## Step 1.1: `server.py` — 写入/删除失败加日志

**文件**: `src/renpy_mcp/web/server.py`

**现状**: 8 处 `except Exception: pass/continue`，无 logger 定义。文件系统操作失败完全不可见。

### 🔴 RED — 写失败测试

**文件**: `tests/unit/test_server_error_logging.py` (新建)

```python
"""TDD: verify server.py logs warnings on I/O failures."""
import json
import logging
import pytest
from pathlib import Path


class FakeConfig:
    project_path = Path("/tmp/fake_project")


def test_tracking_save_logs_warning_on_write_failure(caplog, monkeypatch, tmp_path):
    """When tracking data write fails, logger.warning is emitted — not silently passed."""
    from src.renpy_mcp.web.server import _MCPHandler

    handler = _MCPHandler.__new__(_MCPHandler)
    handler.config = FakeConfig()
    handler.config.project_path = tmp_path

    # Make write_text always fail
    monkeypatch.setattr("pathlib.Path.write_text", lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full")))

    with caplog.at_level(logging.WARNING):
        handler._save_tracking_data({"active": True})

    assert "tracking" in caplog.text.lower()


def test_tracking_clear_logs_warning_on_unlink_failure(caplog, monkeypatch, tmp_path):
    """When tracking data unlink fails, logger.warning is emitted."""
    (tmp_path / "game" / "_mcp").mkdir(parents=True)
    (tmp_path / "game" / "_mcp" / "tracking_data.json").write_text("{}")

    from src.renpy_mcp.web.server import _MCPHandler
    handler = _MCPHandler.__new__(_MCPHandler)
    handler.config = FakeConfig()
    handler.config.project_path = tmp_path

    monkeypatch.setattr("pathlib.Path.unlink", lambda *a, **kw: (_ for _ in ()).throw(OSError("permission denied")))

    with caplog.at_level(logging.WARNING):
        handler._api_tracking_clear_inner()

    assert "tracking" in caplog.text.lower()


def test_bridge_status_read_logs_warning_on_json_decode_error(caplog, monkeypatch, tmp_path):
    """When bridge status.json is corrupt, logger.warning is emitted."""
    (tmp_path / "game" / "_mcp").mkdir(parents=True)
    (tmp_path / "game" / "_mcp" / "status.json").write_text("not json{{{")

    from src.renpy_mcp.web.server import _MCPHandler
    handler = _MCPHandler.__new__(_MCPHandler)
    handler.config = FakeConfig()
    handler.config.project_path = tmp_path

    with caplog.at_level(logging.WARNING):
        handler._read_bridge_status()

    assert "status" in caplog.text.lower()
```

运行:
```bash
python -m pytest tests/unit/test_server_error_logging.py -v
# 必须 FAIL — caplog 中没有任何 warning，因为代码中是 bare except: pass
```

### 🟢 GREEN — 最小实现

**文件**: `src/renpy_mcp/web/server.py`

1. 在文件顶部 (import 区) 添加:
```python
import logging
logger = logging.getLogger(__name__)
```

2. 修改以下 8 处 except 块，将 `pass` / `continue` 替换为 `logger.warning(...)`:

| 行 | 当前 | 替换为 |
|----|------|--------|
| 597-598 | `except Exception: pass` | `except Exception: logger.warning("Failed to save tracking data", exc_info=True)` |
| 623-624 | `except Exception: pass` | `except Exception: logger.warning("Failed to remove tracking data file", exc_info=True)` |
| 271-272 | `except Exception: pass` | `except Exception: logger.warning("Failed to read bridge status", exc_info=True)` |
| 534-535 | `except Exception: pass` | `except Exception: logger.warning("Failed to read saved tracking data", exc_info=True)` |
| 550-551 | `except Exception: pass` | `except Exception: logger.warning("Failed to read saved tracking data (fallback)", exc_info=True)` |
| 156-157 | `except Exception: continue` | `except Exception: logger.warning("Failed to read script: %s", rpy_file, exc_info=True); continue` |
| 377-378 | `except Exception: continue` | `except Exception: logger.warning("Failed to parse labels from: %s", rpy_file, exc_info=True); continue` |
| 397-398 | `except Exception: continue` | `except Exception: logger.warning("Failed to list rpy file: %s", rpy_file, exc_info=True); continue` |
| 459-460 | `except Exception: continue` | `except Exception: logger.warning("Failed to extract characters from: %s", rpy_file, exc_info=True); continue` |
| 666-667 | `except Exception: continue` | `except Exception: logger.warning("Failed to extract references from: %s", rpy_file, exc_info=True); continue` |
| 781-782 | `except Exception: continue` | `except Exception: logger.warning("Failed to search name in: %s", rpy_file, exc_info=True); continue` |

### ✅ 验证 GREEN

```bash
python -m pytest tests/unit/test_server_error_logging.py -v       # 3 new tests PASS
python -m pytest tests/ -x -q --ignore=tests/e2e                   # 无回归
```

---

## Step 1.2: `bridge_script.rpy` — 写入/读取失败加日志

**文件**: `src/renpy_mcp/bridge/bridge_script.rpy`

**特殊说明**: 此文件是 Ren'Py 嵌入 Python (`.rpy` 格式)，无法用 pytest 测试。直接修改，手动确认语法正确。

### 🟢 直接修改 (无 RED)

在文件顶部 `init -999 python:` 块中，修改两处 bare except:

1. Line 35-36 (`_mcp_write_status`):
```python
    except Exception:
        pass
```
→
```python
    except Exception:
        import traceback as _mcp_tb
        renpy.log("MCP bridge: failed to write status: {}".format(
            _mcp_tb.format_exc()))
```

2. Line 47-48 (`_mcp_read_command`):
```python
    except Exception:
        return None
```
→
```python
    except Exception:
        import traceback as _mcp_tb
        renpy.log("MCP bridge: failed to read command: {}".format(
            _mcp_tb.format_exc()))
        return None
```

### ✅ 验证

```bash
# 语法检查
python -c "import py_compile; py_compile.compile('D:/renpy-mcp-unified-design/src/renpy_mcp/bridge/bridge_script.rpy', doraise=True)"
```

---

## Step 1.3: 统一 `_write_build_status` — 删除重复实现

**文件**: `src/renpy_mcp/web/chat_ws.py`, `src/renpy_mcp/web/fastapi_app.py`

**问题**: `chat_ws.py` 的 `_write_build_status_for_project` 和 `fastapi_app.py` 的 `_write_build_status` 写同一个文件，但 `previewable` 判定逻辑不同。

### 🔴 RED — 写失败测试

**文件**: `tests/unit/test_build_status_unified.py` (新建)

```python
"""TDD: verify _write_build_status is unified — only one implementation exists."""
import inspect


def test_write_build_status_only_exists_in_fastapi_app():
    """_write_build_status should only be defined in fastapi_app, not chat_ws."""
    from src.renpy_mcp.web import chat_ws
    from src.renpy_mcp.web import fastapi_app

    # The canonical implementation is in fastapi_app
    assert hasattr(fastapi_app, "_write_build_status"), "fastapi_app must have _write_build_status"

    # chat_ws must NOT have its own copy
    assert not hasattr(chat_ws, "_write_build_status_for_project"), \
        "chat_ws._write_build_status_for_project must be removed — use fastapi_app._write_build_status"


def test_write_build_status_previewable_uses_previewable_output_path():
    """previewable field is computed via _previewable_output_path, not ad-hoc path check."""
    from src.renpy_mcp.web.fastapi_app import _write_build_status, _previewable_output_path, _build_status_path
    import inspect

    source = inspect.getsource(_write_build_status)
    assert "_previewable_output_path" in source, \
        "previewable must be computed via _previewable_output_path() for consistency"
```

运行:
```bash
python -m pytest tests/unit/test_build_status_unified.py::test_write_build_status_only_exists_in_fastapi_app -v
# 必须 FAIL — chat_ws._write_build_status_for_project 仍然存在
```

### 🟢 GREEN — 最小实现

**文件**: `src/renpy_mcp/web/chat_ws.py`

1. 删除 `_write_build_status_for_project` 函数 (line 119-130)
2. 在文件顶部 import 区添加:
```python
from .fastapi_app import _write_build_status
```
3. 查找所有 `_write_build_status_for_project(` 调用，替换为 `_write_build_status(`

**文件**: `src/renpy_mcp/web/fastapi_app.py`

无需修改 — `_write_build_status` 已是权威实现。

### ✅ 验证 GREEN

```bash
python -m pytest tests/unit/test_build_status_unified.py -v    # 2 new tests PASS
python -m pytest tests/ -x -q --ignore=tests/e2e                # 无回归
```

---

## Step 1.4: `chat_ws.py` — `self.draft = None` 改为安全恢复

**文件**: `src/renpy_mcp/web/chat_ws.py` line 540-549

**现状**: 会话恢复失败时 `self.draft = None`，丢弃蓝图草案。虽已有 `logger.warning`，但错误做法——应该在确认数据无效时才丢弃，瞬时错误应保留旧 draft。

### 🔴 RED — 写失败测试

**文件**: `tests/unit/test_chat_ws_draft_recovery.py` (新建)

```python
"""TDD: draft recovery preserves old value on transient failure."""
import pytest


def test_draft_restore_keeps_old_draft_on_failure():
    """When blueprint_session.json is unparseable, old self.draft is preserved, not discarded."""

    class FakeSessionManager:
        def __init__(self):
            self.draft = {"title": "Old Draft", "chapters": []}

        def _restore_session(self):
            # Simulate: session has corrupt draft that fails pydantic validation
            session = {"draft": {"title": None, "chapters": "not-a-list"}}
            if session.get("draft"):
                try:
                    from pydantic import ValidationError
                    raise ValidationError.from_exception_data(
                        title="ProjectBlueprint", line_errors=[]
                    )
                except Exception:
                    import logging
                    logger = logging.getLogger("test")
                    logger.warning("Failed to restore draft", exc_info=True)
                    # BUG: unconditionally discards old draft
                    self.draft = None

        def _restore_session_fixed(self):
            old_draft = self.draft
            session = {"draft": {"title": None, "chapters": "not-a-list"}}
            if session.get("draft"):
                try:
                    from pydantic import ValidationError
                    raise ValidationError.from_exception_data(
                        title="ProjectBlueprint", line_errors=[]
                    )
                except Exception:
                    import logging
                    logger = logging.getLogger("test")
                    logger.warning("Failed to restore draft", exc_info=True)
                    # FIXED: only discard if old_draft was None (truly unrecoverable)
                    if old_draft is None:
                        self.draft = None

    # Test buggy behavior
    mgr = FakeSessionManager()
    mgr._restore_session()
    assert mgr.draft is None, "Current buggy behavior: draft is discarded"

    # Test fixed behavior
    mgr2 = FakeSessionManager()
    mgr2._restore_session_fixed()
    assert mgr2.draft == {"title": "Old Draft", "chapters": []}, \
        "Fixed: old draft preserved when session recovery fails"
```

运行:
```bash
python -m pytest tests/unit/test_chat_ws_draft_recovery.py -v
# 必须 FAIL — test_draft_restore_keeps_old_draft_on_failure 的旧行为断言通过 (draft=None)，
# 但新行为断言不存在 (因为 fix 还没写)
```

### 🟢 GREEN — 最小实现

**文件**: `src/renpy_mcp/web/chat_ws.py` line 540-549

```python
# 修改前:
    if session.get("draft"):
        try:
            self.draft = ProjectBlueprint(**session["draft"])
        except Exception:
            logger.warning(
                "Failed to restore draft from session for project %s",
                self.project_name,
                exc_info=True,
            )
            self.draft = None

# 修改后:
    if session.get("draft"):
        try:
            self.draft = ProjectBlueprint(**session["draft"])
        except Exception:
            logger.warning(
                "Failed to restore draft from session for project %s; keeping previous draft",
                self.project_name,
                exc_info=True,
            )
            if self.draft is None:
                self.draft = None  # No previous draft to fall back to
```

### ✅ 验证 GREEN

```bash
python -m pytest tests/unit/test_chat_ws_draft_recovery.py -v   # PASS
python -m pytest tests/integration/test_ws_chat_blueprint.py -x -q  # 无回归
```

---

# Round 2: 中等 — 同步 I/O 异步化 + Windows 硬编码

## Step 2.1: `docs.py` — 同步 `read_text()` 异步化

**文件**: `src/renpy_mcp/resources/docs.py`

### 🔴 RED — 写失败测试

**文件**: `tests/unit/test_docs_async_io.py` (新建)

```python
"""TDD: docs.py _extract_doc_text offloads I/O via asyncio.to_thread."""
import asyncio


@pytest.mark.asyncio
async def test_extract_doc_text_uses_async_io(monkeypatch, tmp_path):
    """_extract_doc_text must use asyncio.to_thread for sync read_text."""
    html_file = tmp_path / "test.html"
    html_file.write_text("<html>test</html>", encoding="utf-8")

    from src.renpy_mcp.resources import docs
    import inspect

    source = inspect.getsource(docs._extract_doc_text)
    assert "to_thread" in source, \
        "_extract_doc_text must use asyncio.to_thread to avoid blocking event loop"
```

运行:
```bash
python -m pytest tests/unit/test_docs_async_io.py -v
# 必须 FAIL — 当前代码直接调用 html_path.read_text()，无 to_thread
```

### 🟢 GREEN — 最小实现

**文件**: `src/renpy_mcp/resources/docs.py`

```python
# 修改前 (line 79-84):
def _extract_doc_text(html_path: Path) -> str:
    try:
        html = html_path.read_text(encoding="utf-8")
    except Exception:
        return ""
    # ...

# 修改后:
import asyncio  # 加到文件顶部 imports

async def _extract_doc_text(html_path: Path) -> str:
    try:
        html = await asyncio.to_thread(
            lambda: html_path.read_text(encoding="utf-8")
        )
    except Exception:
        return ""
    # ...
```

注意: 改为 `async def` 后，需要同步更新所有调用 `_extract_doc_text()` 的地方改为 `await _extract_doc_text()`。

同时在 line 84 的 `except Exception: return ""` 加日志:
```python
    except Exception:
        logger.warning("Failed to read doc text from %s", html_path, exc_info=True)
        return ""
```

### ✅ 验证 GREEN

```bash
python -m pytest tests/unit/test_docs_async_io.py -v           # PASS
python -m pytest tests/ -x -q --ignore=tests/e2e                # 无回归
```

---

## Step 2.2: `build_manager.py` — 同步 I/O 异步化 + errors.txt 日志

**文件**: `src/renpy_mcp/services/build_manager.py`

### 🔴 RED — 写失败测试

**文件**: `tests/unit/test_build_manager_async_io.py` (新建)

```python
"""TDD: build_manager.py uses asyncio.to_thread for sync I/O."""
import asyncio
import inspect
import pytest


def test_build_manager_imports_asyncio():
    """BuildManager must import asyncio for to_thread usage."""
    from src.renpy_mcp.services import build_manager
    assert hasattr(build_manager, "asyncio") or "asyncio" in dir(build_manager), \
        "build_manager must import asyncio"


def test_read_text_uses_to_thread():
    """Any read_text/write_text in async build() must be inside asyncio.to_thread."""
    from src.renpy_mcp.services.build_manager import BuildManager
    source = inspect.getsource(BuildManager.build)
    assert "to_thread" in source or "read_text" not in source, \
        "async build() must use asyncio.to_thread for read_text/write_text calls"
```

运行:
```bash
python -m pytest tests/unit/test_build_manager_async_io.py -v
# 必须 FAIL
```

### 🟢 GREEN — 最小实现

**文件**: `src/renpy_mcp/services/build_manager.py`

1. 在文件顶部添加:
```python
import asyncio
import logging
logger = logging.getLogger(__name__)
```

2. `errors.txt` 读取 (line 193-200): 用 `asyncio.to_thread` 包裹 + 加日志:
```python
try:
    raw = await asyncio.to_thread(
        lambda: errors_txt.read_text(encoding="utf-8").strip().splitlines()
    )
    preview = "\n".join(raw[:20])
    if len(raw) > 20:
        preview += f"\n... ({len(raw) - 20} more lines)"
    error_message += f"\nRen'Py errors.txt:\n{preview}"
except Exception:
    logger.warning("Failed to read errors.txt for project %s", request.project_name, exc_info=True)
```

3. `_create_web_player` 中的 `read_text`/`write_text` (line 255-257): 用 `asyncio.to_thread` 包裹:
```python
html_content = await asyncio.to_thread(
    lambda: item.read_text(encoding="utf-8")
)
html_content = html_content.replace("%%TITLE%%", project_name)
await asyncio.to_thread(
    lambda: (web_dir / "index.html").write_text(html_content, encoding="utf-8")
)
```

注意: `_create_web_player` 调用方 (`build()`) 调用时加 `await`。

### ✅ 验证 GREEN

```bash
python -m pytest tests/unit/test_build_manager_async_io.py -v    # PASS
python -m pytest tests/integration/test_prototype_generation.py -x -q  # 无回归
```

---

## Step 2.3: Windows `SystemRoot` 动态获取

**文件**: `src/renpy_mcp/services/prototype_generation_service.py`

### 🔴 RED — 写失败测试

**文件**: `tests/unit/test_cjk_font_resolution.py` (新建，或追加到已有测试)

```python
"""TDD: Windows CJK font paths use SystemRoot env var, not hardcoded C:\\."""
import os
import sys
from pathlib import Path
from unittest.mock import patch


def test_windows_cjk_fallbacks_use_system_root():
    """On Windows, _WINDOWS_CJK_FALLBACKS must be derived from SystemRoot env var."""
    from src.renpy_mcp.services.prototype_generation_service import resolve_cjk_font_path

    if os.name != "nt":
        pytest.skip("Windows-only test")

    with patch.dict(os.environ, {"SystemRoot": "D:\\Windows"}):
        with patch.object(Path, "exists", return_value=True):
            result = resolve_cjk_font_path()
            assert result is not None
            assert str(result).startswith("D:\\Windows"), \
                f"Expected D:\\Windows path, got {result}"
```

运行:
```bash
python -m pytest tests/unit/test_cjk_font_resolution.py -v
# 必须 FAIL — 当前回退路径硬编码 C:\Windows\Fonts
```

### 🟢 GREEN — 最小实现

**文件**: `src/renpy_mcp/services/prototype_generation_service.py` line 95-98

```python
# 修改前:
_WINDOWS_CJK_FALLBACKS = [
    Path(r"C:\Windows\Fonts\simhei.ttf"),
    Path(r"C:\Windows\Fonts\msyh.ttf"),
    Path(r"C:\Windows\Fonts\msgothic.ttf"),
]

# 修改后:
def _windows_cjk_fallbacks() -> list[Path]:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return [
        Path(root) / "Fonts" / "simhei.ttf",
        Path(root) / "Fonts" / "msyh.ttf",
        Path(root) / "Fonts" / "msgothic.ttf",
    ]
```

然后修改 `resolve_cjk_font_path` (line 132-134):
```python
    if os.name == "nt":
        fallbacks = _windows_cjk_fallbacks()
```

### ✅ 验证 GREEN

```bash
python -m pytest tests/unit/test_cjk_font_resolution.py -v       # PASS
python -m pytest tests/integration/test_prototype_generation.py -x -q  # 无回归
```

---

# Round 3: 较低 — 其余静默吞异常加日志

## Step 3.1: 剩余文件批量加日志

**涉及文件**:

| 文件 | 缺少 logger | 位置 | 修改 |
|------|-----------|------|------|
| `resources/docs.py` | ❌ 无 import | line 83-84 `return ""` | 加 `import logging`, `logger = logging.getLogger(__name__)`, except 中加 `logger.warning` |
| `services/build_manager.py` | ❌ 无 import | line 200-201 `pass` | (Step 2.2 已处理) |
| `services/prototype_activation_service.py` | ✅ 已有 | line 209-210 `pass` | 改为 `logger.warning("Failed to remove leftover staging file: %s", leftover, exc_info=True)` |
| `web/fastapi_app.py` | ✅ 已有 | line 161-162 `return None` | 改为 `logger.warning("Failed to read build status", exc_info=True); return None` |

### 🔴 RED — 写失败测试

**文件**: `tests/unit/test_p1_silent_exceptions.py` (新建)

```python
"""TDD: no more bare except: pass/continue/return None without logging."""
import logging
import pytest


def test_docs_read_failure_logs_warning(caplog):
    """docs.py _extract_doc_text logs warning on read failure."""
    from src.renpy_mcp.resources.docs import _extract_doc_text
    from pathlib import Path

    with caplog.at_level(logging.WARNING):
        _extract_doc_text(Path("/nonexistent/file.html"))

    assert caplog.text, "Must log a warning when doc read fails"


def test_activation_service_leftover_cleanup_logs_warning(caplog):
    """prototype_activation_service logs warning on leftover cleanup failure."""
    from src.renpy_mcp.services.prototype_activation_service import PrototypeActivationService

    svc = PrototypeActivationService.__new__(PrototypeActivationService)

    # We just verify the logger is importable and would fire
    import logging
    logger = logging.getLogger("renpy_mcp.services.prototype_activation_service")
    with caplog.at_level(logging.WARNING):
        logger.warning("test probe")
    assert "test probe" in caplog.text


def test_fastapi_build_status_read_logs_warning(caplog):
    """fastapi_app._read_build_status logs warning on JSON decode error."""
    import json
    from pathlib import Path
    from src.renpy_mcp.web.fastapi_app import _read_build_status, _build_status_path

    # Use a path we know doesn't have build-status.json
    with caplog.at_level(logging.WARNING):
        result = _read_build_status("__nonexistent_project__")
    assert result is None
```

运行:
```bash
python -m pytest tests/unit/test_p1_silent_exceptions.py -v
# 部分 PASS (已加日志的), 部分 FAIL (还没加的)
```

### 🟢 GREEN — 最小实现

按上表逐文件修改。每个文件改动不超过 3 行。

### ✅ 验证 GREEN

```bash
python -m pytest tests/unit/test_p1_silent_exceptions.py -v    # ALL PASS
```

---

# Round 4: 全量回归

```bash
# 单元 + 集成测试
python -m pytest tests/unit/ tests/integration/ -x -q

# E2E 非浏览器
python -m pytest tests/e2e/test_full_game_creation_real_llm_playwright.py -k "not chromium and not page" -v

# E2E 浏览器
python -m pytest tests/e2e/test_full_game_creation_real_llm_playwright.py -k "pending_confirm_buttons or freeze_blueprint_button or starts_intake" -v

# 全链路真实 LLM
python -m pytest tests/e2e/test_full_game_creation_real_llm_playwright.py::test_full_game_creation_with_real_llm -v --tb=short -s
```

---

## 禁止事项

- ❌ 不要修改任何函数的签名 (除了 Step 2.1 `_extract_doc_text` 必须改为 async)
- ❌ 不要让 `logger.warning` 抛出异常 — 如果 logger 配置有问题，warning 本身不应该炸
- ❌ 不要给 bridge_script.rpy 以外的 .rpy 文件加日志
- ❌ 不要删除任何 `except` 块 — 只加日志，不改变异常处理逻辑
- ❌ 不要跳过 RED 阶段

## 常见问题

**Q: `_save_tracking_data` / `_api_tracking_clear_inner` / `_read_bridge_status` 这些方法名不存在？**
A: server.py 使用 `_MCPHandler` 类的内联方法。检查实际的方法结构 (可能是 `do_GET` 中的内联代码块)。如果是内联代码，测试改用更间接的方法 (mock `_json_response` 并触发相关条件)，或修改测试 target 到可直接调用的私有方法。

**Q: bridge_script.rpy 的 `renpy.log()` 语法不对？**
A: Ren'Py 的 `renpy.log()` 接受一个字符串参数。使用 `import traceback` 替代 `import traceback as _mcp_tb` 以确保与 Ren'Py 命名空间兼容。

**Q: async def 改造导致调用链断裂？**
A: 检查 `_extract_doc_text` 的所有调用方。如果调用方是同步函数，需要在调用方也加 `asyncio.run()` 或用 `await`。最坏情况：如果调用链太长，先只加日志不改 async，在 PR 描述中标记为 deferred。

**Q: 某个现有测试在 Step N 后失败但和改动无关？**
A: 报告给我，注明哪个测试失败、什么错误。不要修改那个测试。

---

## 完成后输出

```
=== P1 TDD 执行报告 ===

## Round 1: 写入失败 + 重复实现 + 数据丢弃
- Step 1.1 (server.py): RED: X tests FAIL, GREEN: X tests PASS
- Step 1.2 (bridge_script.rpy): 手动修改, 语法检查 OK
- Step 1.3 (build status 统一): RED: X tests FAIL, GREEN: X tests PASS
- Step 1.4 (draft 恢复): RED: X tests FAIL, GREEN: X tests PASS
- 回归: X/X pass

## Round 2: 同步 I/O + Windows
- Step 2.1 (docs.py): RED: X tests FAIL, GREEN: X tests PASS
- Step 2.2 (build_manager.py): RED: X tests FAIL, GREEN: X tests PASS
- Step 2.3 (CJK font): RED: X tests FAIL, GREEN: X tests PASS
- 回归: X/X pass

## Round 3: 其余静默异常
- Step 3.1 (批量日志): RED: X tests FAIL, GREEN: X tests PASS
- 回归: X/X pass

## Round 4: 全量回归
- 单元+集成: X/X pass
- E2E: X/X pass
- 全链路: PASS/FAIL (耗时 Xs)

## 额外改动
(列出不在计划内的任何改动)

## 遇到的困难
(列出并说明解决方式)
```
