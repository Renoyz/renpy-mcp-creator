# RenPy MCP Creator

面向中文创作者的、本地优先的 Ren'Py 工程与原型生成工具。它把自然语言需求转换为可审阅的 brief、章节大纲、蓝图、场景和资产，再通过受控的 staging、commit/rollback、build 与 preview 流程生成可继续编辑的 Ren'Py 项目。

> 当前版本为 **0.1.0 开发预览版**。核心流水线可运行，但尚未发布稳定安装包，也尚未完成真实用户验证。

## 当前能力

~~~text
创建项目
  → AI intake
  → brief 确认
  → outline 确认
  → blueprint freeze
  → 多章节场景生成
  → 角色 / 背景 / 字体资产生成或上传确认
  → 脚本预览与事务性写回
  → build / preview
~~~

- FastAPI + WebSocket 后端与 React Dashboard。
- 70+ MCP 工具，覆盖脚本、资产、分析、构建和预览。
- Kimi/Anthropic 兼容、DeepSeek、通义千问及 OpenAI 兼容接口。
- 分步资产确认、项目相对路径、失败回滚和稳定资产保护。
- Windows Electron/PyInstaller 打包源码；安装包仍处于验证阶段。

## 环境要求

- Python 3.11+
- Windows 10/11（当前主要支持平台）
- Node.js 20.19+ 或 22.12+（仅从源码构建 Dashboard/Desktop 时需要）
- Ren'Py SDK 8.x（目前需自行安装并通过 `RENPY_SDK_PATH` 指定；自动下载组件尚未接入启动命令）

## 安装

使用 [uv](https://docs.astral.sh/uv/)：

~~~powershell
uv sync --extra dev
Copy-Item .env.example .env
~~~

或使用 pip：

~~~powershell
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
~~~

编辑 **.env**，至少配置一个对话模型。可选路径保持注释即可使用安全默认值；不要把路径变量留成空值，也不要提交该文件。

## 启动

首次从源码运行统一 Dashboard 前，先生成前端构建：

~~~powershell
Push-Location dashboard
npm ci
npm run build
Pop-Location
~~~

~~~powershell
# 环境诊断
vn-creator doctor

# 启动统一后端并打开 Dashboard
vn-creator start

# 或直接启动 HTTP 服务
python -m renpy_mcp.main --transport http --port 8080
~~~

未生成 Dashboard 构建时，后端 API 仍可启动，但 `/dashboard` 页面不可用。

Dashboard 开发模式：

~~~powershell
Set-Location dashboard
npm ci
npm run dev
~~~

完成 Dashboard 构建后，Windows 用户也可以运行根目录的 **start.bat**。

## Desktop 打包

桌面端源码位于 **desktop/**，PyInstaller 与构建脚本位于 **packaging/**：

~~~powershell
./packaging/scripts/build-dashboard.ps1
./packaging/scripts/build-backend.ps1
./packaging/scripts/build-electron.ps1
~~~

这些脚本会生成较大的本地构建目录；产物不会进入 Git。当前没有稳定发布的 NSIS 安装包。

## 验证

自动化测试默认不得调用真实 LLM 或图像生成服务：

~~~powershell
python -m pytest tests/unit -q
python -m pytest tests/integration -q
python -m pytest tests/e2e -v

Set-Location dashboard
npm ci
npm run build
npx vitest run

Set-Location ../desktop
npm ci
npm test
npm run build
~~~

真实 LLM E2E 仅允许手工触发，具体命令见 [AGENTS.md](AGENTS.md)。当前已知测试状态见 [ROADMAP](docs/ROADMAP.md)，不要从旧计划文档推断当前通过情况。

## 目录

- **src/renpy_mcp/**：Python 后端、服务、MCP 工具和 FastAPI。
- **dashboard/**：React Dashboard。
- **desktop/**：Electron 桌面壳。
- **packaging/**：PyInstaller 和 Windows 构建脚本。
- **tests/**：unit、integration 和 E2E 测试。
- **workspace/**：本地生成项目和调试数据，不进入 Git。
- **docs/**：当前路线图、设计与历史归档。

## 文档

- [文档索引](docs/README.md)
- [当前路线图](docs/ROADMAP.md)
- [工程中间件差距分析](docs/vn-engineering-middleware-gap-analysis.md)
- [双 Agent 未来设计](docs/dual-agent-design.md)

## 许可证

[MIT](LICENSE)
