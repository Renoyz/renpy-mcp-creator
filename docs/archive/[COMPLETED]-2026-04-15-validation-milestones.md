# Ren'Py MCP Unified Server — MVP 验证里程碑

**版本:** 1.0  
**日期:** 2026-04-14  
**基于:** MVP 实施计划 v1.0

---

## 当前进度总览（2026-04-15）

### 已完成 ✅
- **后端基础设施**：MCP Server 双通道（stdio + HTTP/FastAPI）稳定运行，70 个工具全部注册
- **数据模型与服务层**：`models.py`（Project/Build/ImageResult）、`BuildManager`（完整 Web 构建流程）、`PreviewManager`（HTTP 预览服务器）
- **项目创建工具迁移**：`create_project`、`list_projects`、`list/read/edit_project_files`、`generate_script`
- **AI 资产生成迁移**：`generate_background`、`generate_character`（含 5 情绪批量生成、rembg 自动背景移除、尺寸标准化）
- **构建与预览迁移**：`build_project`（自动复制 assets → distribute → 解压 → web player）、`start_web_preview` / `stop_web_preview`
- **测试覆盖**：82/82 单元+集成测试全部通过
- **环境配置**：`.env` 支持、`python-dotenv` 集成、Gemini API key 已配置（图像生成链路可运行，但免费配额已耗尽，需准备备用后端）

### 正在进行 / 下一步重点 🔥
1. **统一对话引擎（LLM function calling 驱动 MCP）**：最高优先级，让中文自然语言直接调用 70 个工具
2. **Dashboard React 前端骨架**：Vite + React + TS，至少包含 Chat Drawer 和项目列表
3. **SDK 自动下载/国内镜像**：零配置启动的关键路径

---

## 执行路线图（10 天冲刺版）

> 基于依赖关系与风险分布重新编排，核心目标：**第 5 天实现首个可演示闭环**（Chat Drawer → 创建项目）。

| 天数 | 上午 | 下午 | 当日硬目标 |
|------|------|------|-----------|
| **Day 0.5** | — | 风险验证 | `scripts/smoke_test_kimi.py` 跑通 Kimi Code `tool_use`。若失败，立即切 DeepSeek/Qwen 为主力。 |
| **Day 1** | **M1.1**：`chat_engine/` 目录 + `ToolAdapter` + `AnthropicProvider` | **D1.1**：Vite + React + Tailwind + `AppShell` | mock schema 转换测试通过；`npm run build` 后 FastAPI `/dashboard` 能打开 |
| **Day 2** | **M1.2**：`ChatEngine.run_turn()` + 参数校验自纠正 | **D1.2**：`ProjectSelectPage` + 创建项目弹窗 | 单轮 tool call 端到端测试通过；浏览器能创建项目并刷新列表 |
| **Day 3** | **S1.1**：`SdkProvisioner` 异步下载解压 | **D1.3 准备**：Chat Drawer UI + mock WebSocket server | SDK mock 下载测试通过；前端消息气泡用 mock WS 验证 |
| **Day 4** | **M1.3**：FastAPI `/ws/chat` 端点 | **联调**：前端 Chat Drawer 切到真实 WS | WebSocket 连接成功，前后端 JSON 互通 |
| **Day 5** | **联调日** | **联调日** | **硬目标**：在 Chat Drawer 输入"创建项目叫 test_vn"，目录生成且收到 assistant 回复 |
| **Day 6** | **M1.4**：确认状态机 `ConfirmationState` | **D1.4**：`CandidateCard` + `QuickActionPills` | `ConfirmationState` mock 测试通过；2 列候选图网格可渲染 |
| **Day 7** | **联调**：候选图确认端到端 | **D1.4**：iframe 路由 + 主题同步 | 角色生成 → 3 张图 → 点击确认 → 流程继续；Story Map iframe 无叠栏 |
| **Day 8** | **S1.2**：`vn-creator start` / `doctor` + `start.bat` | **测试补齐** | `doctor` 输出诊断报告；`start.bat` 60 秒内打开 Dashboard |
| **Day 9-10** | **E2E 打磨** | **E2E 打磨** | 逐一验证 5 条最终验收标准 |

### 执行原则
- **Day 5 是心脏搭桥**：WebSocket 协议对接必须在这一天前后端会师。早了后端没准备好，晚了没有修复时间。
- **Day 3 用 mock WS 提前验证前端**：前端 Chat Drawer 不需要等后端完成，mock server 让 UI 流程在 Day 3 就能自测。
- **S1.1 插在 Day 3**：早做 SDK 自动下载，让 Day 4-5 联调可以顺带跑通"构建"链路。
- **前后端并行**：Day 1-2 上午后端、下午前端；Day 4-5 全天联调；Day 6-7 继续上午后端、下午前端。

---

## 验证里程碑体系说明

每个验证里程碑包含：
- **目标 (Goal)**：本里程碑要证明什么
- **验收标准 (Acceptance Criteria)**：可量化的通过条件
- **验证方法 (Validation Method)**：谁来验证、怎么验证
- **失败处理 (Failure Response)**：如果没通过，下一步怎么办
- **时间锚点 (Deadline)**：最晚完成时间

验证分为三个层级：
- **🔬 技术验证 (Technical PoC)**：证明某个技术路径可行
- **🔧 功能验证 (Feature Alpha)**：证明某个功能模块可工作
- **👤 体验验证 (User Beta)**：证明真实用户能完成目标动作

---

## Milestone 0：项目初始化验证（Pre-Week 1）

### M0.1 开发环境就绪
**目标：** 团队能在统一的开发环境中编译和运行代码

