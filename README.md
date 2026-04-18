# RenPy MCP Creator

AI 驱动的 Ren'Py 视觉小说开发工具。通过自然语言对话，让大模型直接调用 70+ 个专业工具，完成从项目创建、脚本生成、角色/背景图生成到构建预览的完整流程。

## 快速开始

### 环境要求

- Python 3.11+
- Windows 10/11（当前主要支持平台）
- 可选：Node.js 18+（仅开发 Dashboard 前端时需要）

### 安装

```bash
# 1. 克隆仓库
git clone <repo-url>
cd renpy-mcp-unified-design

# 2. 安装 Python 依赖
pip install -e .

# 3. 配置 API Key（至少需要一项用于对话引擎）
cp .env.example .env
# 编辑 .env，填入 ANTHROPIC_API_KEY（Kimi Code）或 DEEPSEEK_API_KEY / QWEN_API_KEY
```

### 启动

#### 方式一：双击启动（推荐新手）

Windows 用户直接双击项目根目录的 `start.bat`，60 秒内会自动：
- 检查并安装 Python 依赖
- 启动 MCP Server + Dashboard
- 在浏览器中打开 Dashboard

#### 方式二：命令行启动

```bash
# 启动服务并自动打开浏览器
vn-creator start

# 指定端口
vn-creator start --port 8080
```

#### 方式三：开发模式

```bash
# 终端 1：启动统一服务（FastAPI + Dashboard）
python -m renpy_mcp.main --transport http --port 8080

# 终端 2：启动前端开发服务器（热更新）
cd dashboard
npm install
npm run dev
```

### 环境诊断

```bash
vn-creator doctor
```

输出包括：
- Python 版本检查
- Ren'Py SDK 是否存在（缺失时会自动下载）
- API Key 配置状态
- 端口占用情况

### 使用 Dashboard

1. 打开 `http://localhost:8080/dashboard`
2. 在 **项目列表** 页面创建新项目
3. 点击进入项目 **Workspace**
4. 在 Workspace 中查看 Blueprint、Story Map、Scene 内容
5. 点击右上角 **AI 助手** 打开 Chat Drawer
6. 用中文自然语言输入指令，例如：
   - "写第一章：图书馆相遇"
   - "生成女主角艾米"
   - "构建项目并启动预览"

## 主要功能

- **统一对话引擎**：基于 LLM function calling，支持 Kimi Code（Anthropic 兼容）、DeepSeek、通义千问
- **Dashboard 面板**：React + Vite + Tailwind，包含项目列表、Workspace（Blueprint / Story Map / Scene）、Chat Drawer
- **70+ MCP 工具**：项目创建、脚本生成、AST 分析、资源管理、构建预览、实时调试
- **SDK 自动下载**：首次启动自动从镜像下载 Ren'Py SDK，无需手动配置
- **候选图确认**：生成角色/背景时支持确认/取消交互

## 项目结构

```
renpy-mcp-unified-design/
├── src/renpy_mcp/          # Python 后端
│   ├── chat_engine/        # 对话引擎（ReAct + Confirmation）
│   ├── services/           # 业务服务（BuildManager, PreviewManager, SdkProvisioner...）
│   ├── tools/              # 70+ MCP 工具
│   ├── web/                # FastAPI + WebSocket
│   └── cli/                # vn-creator CLI
├── dashboard/              # React 前端
│   ├── src/pages/          # 页面组件
│   └── src/components/     # 共享组件
├── tests/                  # 单元/集成测试
├── scripts/                # 辅助脚本（smoke test, mock WS server）
├── start.bat               # Windows 一键启动
└── pyproject.toml          # Python 项目配置
```

## 测试

```bash
# 运行全部测试
pytest

# 当前测试状态：243/243 通过（含 E2E）
```

## 许可证

MIT
