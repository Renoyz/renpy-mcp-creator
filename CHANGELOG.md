# Changelog

## [Unreleased]

### 2026-07-19 — Reliability fixes and open-source readiness

- Fixed a fresh-install blocker: `httpx` moved from dev extras to runtime dependencies (it is imported by `sdk_provisioner`, LLM providers, and the image service); `uv.lock` refreshed.
- Fixed all 4 known integration failures (suite now 417 passed / 0 failed): upload tests now seed a frozen blueprint and stub background removal for determinism; the mock-build path assertion resolves against the workspace.
- Preview server lifecycle: HTTP routes and MCP tools now share one `get_shared_preview_manager()`, and a FastAPI lifespan hook stops all preview servers on shutdown. Integration/E2E tests no longer leak `python -m http.server` processes (mocked starts, try/finally stops, Windows process-tree kill).
- `vn-creator start` now auto-downloads the Ren'Py SDK when missing; a failed download warns without blocking server startup.
- Build-status messages redact Ren'Py SDK absolute paths (in addition to workspace paths), keeping persisted metadata and API payloads free of local paths.
- `sdk_provisioner` only writes `.env` in source checkouts; `download_web_support.py` creates its target directory on fresh machines; `start.bat` warns when `dashboard/dist` is missing.
- Packaging metadata: `license`, `readme`, `authors`, `keywords`, `classifiers`, and repository URL added to `pyproject.toml`.
- Pinned `requires-python` to `>=3.11,<3.12`: fresh installs on Python 3.12+ fail in the `rembg`→`pymatting`→`numba` chain (no prebuilt wheels), so the resolver now stops early with a clear message. Verified with clean-venv installs on Python 3.11 (passes) and 3.12/3.13 (blocked by the guard).

### 2026-07-13 — Repository maintenance

- Removed reproducible dependency directories, build output, caches, logs, screenshots, and the obsolete UI prototype.
- Added the Electron/PyInstaller desktop packaging source, frozen Dashboard-path handling, and tested startup-failure reporting.
- Added `.env.example`, the MIT `LICENSE`, and tracked `uv.lock` for reproducible setup.
- Made the environment template safe to copy, switched packaging scripts to lockfile-driven installs, and corrected current SDK setup guidance.
- Allowed API startup from a clean source checkout before `dashboard/dist` has been built.
- Consolidated active documentation around `docs/README.md` and `docs/ROADMAP.md`; moved completed, partial, and superseded material to `docs/archive/`.
- Updated project status to report current known integration failures instead of stale all-green counts.

### 2026-04-15 — Initial unified creator milestone

### 新增

- **统一对话引擎 (Chat Engine)**
  - `ToolAdapter`：将 70 个 MCP 工具自动转换为 Anthropic / OpenAI function calling 格式
  - `AnthropicProvider`：支持 Kimi Code (`https://api.kimi.com/coding/`)
  - `OpenAICompatibleProvider`：支持 DeepSeek / 通义千问 fallback
  - `ChatEngine.run_turn()`：ReAct 单轮循环，带参数错误自纠正（最多 2 次 retry）
  - `ConfirmationState`：高影响操作（生成角色/背景、删除项目、构建）的确认状态机

- **Dashboard React 前端**
  - 使用 Vite + React + TypeScript + Tailwind CSS 初始化
  - `AppShell`：响应式布局（顶部栏 + 可折叠侧边栏 + Chat Drawer）
  - `ProjectSelectPage`：项目卡片网格，支持新建项目 Dialog
  - `ChatDrawer`：WebSocket 实时聊天，支持消息气泡、加载态、确认面板
  - `LegacyIframePage`：Story Map / 脚本编辑器 / 资源管理通过 iframe 嵌入
  - Vite dev proxy：开发时自动代理 `/api` 和 `/ws/chat` 到后端 8080

- **WebSocket 实时对话 (`/ws/chat`)**
  - 完整的 WS 消息协议：`user_message` → `tool_start` → `tool_result` → `assistant_delta`
  - 支持 `awaiting_confirmation` 暂停/恢复流程
  - 多客户端并发隔离

- **SDK 自动下载 (`SdkProvisioner`)**
  - 检测本地 Ren'Py SDK，缺失时自动从官方源或国内镜像异步下载
  - 支持 zip/tar.gz 解压，自动识别 SDK 根目录
  - 下载完成后自动写入 `.env` 的 `RENPY_SDK_PATH`

- **CLI 脚本**
  - `vn-creator start`：一键启动服务并打开浏览器
  - `vn-creator doctor`：环境诊断（Python/SDK/API Key/端口）
  - `start.bat`：Windows 双击启动脚本

- **测试**
  - 新增 21 个测试，覆盖对话引擎、WebSocket、SDK 下载
  - 该里程碑当时的测试结果：**103/103 通过**

### 变更

- `pyproject.toml` 新增依赖：`anthropic>=0.40.0`, `openai>=1.35.0`
- FastAPI `/dashboard` 路由改为 serve React 构建产物 `dashboard/dist/index.html`
- `Settings` 新增 `anthropic_api_key` 字段

### 验证

- ✅ Kimi Code `tool_use` 兼容性验证通过（`scripts/smoke_test_kimi.py`）
- ✅ 阿里百炼 `qwen-image-2.0-pro` 文生图验证通过（`scripts/smoke_test_dashscope_image.py`）
- ✅ Day 5 硬目标达成：Chat Drawer → 自然语言 → 创建项目端到端闭环
- ✅ Day 7 硬目标达成：角色生成 → 确认面板 → 保存流程跑通