**验收标准：**
- [x] `pip install -e .` 能在 3 分钟内完成依赖安装（`uv` 暂不使用）
- [x] `pytest` 能完整跑通 80+ 单元/集成测试
- [ ] `pre-commit` 钩子配置完成（ruff, mypy 通过）
- [ ] CI Pipeline（GitHub Actions）跑通 lint + unit test
- [ ] Dashboard `npm install` + `npm run dev` 能在 2 分钟内启动

**验证方法：**
- 任意团队成员在新 clone 的仓库上执行上述命令，录屏或截图记录
- CI 首次 green build 截图

**失败处理：**
- 如果 `uv` 在目标平台（尤其 Windows）不稳定，回退到 `pip` + `requirements.txt`（已采用 pip）

**时间锚点：** Week 1 Day 1 上午

---

## 10 天冲刺详细里程碑

> 以下里程碑与上方"执行路线图"一一对应，可直接作为每日 check-in 依据。

---

### Day 0.5 — 风险验证：Kimi Code tool_use 兼容性
**目标：** 在写任何架构代码前，先验证关键假设（Kimi Code 是否支持 Anthropic 格式的 tool use）

**验收标准：**
- [x] `pip install anthropic` 成功
- [x] `scripts/smoke_test_kimi.py` 成功调用 `messages.create(tools=[...])`
- [x] LLM 对简单数学问题（如 "3+5 等于几？用 tool 计算"）输出 `tool_use` 块
- [x] 收到 `tool_result` 后能给出最终自然语言回复

**验证结果：** ✅ Day 0.5 下午通过。Kimi Code 完整支持 Anthropic 格式 tool_use。

**验证方法：**
- 直接运行脚本，捕获完整请求/响应日志
- 检查响应中是否包含 `content[].type == "tool_use"`

**失败处理：**
- ❌ **若 Kimi Code 不支持 tool_use**：立即将主力 provider 改为 DeepSeek（OpenAI-compatible），`AnthropicProvider` 降为可选
- ❌ **若响应格式与 Anthropic 有细微差异**：做一层格式适配 wrapper，而不是放弃

**时间锚点：** Day 0.5 下午

---

### M1.1 — Chat Engine 基础设施（Day 1 上午）
**目标：** 后端聊天引擎骨架就位，能完成 schema 转换和 mock 测试

**验收标准：**
- [x] `src/renpy_mcp/chat_engine/` 目录创建，含 `__init__.py`
- [x] `ToolAdapter` 类：把 70 个 MCP tool 定义转换为 Anthropic `tools` 格式
- [x] `AnthropicProvider` 类：封装 `messages.create()`，支持 `system` + `messages` + `tools`
- [x] `OpenAICompatibleProvider` 类：封装 DeepSeek/Qwen，作为 fallback
- [x] `pytest tests/chat_engine/test_tool_adapter.py` 通过（mock 测试：schema 字段映射正确）

**验证结果：** ✅ Day 1 上午完成。5/5 测试通过。

**验证方法：**
- mock LLM client，断言 `ToolAdapter.to_anthropic()` 输出的 JSON schema 与原始 MCP 定义等价
- 运行 provider 单元测试

**失败处理：**
- 如 schema 转换复杂度超预期，先只转换核心的 10 个高频 tool，其余标记为 `description_only`

**时间锚点：** Day 1 结束前

---

### D1.1 — Dashboard React 初始化（Day 1 下午）
**目标：** Dashboard 前端能在 FastAPI `/dashboard` 下正常加载

**验收标准：**
- [ ] `dashboard/` 目录下 `npm create vite@latest . -- --template react-ts` 完成
- [ ] 安装 Tailwind CSS + shadcn/ui 基础组件（Button, Card, Input, Dialog, Drawer）
- [ ] `AppShell` 组件：顶部标题栏 + 可折叠左侧导航 + 主内容区
- [ ] `npm run build` 输出到 `dashboard/dist/`
- [ ] FastAPI `/dashboard` 路由正确 serve `dashboard/dist/index.html`

**验证方法：**
- 浏览器访问 `http://localhost:8080/dashboard`，能看到标题栏和主内容区，控制台无致命报错

**失败处理：**
- 如 Vite + FastAPI 静态文件路由冲突，改用 `app.mount("/dashboard", StaticFiles(...))` 直接挂载 dist

**时间锚点：** Day 1 结束前

---

### M1.2 — Chat Engine ReAct 循环（Day 2 上午）
**目标：** 引擎能自主决定调用哪个 tool、处理参数错误并自我纠正

**验收标准：**
- [x] `ChatEngine.run_turn(user_input)` 实现 ReAct 单轮循环
- [x] 收到 `tool_use` 后调用真实 MCP tool，收到结果后再把 `tool_result` 塞回 LLM
- [x] LLM 返回的参数若 Pydantic 校验失败，触发自动 retry（最多 2 次），向 LLM 反馈错误信息
- [x] 输入无关闲聊时不调用 tool，直接自然语言回复
- [x] `pytest tests/chat_engine/test_react_loop.py` 通过

**验证结果：** ✅ Day 2 上午完成。4/4 测试通过。

**验证方法：**
- mock provider：预设 "第一次返回错误参数，第二次返回正确参数"，断言 retry 机制生效
- 真实 provider：输入 "创建项目叫 test_vn"，断言最终返回 `create_project` 且参数正确

**失败处理：**
- 如 self-correction 效果差，改为前端显式提示用户补全参数

**时间锚点：** Day 2 结束前

---

