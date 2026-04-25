# 代码质量收敛计划

## 扫描范围

对 `src/renpy_mcp/` 及 `tests/` 进行了三轮覆盖扫描：
- **死代码与重复代码** — 未使用的枚举值、模型类、模型字段、配置项；跨文件重复函数
- **架构问题** — 上帝类、关注点混合、耦合、硬编码、缺失抽象
- **逻辑 Bug** — 错误吞没、竞态条件、边界情况、异步阻塞

---

## P0 — 必须修复（会导致数据丢失、静默故障或运行时崩溃）

### P0-1: 事务提交中的数据丢失窗口

**文件：** `src/renpy_mcp/services/prototype_generation_service.py:559-561`

**问题：** `final_file.unlink()` 在 `staging_file.rename(final_file)` 之前执行。如果 rename 失败（跨设备移动、权限），旧文件已删除但新文件未就位。虽然 `old_final_contents` 可以在回退时恢复内容，但如果异常类型导致回退也失败，数据就丢失了。

**修复方向：** 改为先 rename staging→final（覆盖），不预先 unlink。`Path.rename()` 在 Windows 和 POSIX 上行为不同，改用 `shutil.move()` 或确保同设备操作。

**不修复的后果：** 用户在生成后丢失全部脚本文件，只能重新生成。

### P0-2: 竞态条件 — 模块级 Orchestrator 字典无锁

**文件：** `src/renpy_mcp/web/chat_ws.py:685, 1816-1820`

**问题：** `_orchestrators: dict[str, BlueprintOrchestrator]` 是模块级全局字典，被多个 async WebSocket 连接并发访问。`_get_orchestrator` 中的 check-then-act 是非原子的：两个连接同时访问同一项目时，可能创建两个不同的 `BlueprintOrchestrator` 实例，各有独立的 `self.draft` 和 `self.phase`，状态互相覆盖。

**修复方向：** 加 `asyncio.Lock` 保护，或使用 `dict.setdefault` 的原子性。

**不修复的后果：** 用户同时开两个浏览器标签页操作同一项目时，丢失确认的蓝图数据。

### P0-3: 异步上下文中的同步阻塞 `time.sleep()`

**文件：** `src/renpy_mcp/web/fastapi_app.py:109, 117`

**问题：** `_send_bridge_command` 在 async FastAPI 路由处理器中被调用，内部使用 `time.sleep(0.2)` 忙等轮询。这阻塞事件循环线程，所有并发请求都被卡住。

**修复方向：** 用 `asyncio.sleep()` 替换 `time.sleep()`，整个函数改为 async。

**不修复的后果：** 在高并发下（如 dashboard 自动刷新），整个服务器响应延迟累积，用户感知卡顿。

---

## P1 — 应该尽快修复（代码质量严重下降、跨平台兼容性、调试困难）

### P1-1: 三份重复的 Bridge Command 实现

**文件：**
- `src/renpy_mcp/web/fastapi_app.py:90-118`（其中之一为死代码，从未被调用）
- `src/renpy_mcp/web/server.py:286-317`
- `src/renpy_mcp/tools/live.py:35-53`

**问题：** 相同的「写 cmd.json.tmp → 原子 rename → 轮询 status.json」逻辑写了三遍。fastapi_app.py 的副本还是 `time.sleep` 同步阻塞版；live.py 是 async 版；server.py 是实例方法版。三份代码已经出现了异步处理差异和错误消息不一致。

**修复方向：** 提取为 `BridgeClient` 类，统一使用 async 实现。删除 fastapi_app.py 的死代码副本。

**不修复的后果：** 一个 bug 修复了其中一份，另两份仍然存在；新增第四个调用方时再复制一份。

### P1-2: `C:\Windows\Fonts\simhei.ttf` 硬编码

**文件：** `src/renpy_mcp/services/prototype_generation_service.py:92`

**问题：** CJK 字体路径是 Windows 绝对路径。在 Linux/macOS 上部署时，整个字体系统完全不工作。没有任何回退方案。

