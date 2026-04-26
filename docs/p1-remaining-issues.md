# P1 残余问题清单

扫描时间：2026-04-26
扫描范围：`src/renpy_mcp/` 全部 Python 文件

---

## 概览

| 类别 | 数量 | 核心风险 |
|------|------|----------|
| 静默吞异常 | 13 处 | 写入失败、解析失败无日志，线上问题无法定位 |
| 同步 I/O 在异步函数中 | 2 处 | 事件循环阻塞，高并发下延迟累积 |
| 重复实现 | 1 处 | 两份 `_write_build_status` 逻辑不一致 |
| Windows 硬编码 | 1 处 | 非 C: 盘 Windows 安装 CJK 字体失效 |
| 静默丢弃数据 | 1 处 | 会话恢复失败时蓝图数据丢失 |

---

## 一、静默吞异常（13 处）

这些位置捕获 `except Exception` 后直接 `pass`、`continue` 或 `return None`，不输出任何日志。

### 严重：写入/删除失败被吞没

| 文件 | 行号 | 吞没方式 | 风险 |
|------|------|----------|------|
| `web/server.py` | 597-598 | `pass` | 追踪数据写磁盘失败，静默丢失 |
| `web/server.py` | 623-624 | `pass` | 追踪文件删除失败，残留过期数据 |
| `bridge/bridge_script.rpy` | 37-38 | `pass` | 状态文件写失败，MCP 通信中断 |

### 中等：读取/解析失败静默返回空

| 文件 | 行号 | 吞没方式 | 风险 |
|------|------|----------|------|
| `resources/docs.py` | 83-84 | `return ""` | 文档读取失败返回空字符串，搜索结果缺失 |
| `web/server.py` | 271-272 | `pass` | Bridge 状态读取失败，误判为未连接 |
| `web/server.py` | 534-535, 550-551 | `pass` | 追踪数据 JSON 解析失败，返回空数据 |
| `bridge/bridge_script.rpy` | 49-50 | `return None` | 命令文件读取失败，指令静默丢失 |
| `services/build_manager.py` | 200-201 | `pass` | errors.txt 读取失败，构建错误信息丢失 |
| `tools/translation.py` | 451-452 | `tl_lines = []` | 翻译文件读取失败，返回空翻译 |

### 较低：批量文件遍历中的单项跳过

| 文件 | 行号 | 吞没方式 | 风险 |
|------|------|----------|------|
| `tools/analysis.py` | 27-28, 531-532, 661-662, 682-683, 777-778 | `continue` | 单个脚本文件解析失败被跳过（x5） |
| `tools/assets.py` | 260-261, 396-397, 519-520 | `continue` | 单个资源文件解析失败被跳过（x3） |
| `tools/translation.py` | 27-28, 256-257, 292-293 | `continue` / `return []` | 翻译条目解析失败 |
| `tools/testing.py` | 82-83 | `continue` | 测试脚本读取失败 |
| `web/server.py` | 156-157, 377-378, 397-398, 459-460, 666-667, 781-782 | `continue` | 标签/角色/资源扫描中单项失败（x6） |
| `services/prototype_activation_service.py` | 209-210 | `pass` | 过期临时文件清理失败 |

> **修复建议：** 最低限度在每个 `except Exception` 块中加入 `logger.warning(..., exc_info=True)`。对于写入失败（`server.py:597`），应至少尝试一次重试，最终失败时应通过 API 返回错误而非静默。

---

## 二、同步 I/O 在异步函数中阻塞事件循环（2 处）

| 文件 | 行号 | 问题 |
|------|------|------|
| `resources/docs.py` | 229 → 82 | `async def search_docs()` 调用 `_extract_doc_text()` 内同步 `read_text()` |
| `services/build_manager.py` | 24 → 194, 255 | `async def build()` 内同步 `read_text()` / `write_text()` |

> **修复建议：** 用 `await asyncio.to_thread(lambda: path.read_text(...))` 替代。

---

## 三、重复实现：`_write_build_status`（1 处）

| 文件 | 行号 | 函数名 |
|------|------|--------|
| `web/fastapi_app.py` | 126 | `_write_build_status()` |
| `web/chat_ws.py` | 125 | `_write_build_status_for_project()` |

两者写入 **同一文件** `logs/build-status.json`，结构几乎相同，但 **`previewable` 判定逻辑不同**：

- `fastapi_app.py`: `_previewable_output_path(output_path) is not None`
- `chat_ws.py`: `output_path is not None and (Path(output_path) / "index.html").exists() if output_path else False`

如果两处并发写入，后写者覆盖前写者，前端显示的 previewable 状态不可预期。

> **修复建议：** 删除 `chat_ws.py` 中的副本，统一使用 `fastapi_app.py` 的 `_write_build_status`（或进一步提取到 utils）。

---

## 四、Windows 硬编码：非 C: 盘失效（1 处）

| 文件 | 行号 | 问题 |
|------|------|------|
| `services/prototype_generation_service.py` | 95-98 | `_WINDOWS_CJK_FALLBACKS` 全部硬编码 `C:\Windows\Fonts\...` |

`resolve_cjk_font_path()` 已有平台检测和回退链，但如果用户 Windows 安装在 D: 盘，三个回退路径全部失效，返回 `None`。

> **修复建议：** 用 `os.environ.get("SystemRoot", "C:\\Windows")` 动态获取 Windows 目录。

---

## 五、静默丢弃数据：会话恢复失败（1 处）

| 文件 | 行号 | 问题 |
|------|------|------|
| `web/chat_ws.py` | 549 | `except Exception: self.draft = None` |

WebSocket 会话恢复时，如果 `blueprint_session.json` 出现瞬时 JSON 解析错误，正在进行的蓝图草案被静默丢掉（`self.draft = None`），用户只能重新开始。

> **修复建议：** 至少记录 `logger.warning`。考虑保留旧 `self.draft` 不做覆盖，仅在确认新数据有效后才替换。

---

## 优先级建议

```
第 1 轮：写入失败吞没 (server.py:597, bridge_script.rpy:37)
        + 重复 _write_build_status 统一
        + self.draft = None 加日志

第 2 轮：同步 I/O 异步化 (docs.py, build_manager.py)
        + SystemRoot 动态获取

第 3 轮：其余静默吞异常加日志
```