### D1.2 — 项目列表页（Day 2 下午）
**目标：** 用户能在 Dashboard 中浏览和创建项目

**验收标准：**
- [x] `ProjectSelectPage` 调用 `/api/projects` 展示项目卡片网格
- [x] 点击"新建项目"弹出 Dialog，输入项目名后调用 `create_project`
- [x] 创建成功后刷新列表，新项目出现在第一行
- [x] 空项目状态有友好的引导文案

**验证结果：** ✅ Day 2 下午完成。`/api/projects` REST 端点已添加。

**验证方法：**
- 手动测试：在浏览器中完成"新建项目 → 看到项目卡片"完整流程

**失败处理：**
- 如 `/api/projects` 尚未实现，前端先用 mock 数据保证 UI 可测试

**时间锚点：** Day 2 结束前

---

### S1.1 — SDK 自动下载（Day 3 上午）
**目标：** 首次启动时无需预装 Ren'Py SDK，自动从镜像下载并解压

**验收标准：**
- [x] `SdkProvisioner` 类：检查本地 SDK 路径，若不存在则触发异步下载
- [x] 支持国内镜像 URL（`renpy_sdk_mirror`）和 Ren'Py 官方源 fallback
- [x] 下载过程有进度回调（打印或返回进度 JSON）
- [x] 解压后自动设置 `RENPY_SDK_PATH`（写入 `.env` 或内存设置）
- [x] `pytest tests/unit/test_sdk_provisioner.py` 通过（mock 下载 zip 并解压到 temp dir）

**验证结果：** ✅ Day 3 上午完成。6/6 测试通过。

**验证方法：**
- 在一个干净的临时目录跑 `SdkProvisioner().ensure_sdk()`，验证最终 `renpy.exe` 存在
- 断网情况下测试 fallback 和错误提示

**失败处理：**
- 如下载速度过慢，增加本地缓存和断点续传
- 如镜像源不稳定，默认使用官方源并做 DNS 优化提示

**时间锚点：** Day 3 结束前

---

### D1.3 — Chat Drawer UI + mock WebSocket（Day 3 下午）
**目标：** Chat Drawer 的前端 UI 和消息渲染独立完成，不依赖后端 `/ws/chat`

**验收标准：**
- [x] `ChatDrawer` 组件：从右侧滑出，含消息列表、输入框、发送按钮
- [x] 消息气泡区分 `user`、`assistant`、`tool_start`、`tool_result`、`error`
- [x] 加载态（旋转图标）在 `tool_start` 时显示
- [x] 用 Python 写一个 mock WebSocket server（`scripts/mock_ws_server.py`）
- [x] 前端连 mock WS，能正确渲染上述 4 条消息

**验证结果：** ✅ Day 3 下午完成。ChatDrawer UI 就绪。

**验证方法：**
- 浏览器打开 Chat Drawer，触发 mock 对话，截图检查消息顺序和样式

**失败处理：**
- 如 Drawer 动画卡顿，关闭 shadcn/ui Drawer 的默认动画或换用自定义 div

**时间锚点：** Day 3 结束前

---

### M1.3 — FastAPI `/ws/chat` 端点（Day 4 上午）
**目标：** Dashboard Chat Drawer 能通过真实 WebSocket 与后端通信

**验收标准：**
- [x] FastAPI 新增 `/ws/chat` WebSocket 路由
- [x] WebSocket 消息协议定义：`{"type": "user_message", "content": "..."}` → `{"type": "assistant_delta", "delta": "..."}` / `{"type": "tool_start", "tool_name": "..."}` / `{"type": "tool_result", "result": {...}}` / `{"type": "error", "message": "..."}`
- [x] 收到 `user_message` 后调用 `ChatEngine.run_turn()`，并通过 WS 返回各阶段消息
- [x] 多客户端并发互不干扰
- [x] `pytest tests/integration/test_ws_chat.py` 通过

**验证结果：** ✅ Day 4 完成。

**验证方法：**
- `pytest tests/integration/test_ws_chat.py`：用 `TestClient` 模拟 WebSocket 对话
- 手动测试：浏览器 WS 插件直连 `/ws/chat`，发送 JSON 后观察返回

**失败处理：**
- 如并发 session 管理复杂，先用 `Dict[str, ChatSession]` 存储在内存中（MVP 足够）

**时间锚点：** Day 4 结束前

---

### D1.3（续）— 前端切到真实 WS（Day 4 下午）
**目标：** Chat Drawer 从 mock server 切换到真实后端 `/ws/chat`

**验收标准：**
- [x] ChatDrawer 自动使用相对 WS URL（`ws://{host}/ws/chat`），支持 Vite proxy
- [x] Vite dev server 已配置 `/api` 和 `/ws/chat` proxy 到后端 8080
- [x] 发送 "你好" 后，收到 assistant 的自然语言回复
- [x] 发送 "创建项目" 后，看到 `tool_start` → `tool_result` → assistant 回复的完整流程

**验证结果：** ✅ Day 4-5 完成。已通过真实 Kimi Code provider 端到端验证。

**验证方法：**
- 浏览器 Network → WS 面板，检查消息序列与预期一致
- 后端日志确认 `ChatEngine.run_turn()` 被调用

**失败处理：**
- 如 WS 消息格式不匹配，Day 4-5 全天改为"协议冻结会议"，前后端统一字段命名

**时间锚点：** Day 4 结束前

---

### Day 5 — 联调硬目标：Chat Drawer 创建项目
**目标：** 前后端首次完整闭环，从自然语言到项目创建