**修复方向：** 从 config 中读取字体路径；增加 OS 检测和平台默认路径列表；提供 Docker/CI 的字体安装说明。

**不修复的后果：** 在所有非 Windows 环境下，生成的游戏无 CJK 文字显示。CI/CD 无法运行端到端测试。

### P1-3: 100+ 处 `except Exception` 静默吞没

**文件及行号（仅列最严重的）：**

| 文件 | 行号 | 吞没方式 |
|------|------|----------|
| `web/chat_ws.py` | 729 | `self.draft = None`（回话恢复失败无日志） |
| `web/chat_ws.py` | 830 | `return False`（文件损坏时静默判定 brief 未确认） |
| `web/chat_ws.py` | 1691 | `pass`（回退失败丢弃） |
| `web/chat_ws.py` | 2260 | `pass`（WebSocket 关闭失败丢弃） |
| `web/fastapi_app.py` | 162 | `continue`（精灵数据损坏静默跳过） |
| `web/fastapi_app.py` | 2394, 2519, 2536, 2583, 2652, 2759 | `continue`（各种解析失败静默跳过） |
| `services/prototype_generation_service.py` | 601, 606, 618 | 嵌套静默吞没 |
| `ai/image_service.py` | 369, 387 | `return None`（API 调用失败无日志） |

**修复方向：** 所有 `except Exception` 至少加 `logger.warning/error`；关键路径（数据写入、状态变更）的异常必须传播；只在确实不影响正确性的地方才 catch。

**不修复的后果：** 线上问题无法定位，用户报告"我的人物不显示了"但日志里没有任何错误。

### P1-4: 跨文件重复代码 — 章节大纲推导

**文件：** `web/chat_ws.py:777-824` 和 `web/fastapi_app.py:656-709`

**问题：** 完全相同的 12+ 行 `emotional_arc`、`chapter_goal`、`key_conflict` 等派生公式在两个文件中各写一遍。修改一个必须同步修改另一个——这已经在之前的叙事改进计划中被标记为需要同时修改两处。

**修复方向：** 提取为共享函数 `derive_chapter_outline_fields(chapter, total_chapters)` → 放入 `src/renpy_mcp/blueprint/` 或 `src/renpy_mcp/services/`。

**不修复的后果：** 后续叙事改进（大纲随位置变化）需要改两处，容易遗漏导致行为不一致。

---

## P2 — 建议修复（架构债务、可维护性）

### P2-1: God Class — `PrototypeGenerationService`（2403 行）

**文件：** `src/renpy_mcp/services/prototype_generation_service.py`

**问题：** 一个类混合了 7 种职责：LLM 场景生成、图像生成、背景去底、字体管理、Ren'Py 脚本代码生成、文件暂存/提价、事务回退。30+ 个方法，任一修改都可能级联影响其他职责。

**修复方向：** 拆分为：
- `SceneGenerationService` — LLM 场景生成 + 验证
- `AssetGenerationService` — 背景 + 角色图生成
- `SpriteNormalizationService` — 去底 + 归一化 + 质量门
- `ScriptRenderService` — Ren'Py .rpy 代码生成
- `PrototypeActivationService` — 提价、回退、主脚本接线

`PrototypeGenerationService` 保留为门面，协调上述子服务。

**不修复的后果：** 每加一个新功能，类就再膨胀 200 行。单元测试无法针对单一职责编写，集成测试成为唯一选择。新人理解代码的时间随着类长度指数增长。

### P2-2: God Function — `create_app()`（2566 行）

**文件：** `src/renpy_mcp/web/fastapi_app.py:241-2807`

**问题：** 56 个路由 + 15 个私有辅助函数全部嵌套在一个闭包内。没有按资源分组，修改一个端点需要翻遍 2500 行。领域逻辑（`_check_generation_gate`、`_compute_refinement_state`、`_materialize_brief_from_intake`）和 HTTP 传输混在一起。