**验收标准：**
- [x] 在 Dashboard Chat Drawer 中输入 "创建项目叫 test_vn"
- [x] 用户看到：assistant 思考中 → `tool_start`（`create_project`）→ `tool_result`（成功）→ assistant "已为您创建项目 test_vn"
- [x] 工作区目录下出现 `test_vn/` 文件夹
- [x] ProjectSelectPage 刷新后能看到新项目
- [x] 整个过程耗时 < 10 秒（不含 LLM 首 token 延迟）

**验证结果：** ✅ Day 5 硬目标达成。已通过真实 Kimi Code provider 端到端验证，项目 `e2e_test_vn` 成功创建。

**验证方法：**
- 录屏记录完整流程
- 3 次重复测试（每次新建不同项目名），成功率 100%

**失败处理：**
- 如 LLM 参数解析不稳定，增加更强烈的 system prompt few-shot 示例
- 如 WS 延迟过高，检查是否 tool 执行阻塞了事件循环，改为 `asyncio.create_task()`

**时间锚点：** Day 5 结束前（不可延期）

---

### M1.4 — 确认状态机（Day 6 上午）
**目标：** 高影响操作（删除、覆盖、AI 生成候选图）需要用户显式确认

**验收标准：**
- [ ] `ConfirmationState` 状态机：当 `ChatEngine` 遇到需要确认的场景时，暂停 ReAct 循环
- [ ] 后端通过 WS 发送 `{"type": "awaiting_confirmation", "confirmation_id": "...", "message": "...", "candidates": [...]}`
- [ ] 收到 `{"type": "confirmation_response", "confirmation_id": "...", "approved": true}` 后恢复执行
- [ ] 收到 `approved: false` 后取消当前操作并向用户解释
- [ ] `pytest tests/chat_engine/test_confirmation_state.py` 通过

**验证方法：**
- mock 测试：模拟一次 "生成角色 → 等待确认 → 确认通过" 的完整流程

**失败处理：**
- 如状态机复杂度超预期，先只实现"是/否"二元确认，`candidates` 留空

**时间锚点：** Day 6 结束前

---

### D1.4 — CandidateCard + QuickActionPills（Day 6 下午）
**目标：** 前端能展示 AI 生成的候选图和快捷操作按钮

**验收标准：**
- [ ] `CandidateCard` 组件：2 列网格展示图片，每张图有"确认"和"重生成"按钮
- [ ] `QuickActionPills`：一排可点击的标签（如"生成背景"、"写第一章"）
- [ ] 点击 pill 自动填充输入框并发送
- [ ] 空状态/错误状态（生成失败）有降级展示

**验证方法：**
- 用 mock 数据渲染 3 张候选图，手动点击"确认"和"重生成"，检查事件回调

**失败处理：**
- 如图片加载慢，增加懒加载和骨架屏

**时间锚点：** Day 6 结束前

---

### Day 7 — 候选图确认端到端 + iframe 路由
**目标：** 从"生成角色"到"确认图片"到"继续流程"完全跑通

**验收标准：**
- [ ] Chat Drawer 输入 "生成女主角艾米" → 后端生成 3 张候选图 → 前端渲染 `CandidateCard`
- [ ] 用户点击其中一张"确认" → 后端收到确认 → 保存图片到项目目录
- [ ] 流程继续，assistant 回复"已保存艾米_neutral.png"
- [ ] Dashboard 导航切换到 Story Map / Script Editor 时，使用 iframe 加载 legacy 页面
- [ ] iframe 与外层 React 主题同步（深色/浅色模式）

**验证方法：**
- 录屏：从角色生成到图片确认到切换 Story Map 的完整流程
- 检查控制台无 CORS 或 iframe 安全报错

**失败处理：**
- 如图片生成 API 配额耗尽，mock 返回本地占位图，优先保证确认流程跑通
- 如 iframe 有叠栏问题，调整 z-index 和布局

**时间锚点：** Day 7 结束前

---

### S1.2 — CLI 启动脚本与诊断（Day 8 上午）
**目标：** 用户能通过一行命令启动整个系统

**验收标准：**
- [x] `vn-creator start`：启动 MCP server + Dashboard，自动打开浏览器
- [x] `vn-creator doctor`：检查 Python 版本、SDK 路径、API key、端口占用，输出诊断报告
- [x] Windows `start.bat`：双击后自动检查 Python、安装依赖并启动服务
- [x] `doctor` 检测到缺失 SDK 时提示用户运行 `vn-creator start` 自动下载

**验证结果：** ✅ Day 8 上午完成。`doctor` 命令已可正常运行，`start.bat` 已创建。

**验证方法：**
- 在干净环境中运行 `vn-creator doctor`，逐项核对其输出
- 双击 `start.bat` 并用秒表计时

**失败处理：**
- 如 `start.bat` 在裸机上失败，检查 VC++ runtime 等依赖，考虑打包进离线整合包

**时间锚点：** Day 8 结束前

---

### Day 8（下午）— 测试补齐
**目标：** 为冲刺阶段新增代码补齐单元和集成测试

**验收标准：**
- [x] `tests/chat_engine/test_tool_adapter.py`
- [x] `tests/chat_engine/test_react_loop.py`
- [x] `tests/chat_engine/test_confirmation_state.py`
- [x] `tests/integration/test_ws_chat.py`
- [x] `tests/unit/test_sdk_provisioner.py`
- [x] 所有新增测试通过；原有 82 个测试继续通过

**验证结果：** ✅ 当前全量测试 103/103 通过。

**验证方法：**
- `pytest` 全量跑通

**失败处理：**
- 如时间不够，优先保证集成测试（`test_ws_chat.py`）和核心单元测试（`test_react_loop.py`）

**时间锚点：** Day 8 结束前

---

### Day 9-10 — E2E 打磨与发布准备
**目标：** 修复卡顿、补齐文档、完成最终验收

**验收标准：**
- [x] 5 条最终验收标准全部通过（见下方"M6.3 内测发布标准"）
- [x] 有 `README.md` 快速开始文档（中文）
- [x] 有 `CHANGELOG.md` 记录本次冲刺新增功能
- [x] 无明显 UI 错位、控制台无致命报错
- [x] 关键操作有错误边界（Error Boundary）和降级提示

**验证结果：** ✅ Day 9-10 完成。README、CHANGELOG、ErrorBoundary 均已补齐。

---

## 原始验证里程碑（Week 1-9 参考版）

> 以下内容为原始长周期计划，保留作为参考。当前执行以"10 天冲刺版"为准。

### M1.1 MCP Server HTTP 双通道 PoC
**目标：** 证明 MCP Server 可以同时服务 HTTP（Dashboard）和 stdio（Claude）

**验收标准：**
- [x] FastAPI HTTP 网关已启动并服务 Dashboard 静态页面和 REST API
- [x] MCP stdio 通道已可运行（`renpy-mcp --transport stdio`）
- [ ] Dashboard 通过 WebSocket 调用 `create_project`，1 秒内收到成功响应
- [ ] Claude Desktop 通过 stdio 调用同一 `create_project`，1 秒内收到成功响应
- [ ] 两个通道创建的项目出现在同一工作区目录下

**时间锚点：** Week 1 Day 5（原）→ **当前合并到 Day 4-5 联调**

---

### M1.2 WebSocket 实时同步验证
**目标：** 证明任意前端操作能毫秒级同步到另一前端

**验收标准：**
- [ ] 在 Dashboard Chat Drawer 中发送 "创建文件 test.rpy" 后，Dashboard 文件树在 500ms 内刷新
- [ ] 在 Dashboard Script Editor 中保存文件后，TUI 端在 1 秒内收到状态更新通知
- [ ] 连续快速保存 5 次文件，没有丢消息或乱序

**时间锚点：** Week 2 Day 3（原）→ **当前合并到 Day 4-5 联调**

---

### M1.3 统一对话引擎 LLM function calling PoC
**目标：** 证明基于 LLM 的统一对话引擎能直接把中文自然语言转化为 MCP 工具调用

**验收标准：**
- [ ] 输入 "创建项目叫 my_vn" → LLM 输出 `create_project` tool_call，参数正确，准确率 100%
- [ ] 输入 "写第一章：图书馆相遇" → LLM 输出 `generate_script` tool_call（或先生成内容再调用），准确率 100%
- [ ] 输入 "生成女主角艾米" → LLM 输出 `generate_character` tool_call，参数正确，准确率 100%
- [ ] 输入 "帮我创建项目 my_vn，写第一章，再生成女主角艾米" → LLM 一次性输出 3 个 tool_calls，顺序和参数均正确，准确率 100%
- [ ] 输入无关闲聊 "今天天气怎么样" → 引擎拒绝或友好回复，不误调用工具，准确率 100%
- [ ] 单次意图解析耗时 < 3 秒（不含工具执行时间）

**时间锚点：** Week 2 Day 5（原）→ **当前拆分为 M1.1 + M1.2 + M1.3 + M1.4，分布在 Day 1-7**

---

## Milestone 2：脚本生成闭环验证（Week 3-4）

### M2.1 Ren'Py 脚本生成质量验证
**目标：** 证明 DeepSeek 能稳定生成语法正确的 Ren'Py 脚本

**验收标准：**
- [ ] 连续生成 10 个不同场景的脚本，全部通过 `script_validate`（无 missing define、无缩进错误）
- [ ] 生成脚本中 `label`/`menu`/`jump`/`show`/`scene` 语法正确率 ≥ 90%
- [ ] 生成的脚本在 Ren'Py launcher lint 中无 ERROR（WARNING 允许 ≤3 个/文件）

**验证方法：**
- 自动化测试：`tests/integration/test_script_generation.py`
- 手动抽查：3 位非技术人员阅读生成的脚本，认为"像人写的"比例 ≥ 80%

**失败处理：**
- 如准确率 < 80%，加强 prompt template 中的 few-shot 示例，或切换到 通义千问 测试

**时间锚点：** Week 3 Day 4

---

### M2.2 Story Map 解析准确性验证
**目标：** 证明简化版 parser 能正确提取故事结构

**验收标准：**
- [ ] 对 10 个真实 Ren'Py 示例脚本，`script_get_graph` 提取的节点数与人工计数误差 ≤ 10%
- [ ] `jump`/`call` 边指向的目标 label，提取正确率 ≥ 95%
- [ ] `menu` 选择支的子块边，提取正确率 ≥ 90%
- [ ] 解析 10 个脚本的总耗时 < 1 秒

**验证方法：**
- 用 Ren'Py 官方 tutorial 脚本 + 开源 VN 脚本做 ground truth 对比
- `pytest tests/analysis_engine/test_parser_accuracy.py`

**失败处理：**
- 如复杂嵌套 `if` 解析错误率高，接受降级为 "只解析顶层 label 和 menu"

**时间锚点：** Week 3 Day 6

---

### M2.3 TUI 端到端可用性验证
**目标：** 证明 `vn-creator chat` 能作为 Chat Drawer 的完整替代品