**修复方向：** 拆分为 6-8 个 FastAPI Router：
- `routers/projects.py` — CRUD
- `routers/refinement.py` — intake、brief、outline、freeze
- `routers/generation.py` — 场景生成、多章节生成
- `routers/preview_build.py` — 预览、构建、状态
- `routers/scripts_assets.py` — 脚本读写、资源管理
- `routers/pages.py` — 静态页面

领域逻辑函数移到 `services/` 中。

**不修复的后果：** 新路由只能继续塞进这个文件。测试只能通过 HTTP 端到端测试，无法对领域逻辑做单元测试。路由冲突（当前已有两对重叠路由）难以发现。

### P2-3: God Class — `BlueprintOrchestrator`（1567 行，在 web 层）

**文件：** `src/renpy_mcp/web/chat_ws.py:697-2264`

**问题：** 整个需求澄清访谈、蓝图生成、原型流水线协调全部在一个 web 层类中。定义在 `web/` 但几乎不涉及 HTTP/WebSocket 传输——它应该是一个服务。

**修复方向：** 拆分为：
- `RefinementInterviewService` — 访谈状态机 + 槽位管理（移到 `services/`）
- `BlueprintGenerationService` — LLM 生成 + JSON 修复 + 重试（移到 `services/`）
- `PrototypeOrchestrationService` — 协调生成流水线各步骤（移到 `services/`）
- `chat_ws.py` 只保留 WebSocket 消息路由和会话绑定

**不修复的后果：** 访谈改进（refinement-interview-redesign.md 中的方案）需要在一个 1567 行的 web 类中做手术。无法脱离 WebSocket 连接单独测试访谈逻辑。

### P2-4: 硬编码的「读-改-写-回退」模式重复 10 次

**文件：** `src/renpy_mcp/web/fastapi_app.py`

**位置：** lines 828-842, 954-968, 1024-1038, 1094-1108, 1192-1206, 1260-1274, 1313-1339 等

**问题：** 每个变更端点都复制粘贴相同的 15 行模板：
```python
old = path.read_text()
try:
    # modify
    path.write_text(new)
except:
    path.write_text(old)  # rollback
    raise
```

**修复方向：** 提取为 `transactional_write(path, data)` 上下文管理器或 `AtomicFileWriter` 类。

**不修复的后果：** 继续复制粘贴；某次忘记写回退逻辑导致文件损坏且无法恢复。

### P2-5: LLM 重试逻辑硬编码 3 处且实现不一致

**文件：**
- `chat_ws.py:1068` — `max_retries = 2`，内联重试
- `prototype_generation_service.py:1023` — `max_retries = 2`，内联重试
- `chat_engine/engine.py:23` — `self.max_retries`（默认 2），不同实现
- `chat_engine/engine.py:172-202` — `_execute_tool_with_retry` **名字说重试但实际不重试**，第一次失败就返回

**修复方向：** 统一为一个 `with_retry(max_retries, backoff)` 装饰器或工具函数。修复 engine.py 的误导命名。

**不修复的后果：** 调重试次数要改 3 个文件。engine.py 的工具重试逻辑是 bug——调用方以为它在重试，但它没有。

---

## P3 — 清理性工作（低风险、提升代码卫生）

### P3-1: 删除死代码

| 项目 | 文件 | 行号 |
|------|------|------|
| `_send_bridge_command` 死副本 | `web/fastapi_app.py` | 90-118 |
| `_bridge_lock` 死依赖 | `web/fastapi_app.py` | 61 |
| `threading` import | `web/fastapi_app.py` | 8 |
| `jimeng_api_key` 死配置 | `config.py` | 52 |
| `tongyi_api_key` 死配置 | `config.py` | 53 |
| `gemini_image_model` 死配置 | `config.py` | 57 |
| `gemini_text_model` 死配置 | `config.py` | 58 |
| `ProjectInfo` 死模型 | `models.py` | 12 |
| `CurrentProjectPayload` 死模型 | `models.py` | 40 |
| `ChoiceItem` 死模型（生产代码从未构造） | `blueprint/models.py` | 83 |
| `ProjectMeta.description` 死字段 | `models.py` | 69 |
| `ProjectStatus.BLUEPRINTING/GENERATING/EDITING/IN_PROGRESS/COMPLETED` | `models.py` | 17-22 |
| `RefinementState.BRIEF_DRAFT/CHAPTER_OUTLINE_DRAFT/CHAPTER_OUTLINE_CONFIRMED` | `models.py` | 39,42,44 |
| 未使用 import: `BlueprintCharacter`, `ChapterSummary`, `SceneSummary`, `ProjectBrief` | `web/chat_ws.py` | 17,19,24,27 |