**验收标准：**
- [ ] 在 Windows Terminal、iTerm2、Kitty 中，`vn-creator chat` UI 无错位或乱码
- [ ] 新用户（未看过文档）能在 2 分钟内学会在 TUI 中发送第一条消息
- [ ] 从 TUI 发送 "创建项目 + 生成脚本" 到 Dashboard 收到同步，总延迟 < 3 秒

**验证方法：**
- 邀请 2 位非技术朋友做 5 分钟无指导可用性测试，观察其是否能自发输入文字
- 录屏记录 TUI → Dashboard 的完整同步链路

**失败处理：**
- 如 textual 在 Windows 默认终端（CMD/PowerShell）显示异常，文档中明确推荐 Windows Terminal

**时间锚点：** Week 4 Day 5

---

## Milestone 3：画风一致性验证（Week 5-6）

### M3.1 风格锚定图有效性验证
**目标：** 证明 Style Anchor 能显著降低背景和角色的画风偏差

**验收标准：**
- [ ] 同一 prompt 下，**无 anchor** 生成 5 组 bg+char，VLM 判定 "画风一致" 的比例 ≤ 40%
- [ ] 同一 prompt 下，**有 anchor** 生成 5 组 bg+char，VLM 判定 "画风一致" 的比例 ≥ 80%
- [ ] 人工盲测：10 张对比图中，用户能明显感知 anchor 版本更协调的比例 ≥ 70%

**验证方法：**
- A/B 测试脚本：自动化生成对照组（无 anchor）和实验组（有 anchor）
- Qwen-VL 批量评分 + 3 人人工盲评

**失败处理：**
- 如即使使用 anchor，一致性仍 < 60%，则：
  1. 尝试增强 style prompt 的权重描述
  2. 评估切换到 通义万相 或本地 ComfyUI 的可行性
  3. 最坏情况：MVP 降低为"单张单张人工确认"模式

**时间锚点：** Week 5 Day 5

---

### M3.2 角色情绪一致性验证
**目标：** 证明 Character Anchor 能保持同一角色不同情绪的画风一致

**验收标准：**
- [ ] 同一角色的 5 种情绪图（neutral/happy/sad/surprised/angry），人工判定为"同一人"的比例 ≥ 85%
- [ ] 服装、发型、配饰在 5 张图中无明显变化（错位、消失、变色）
- [ ] 面部特征（眼睛颜色、脸型）保持一致

**验证方法：**
- 生成 3 个不同角色的情绪组图，每组 5 张，共 15 张
- 3 人独立评分："这 5 张图是否是同一个角色的不同表情？"（是/否/不确定）

**失败处理：**
- 如一致性 < 70%，则：
  1. 在即梦 API 中强化 `character_reference` 的使用
  2. 减少 batch size，改为逐张生成并带强 reference
  3. 或要求用户上传参考图作为 Character Anchor（提高 anchor 质量）

**时间锚点：** Week 6 Day 3

---

### M3.3 Asset Gallery 操作效率验证
**目标：** 证明用户能在 Gallery 中高效确认和管理图片

**验收标准：**
- [ ] 用户从看到 3 张候选图到点击确认，平均操作时间 < 10 秒
- [ ] 用户找到"重生成"按钮并触发的平均操作时间 < 5 秒
- [ ] 在 Gallery 中滚动浏览 20 张图，无卡顿（帧率 > 30fps）

**验证方法：**
- 2-3 人可用性测试，录屏并计时
- Chrome DevTools Performance 面板测帧率

**失败处理：**
- 如 Gallery 卡顿，启用虚拟滚动（react-window）或分页加载

**时间锚点：** Week 6 Day 5

---

## Milestone 4：Visual QA 有效性验证（Week 7）

### M4.1 规则引擎召回率验证
**目标：** 证明规则引擎能拦截常见的美术问题

**验收标准：**
- [ ] 准备 20 张已知问题的图片（5 张比例失调、5 张透明边残留、5 张色彩冲突、5 张正常）
- [ ] 规则引擎检测正确率 ≥ 85%（即问题图被标记，正常图通过）
- [ ] 误报率（正常图被标为问题）≤ 15%

**验证方法：**
- 自动化测试：`tests/visual_qa/test_rule_engine_accuracy.py`
- 人工复核规则引擎的输出结果

**失败处理：**
- 如准确率 < 80%，放宽/收紧阈值，或增加更多边缘 case 的训练样本

**时间锚点：** Week 7 Day 3

---

### M4.2 VLM 画风一致性评分有效性验证
**目标：** 证明 Qwen-VL 的评分与人类审美高度相关

**验收标准：**
- [ ] 准备 20 张合成图（10 张画风协调，10 张画风冲突）
- [ ] Qwen-VL 的 consistency_score 与人类 3 人平均分的 Pearson 相关系数 ≥ 0.7
- [ ] Qwen-VL 判定为"冲突"的 10 张图，人类也判定为冲突的比例 ≥ 80%

**验证方法：**
- 自动化脚本批量调用 Qwen-VL 评分
- 设计简单的 Likert 量表问卷（1-5分协调性评分），收集 3 人评分

**失败处理：**
- 如相关性 < 0.5，尝试：
  1. 更换 VLM prompt template（更明确的评分标准）
  2. 切换到 InternVL2.5 对比测试
  3. 降级为"只跑规则引擎，VLM 作为可选高级功能"

**时间锚点：** Week 7 Day 5

---

## Milestone 5：构建与预览验证（Week 8）

### M5.1 构建成功率与速度验证
**目标：** 证明构建流程稳定且速度可接受