### P3-2: 删除 stale 测试

| 项目 | 文件 |
|------|------|
| `test_models.py` 测试死模型 `ProjectInfo` | `tests/unit/test_models.py:10` |
| `test_config.py` 测试死配置 `jimeng_api_key` | `tests/unit/test_config.py:27,46` |
| `test_ws_chat.py` 中无效的 `_get_provider` mock | `tests/integration/test_ws_chat.py:54-57` |

### P3-3: `"slots" in dir()` 无效守卫

**文件：** `web/chat_ws.py:926-932`

**问题：** 用 `"slots" in dir()` 检查局部变量是否存在。该变量在所有分支中都会被赋值，`dir()` 检查永远不会触发 else 分支。

**修复方向：** 删除 `dir()` 检查，直接使用 `slots` 变量。

### P3-4: JSON 提取/修复工具应该共享

**文件：**
- `web/chat_ws.py:321-440` — `_extract_json_block`、`_repair_json_text`
- `services/prototype_generation_service.py:1036-1048` — 内联 JSON 提取逻辑

**问题：** 两处都从 LLM 输出中提取 JSON，但 prototype_generation_service 没有复用 chat_ws 的 `_repair_json_text`。

**修复方向：** 提取到 `src/renpy_mcp/utils/json_repair.py`。

### P3-5: 国际化工具不应局限在 chat_ws.py

**文件：** `web/chat_ws.py:260-319` — `_contains_cjk`、`_is_clearly_english`、`_localized_text` 等

**问题：** 这些是通用的 i18n 工具函数，但只存在于 WebSocket 模块。`fastapi_app.py` 内联了自己的中英文字符串。

**修复方向：** 提取到 `src/renpy_mcp/utils/i18n.py`。

---

## 执行顺序

```
第 1 轮（本周）: P0-1, P0-2, P0-3 → 消除数据丢失和运行时崩溃风险
第 2 轮（下周）: P1-1, P1-2, P1-3, P1-4 → 消除重复、平台兼容、可观测性
第 3 轮（两周内）: P2-1, P2-2, P2-3, P2-4, P2-5 → 架构拆分、解除耦合
第 4 轮（后续）: P3-1 ~ P3-5 → 清理删除、工具提取
```

**依赖说明：**
- P1-4（大纲推导去重）应在叙事改进方案（narrative-improvement-plan.md）执行前完成，否则需要改两处
- P2-3（BlueprintOrchestrator 拆分）应在访谈改进方案（refinement-interview-redesign.md）执行前完成，否则在上帝类上做手术
- P2-1（PrototypeGenerationService 拆分）和 P2-2（create_app 拆分）可以并行，没有相互依赖
- P3 随时可以做，但建议等 P0-P2 稳定后再清理以避免合并冲突

---

## 总结

| 优先级 | 数量 | 核心问题 |
|--------|------|----------|
| P0 | 3 | 数据丢失窗口、竞态条件、事件循环阻塞 |
| P1 | 4 | 三份重复实现、Windows 硬编码、静默吞没 100+ 处、大纲推导重复 |
| P2 | 5 | 3 个上帝类/函数、读写回退模式重复、重试逻辑不一致 |
| P3 | 5 类 | 死代码清理、stale 测试、工具函数分散 |