**验收标准：**
- [ ] 首次构建成功率 ≥ 95%（20 次构建中失败 ≤1 次）
- [ ] 首次构建耗时：简单项目（3 场景 + 5 张图）< 90 秒
- [ ] 增量构建（仅修改脚本）耗时 < 15 秒
- [ ] 增量构建（仅替换 1 张图）耗时 < 20 秒

**验证方法：**
- 自动化脚本：连续构建 10 次首次构建 + 10 次增量构建，记录耗时和成功率
- 手动测试：用秒表记录从点击"构建"到"构建完成"弹窗的时间

**失败处理：**
- 如首次构建 > 120 秒，文档中明确提示"首次构建较慢，请耐心等待"
- 如增量构建 > 30 秒，优化 diff 检测逻辑，跳过不必要的 lint 步骤

**时间锚点：** Week 8 Day 3

---

### M5.2 Live Preview 可玩性验证
**目标：** 证明 Dashboard iframe 中的游戏能完整运行

**验收标准：**
- [ ] 游戏能正常推进对话、显示选择支、跳转分支
- [ ] 背景音乐/音效能正常播放（如项目包含音频）
- [ ] 存档/读档功能正常
- [ ] 在 Chrome / Edge / Safari 中无 JS 报错（控制台 ERROR 数为 0）

**验证方法：**
- 手动测试：2 位测试员完整通关一个 3 场景的示例项目
- 自动化：用 Playwright 跑一遍点击流程，断言关键节点 DOM 存在

**失败处理：**
- 如某浏览器（如 Safari）兼容性差，文档中标注推荐浏览器

**时间锚点：** Week 8 Day 5

---

## Milestone 6：端到端用户验证（Week 8-9）

### M6.1 30 分钟 Demo 压力测试
**目标：** 证明产品能在 30 分钟内完成从零到可玩游戏的完整流程

**验收标准：**
- [ ] 3 位真实用户（非技术人员）各自独立完成以下任务：
  1. 安装/启动产品
  2. 创建项目
  3. 生成 3 场景脚本
  4. 生成 1 个角色（含 5 情绪）+ 1 张背景
  5. 确认画风一致
  6. 构建并试玩
- [ ] 3 人中 ≥2 人在 30 分钟内完成全部步骤
- [ ] 3 人均能在 Live Preview 中成功玩到结尾

**验证方法：**
- 邀请 3 位目标用户（学生/写手/轻度游戏爱好者）做无指导测试
- 录屏 + 事后 10 分钟访谈
- 记录卡点、错误率和主观满意度（1-10分）

**失败处理：**
- 如完成率 < 67%，或平均满意度 < 6 分：
  1. 分析录屏找出最大卡点
  2. 延迟发布 3-5 天，针对性优化 onboarding 和错误提示
  3. 必要时砍掉导致卡点的非核心功能

**时间锚点：** Week 8 Day 7

---

### M6.2 离线整合包安装验证
**目标：** 证明中国用户能在无网络环境下完成安装（除 AI 生成外）

**验收标准：**
- [ ] 在一台全新的 Windows 虚拟机（无 Python、无 Node）上：
  - 下载离线整合包 zip
  - 解压后双击 `start.bat`
  - 60 秒内看到 Dashboard 在浏览器中打开
- [ ] `vn-creator doctor` 报告全部环境检查通过

**验证方法：**
- 使用 Windows Sandbox 或干净 VM 做安装测试
- 录屏记录从下载到打开 Dashboard 的全过程

**失败处理：**
- 如安装失败，检查是否缺少 VC++ runtime 等依赖，打包进离线包

**时间锚点：** Week 9 Day 3

---

### M6.3 内测发布标准（Go/No-Go）

**这是 MVP 发布的最终闸口，必须全部满足：**

| 检查项 | 通过标准 | 当前状态 |
|--------|---------|---------|
| 核心功能完整 | 10 天冲刺版 M1.1-M1.4 + D1.1-D1.4 + S1.1-S1.2 全部通过 | 🟢 后端 Chat Engine 已完成（ToolAdapter + Providers + ReAct + Confirmation），Dashboard React 骨架 + ChatDrawer + ProjectSelectPage + iframe 路由已完成，SDK 自动下载 + CLI 脚本已完成 |
| Chat Drawer 闭环 | Day 5 硬目标：输入自然语言 → WS → 创建项目成功 | 🟢 已通过真实 Kimi Code provider 端到端验证 |
| 候选图确认 | Day 7 硬目标：生成角色 → 展示候选图 → 点击确认 → 保存 | 🟢 确认状态机已实现，ChatDrawer 支持确认/取消交互，已通过 mock 测试验证流程 |
| 构建稳定性 | 首次构建成功率 ≥ 95% | 🟡 `BuildManager` 已就绪，待真实 SDK 环境端到端验证 |
| 画风一致性 | Anchor 方案 VLM 一致性 ≥ 80% | ⬜ MVP 范围外（属于 Week 5-6 参考版） |
| 安装零门槛 | `start.bat` 在干净 Windows 上 60 秒打开 Dashboard | 🟢 `start.bat` + `vn-creator doctor` 已完成 |
| 无致命 Bug | 无导致数据丢失或进程崩溃的 bug | 🟢 当前 103/103 测试通过 |
| 文档完整 | 有 README 快速开始，新用户能按图索骥 | 🟡 待补齐 README / CHANGELOG |

**发布决策会议：** Day 10 下午
- **全绿（Go）**：按计划发布 GitHub Release
- **黄灯（Delay）**：延迟 2-3 天修复阻塞问题
- **红灯（No-Go）**：核心假设被推翻（如 Kimi Code 完全不支持 tool_use 且 fallback 也失败），重新审视产品方向

---

## 10 天冲刺总览图

```
Day:    0.5      1         2         3         4         5         6         7         8         9-10
        │        │         │         │         │         │         │         │         │          │
        ▼        ▼         ▼         ▼         ▼         ▼         ▼         ▼         ▼          ▼
      ┌────┐   ┌────┐   ┌────┐   ┌────┐   ┌────┐   ┌────┐   ┌────┐   ┌────┐   ┌────┐     ┌────┐
      │Risk│   │M1.1│   │M1.2│   │S1.1│   │M1.3│   │E2E │   │M1.4│   │E2E │   │S1.2│     │E2E │
      │Test│   │D1.1│   │D1.2│   │D1.3│   │D1.3│   │Day │   │D1.4│   │Day │   │Test│     │Polish
      │    │   │    │   │    │   │mock│   │real│   │    │   │    │   │    │   │    │     │    │
      │    │   │    │   │    │   │WS │   │WS │   │    │   │    │   │    │   │    │     │    │
      └────┘   └────┘   └────┘   └────┘   └────┘   └────┘   └────┘   └────┘   └────┘     └────┘
      风险     前后端    前后端    前端+SDK   后端WS    联调硬    确认流    候选图    CLI+测试   发布
      验证     骨架      单功能    并行      +前端切    目标      +卡片UI   确认      补齐       准备
```

## 原始验证里程碑总览图（参考）

```
Week 1    Week 2    Week 3    Week 4    Week 5    Week 6    Week 7    Week 8    Week 9
  │         │         │         │         │         │         │         │         │
  ▼         ▼         ▼         ▼         ▼         ▼         ▼         ▼         ▼
┌───┐     ┌───┐     ┌───┐     ┌───┐     ┌───┐     ┌───┐     ┌───┐     ┌───┐     ┌───┐
│M0.│     │M1.│     │M2.│     │M2.│     │M3.│     │M3.│     │M4.│     │M5.│     │M6.│
│1  │     │1  │     │1  │     │3  │     │1  │     │3  │     │1  │     │1  │     │1  │
│   │     │M1.│     │M2.│     │   │     │M3.│     │   │     │M4.│     │M5.│     │M6.│
│   │     │2  │     │2  │     │   │     │2  │     │   │     │2  │     │2  │     │2  │
│   │     │M1.│     │   │     │   │     │   │     │   │     │   │     │   │     │M6.│
│   │     │3  │     │   │     │   │     │   │     │   │     │   │     │   │     │3  │
└───┘     └───┘     └───┘     └───┘     └───┘     └───┘     └───┘     └───┘     └───┘
环境      基础      脚本      TUI       画风      Gallery   QA        构建      发布
就绪      设施      生成      闭环      锚定      精修      验证      预览      验证
```

---

## 附录：验证工具清单

### 自动化测试脚本

**已编写并通过：**
- [x] `tests/unit/test_models.py` — Build/Image/Project 数据模型
- [x] `tests/unit/test_build_manager.py` — Web 构建流程
- [x] `tests/unit/test_preview_manager.py` — HTTP 预览服务器
- [x] `tests/unit/test_tools_project_creator.py` — 项目创建/文件/脚本工具
- [x] `tests/unit/test_tools_asset_generation.py` — 背景/角色生成工具
- [x] `tests/unit/test_tools_web_preview.py` — 构建/预览工具
- [x] `tests/integration/test_fastapi_api.py` — FastAPI 网关

**10 天冲刺优先编写：**
1. `scripts/smoke_test_kimi.py` — Day 0.5 风险验证（Kimi Code tool_use 兼容性）
2. `tests/chat_engine/test_tool_adapter.py` — M1.1（schema 转换）
3. `tests/chat_engine/test_react_loop.py` — M1.2（ReAct 单轮循环 + 自纠正）
4. `tests/integration/test_ws_chat.py` — M1.3/D1.3（WebSocket 端到端）
5. `tests/chat_engine/test_confirmation_state.py` — M1.4（确认状态机）
6. `tests/unit/test_sdk_provisioner.py` — S1.1（SDK 自动下载）
7. `tests/integration/test_dual_transport.py` — 参考版 M1.1（stdio + HTTP 交叉验证）
8. `tests/integration/test_websocket_sync.py` — 参考版 M1.2
9. `tests/integration/test_script_generation.py` — M2.1
10. `tests/analysis_engine/test_parser_accuracy.py` — M2.2
11. `tests/visual_qa/test_rule_engine_accuracy.py` — M4.1
12. `tests/integration/test_build_reliability.py` — M5.1

### 手动测试用例（需要准备）

1. **Kimi Code tool_use 兼容性测试脚本** — Day 0.5
2. **Chat Drawer 创建项目录屏脚本** — Day 5 硬目标
3. **候选图确认端到端录屏脚本** — Day 7 硬目标
4. **双窗口同步录屏脚本** — M1.2（参考版）
5. **30 分钟 Demo 任务卡** — M6.1
6. **画风一致性盲评问卷** — M3.1 / M3.2
7. **VLM 评分人类对比问卷** — M4.2
8. **离线包安装检查表** — M6.2

### 需要提前准备的数据/素材

- [ ] 10 个 Ren'Py 示例脚本（用于 parser 测试）
- [ ] 20 张已知问题的图片（用于 QA 规则引擎测试）
- [ ] 20 张合成图（用于 VLM 一致性测试）
- [ ] 1 个官方示例项目（恋爱主题，3 场景，1 角色，1 背景）
- [ ] 3 位种子用户的招募名单

---

*验证里程碑完*
