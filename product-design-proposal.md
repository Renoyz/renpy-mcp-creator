# Ren'Py MCP 产品设计方案

**版本:** 2.0 — Creator 聚焦版  
**日期:** 2026-04-14  
**定位:** 中国创作者的 AI 视觉小说生成器  
**目标:** 让不会代码的人，用自然语言在 30 分钟内生成可玩的视觉小说

---

## 1. 产品定位与核心主张

### 1.1 一句话定位
**"会说话就能做 Galgame"**

我们不是做 Ren'Py 的辅助开发工具，而是做一款**面向中国创作者的一站式 AI 视觉小说生成器**。用户不需要懂代码、不需要会画画、不需要配环境，只需要用中文描述故事，就能产出带立绘、背景、分支剧情的可玩 Web 游戏。

### 1.2 核心主张
- **零代码**: 不需要写 Ren'Py 脚本，AI 根据自然语言生成完整代码
- **零美术**: AI 一键生成背景和角色，自动保证画风一致
- **零配置**: 自动下载引擎、自动构建、一键预览，开箱即用
- **中国可用**: 默认接入国产模型，所有下载走国内镜像

### 1.3 与原版设计规格书的核心差异

| 原版设计 | 本方案 | 原因 |
|---------|--------|------|
| 服务 Creator + Developer + Team Lead | **只做 Creator** | 单点打透，避免功能分散 |
| 46 个 MCP 工具 | **约 20 个核心工具** | 降低认知负担 |
| Live Bridge 实时调试 | **砍掉** | 对创作者非刚需，开发成本高 |
| 自定义 AST Parser + 重构引擎 | **降级为只读分析器** | 不做代码重构，只做结构展示 |
| 翻译管理、自动化测试 | **不做** | MVP 阶段不做 |
| Gemini 默认图像生成 | **即梦/通义万相 + 风格锚定** | 国内可访问 + 解决画风一致性问题 |
| 独立 Web Dashboard 为主 | **统一对话引擎 + 多前端皮肤** | Chat Drawer 和 CLI TUI 是同一引擎的不同皮肤 |

---

## 2. 产品形态：统一对话引擎 + 多前端皮肤

### 2.1 核心原则

**Chat Drawer 和 `vn-creator` 不是两个独立产品，而是同一个"统一对话引擎"的不同皮肤。**

用户无论是在浏览器抽屉里打字，还是在终端里敲命令，本质上都是在和同一个对话引擎交互。这个引擎负责：
- 理解用户意图
- 编排 MCP 工具调用
- 管理会话状态（如待确认候选图）
- 将结果以适合当前前端的形式返回

```
前端皮肤层
├── Web Dashboard 中的 Chat Drawer  (React + WebSocket)
├── vn-creator CLI 的 Chat Mode      (Python TUI + WebSocket)
├── vn-creator CLI 的 Command Mode   (快捷命令，直接调用引擎)
└── 第三方 MCP 客户端               (Claude Desktop / Cursor / stdio)
         │
         ▼
    统一对话引擎 (Unified Chat Engine)
         │
         ▼
    MCP Server Core
```

### 2.2 为什么必须是"统一引擎 + 多皮肤"？

| 前端 | 最适合的场景 | 不适合的场景 |
|------|------------|-------------|
| **Chat Drawer** | Dashboard 内快速补一句生成指令 | 深度创意 brainstorming |
| **vn-creator TUI** | 终端党的完整对话创作流程 | 看图确认、拖拽编辑 |
| **vn-creator 快捷命令** | 开发者习惯的一次性操作 | 需要多轮确认的复杂生成 |
| **Claude Desktop** | 深度创意对话、长文构思 | 实时看图确认 |
| **Dashboard 主界面** | 看图选图、Story Map 确认、iframe 试玩 | 自然语言批量生成 |

**没有一个前端能通吃所有场景，但对话引擎只需要写一次。**

### 2.3 "对话生成，面板确认"（Chat to Generate, Dashboard to Verify）

虽然 Chat 入口有多个皮肤，但创作流程的核心理念不变：
- **Chat 侧（任意皮肤）负责"想"和"做"**：创意输入、批量生成、大段修改
- **Dashboard 主界面负责"看"和"调"**：结构确认、图片审查、精细编辑、即时试玩

### 2.4 前端分工边界

| 操作类型 | 首选入口 | 说明 |
|---------|---------|------|
| **创建项目** | Chat（任意皮肤） | "帮我创建一个校园恋爱 VN" |
| **生成脚本章节** | Chat | "写第二章：告白场景" |
| **生成立绘/背景** | Chat | "生成女主角艾米" |
| **确认画风锚定图** | Dashboard | 3 张候选图并排对比，点击选择 |
| **查看故事结构** | Dashboard | Story Map 只读可视化 |
| **微调单句台词** | Dashboard | Script Editor 直接编辑 |
| **重生成某张图** | Dashboard | Asset Gallery 点击重生成 |
| **查看 Visual QA 报告** | Dashboard | 结构化报告 + 截图标注 |
| **试玩游戏** | Dashboard | Live Preview iframe |
| **构建导出** | Chat 或 Dashboard | Chat 中说"构建并给我链接" 或 Dashboard 一键构建 |

---

## 3. 统一对话引擎（Unified Chat Engine）

### 3.1 定位

统一对话引擎是产品的**核心大脑**，位于 MCP Server 内部（或作为 MCP Server 的一个子服务）。

它的职责：
1. **意图解析**：把用户的自然语言转化为可执行的操作意图
2. **工具编排**：决定调用哪些 MCP tools、以什么顺序调用、参数是什么
3. **状态管理**：维护对话上下文、项目引用、待确认事项（如候选图选择）
4. **结果渲染**：把 tool 执行结果包装成适合当前前端的结构化消息

**实现策略（已确定）：** 不采用规则/关键词匹配，而是直接通过 **LLM function calling** 驱动 MCP 工具。引擎自动将已注册的 MCP tools 转换为 LLM 可用的 function schemas，由 LLM 自主决定调用哪些工具、如何组合参数。新增工具零代码接入，自然语言容错和多意图组合能力远超规则引擎。

### 3.2 会话模型

每个前端连接都对应一个 `ChatSession`：

```python
@dataclass
class ChatSession:
    session_id: str
    project_name: Optional[str]
    frontend_type: str  # "web_drawer" | "cli_tui" | "cli_command" | "mcp_stdio"
    message_history: List[dict]
    pending_confirmations: List[dict]  # 待用户确认的事项
    
    async def send_message(self, text: str) -> dict:
        # 1. 意图解析
        # 2. 工具编排（可能调用 1-N 个 tools）
        # 3. 生成回复
        # 4. 如果有待确认项，标记 pending_confirmation
        ...
```

### 3.3 通用消息协议

无论是 WebSocket 还是 stdio，都走同一套结构化消息格式：

```json
// 客户端 → 服务端
{
  "type": "chat_message",
  "session_id": "sess_abc123",
  "project_name": "my_vn",
  "content": "生成女主角艾米",
  "frontend_type": "cli_tui"
}

// 服务端 → 客户端
{
  "type": "chat_response",
  "session_id": "sess_abc123",
  "role": "assistant",
  "content": "已生成 3 张候选图，请确认...",
  "cards": [
    {
      "type": "image_candidates",
      "title": "emi_neutral 候选图",
      "items": [
        {"id": "1", "url": "/api/.../emi_neutral_1.png"},
        {"id": "2", "url": "/api/.../emi_neutral_2.png"},
        {"id": "3", "url": "/api/.../emi_neutral_3.png"}
      ],
      "requires_confirmation": true
    }
  ],
  "quick_actions": ["重新生成", "换种描述", "跳过"]
}
```

### 3.4 待确认状态机（Confirmation State Machine）

当 AI 需要用户做选择时（如选候选图），引擎进入 `awaiting_confirmation` 状态：

```python
class ConfirmationState:
    prompt: str
    options: List[dict]
    on_confirm: callable
```

**不同前端的渲染方式：**
- **Chat Drawer**：显示 3 张图片卡片，每张下面有"确认"按钮
- **CLI TUI**：显示 `[1] [2] [3]` 的 ASCII 选项，用户输入数字
- **Claude Desktop**：用文字回复"候选图已生成，请回复 1/2/3 确认"

### 3.5 实时状态同步

统一对话引擎在执行工具后，会同时做两件事：
1. **返回结构化消息给当前前端**
2. **广播 `project_state_changed` 到所有连接该项目的客户端**

这意味着：
- 用户在 `vn-creator` TUI 里生成一张图
- Dashboard 浏览器里的 Asset Gallery 会实时刷新
- Dashboard Chat Drawer 里会追加一条系统通知："资源已更新"

```json
{
  "event": "project_state_changed",
  "project_name": "school_romance",
  "change_type": "file_written",
  "affected_files": ["game/script.rpy", "game/images/emi_happy.png"],
  "timestamp": 1713123456
}
```

---

## 4. 目标用户与使用场景

### 4.1 目标用户画像

**主用户：视觉小说创作者（18-30 岁）**
- 有故事创意，但不懂编程
- 可能用过橙光、易次元、B站专栏
- 想用 AI 快速验证故事原型
- 对画风一致性敏感，但不懂美术原理
- 网络环境限制，无法稳定访问 OpenAI/Gemini

**次要用户：独立游戏开发者（个人开发者）**
- 懂一点 Ren'Py，想快速出 Demo
- 用 AI 生成占位资源，后续再替换精修
- 希望通过 VS Code 插件深度集成

### 4.2 核心使用场景

#### 场景 A：从零生成一个可玩 Demo（30 分钟目标）
1. 用户打开 Claude/DeepSeek 客户端，说想做恋爱视觉小说
2. AI 创建项目 → 生成 3 场景脚本 → 生成主角 + 背景
3. 用户切到 Dashboard 确认风格锚定图和角色首图
4. 系统自动保证画风一致 → 构建 Web 包 → 启动预览
5. 用户在 Dashboard 中游玩，发现角色表情不对，点击重生成
6. 5 分钟后刷新页面，看到新版本

#### 场景 B：用 Dashboard 管理项目
1. 用户浏览器打开 Dashboard
2. 在 Visual Story Map 中看见自己的故事结构（只读）
3. 在 Asset Gallery 中查看所有图片，标记某张"重生成"
4. 在 Script Editor 中微调某句台词
5. 点击"构建并预览"，实时看到修改效果

#### 场景 C：视觉质量自动检查
1. 用户生成第 2 个角色后，系统自动跑 Visual QA
2. 发现新角色画风与整体风格偏差较大
3. Dashboard 弹出提示，给出具体修改建议
4. 用户一键接受建议，重新生成

---

## 5. 总体架构

### 5.1 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        前端皮肤层 (Unified Skins)                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│  │  AI 客户端       │  │  Web Dashboard  │  │  vn-creator CLI     │ │
│  │ (Claude/DeepSeek)│  │  (浏览器)        │  │  (Command + TUI)    │ │
│  │  MCP stdio       │  │  REST + WebSocket│  │  WebSocket          │ │
│  └────────┬────────┘  └────────┬────────┘  └──────────┬──────────┘ │
│           │                    │                      │            │
│           │                    │                      │            │
│           └────────────────────┼──────────────────────┘            │
│                                │                                   │
│                                ▼                                   │
│              ┌─────────────────────────────────────┐               │
│              │      Unified Chat Engine            │               │
│              │  （意图解析 + 工具编排 + 会话状态）   │               │
│              │                                     │               │
│              │  输入：自然语言 / 快捷指令 / MCP      │               │
│              │  输出：结构化消息卡片（文本+UI数据）   │               │
│              └────────────────┬────────────────────┘               │
│                               │                                    │
│                               ▼                                    │
│              ┌─────────────────────────────────────┐               │
│              │      MCP Server Core                │               │
│              │  (Project / Script / Asset / Build) │               │
│              └─────────────────────────────────────┘               │
│                               │                                    │
│                               ▼                                    │
│              ┌─────────────────────────────────────┐               │
│              │      Ren'Py SDK + AI Models         │               │
│              └─────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 运行模式

**模式一：`vn-creator` 启动（推荐默认）**
- 用户在终端运行 `vn-creator start`
- CLI 启动 MCP Server（HTTP + WebSocket 模式）
- 自动打开浏览器进入 Dashboard
- Dashboard 中的 Chat Drawer 和 CLI 中的 Chat Mode 共享同一个对话引擎

**模式二：AI 客户端 stdio（高级用户可选）**
- Claude Desktop / Cursor 等 MCP 客户端通过 stdio 启动 Server
- Server 在握手后自动启动内嵌的 FastAPI 网关
- Dashboard 通过同一进程的 HTTP 端口访问
- 适合已经习惯 Claude 对话流的高级用户

**模式三：纯 Dashboard 操作**
- 用户直接浏览器访问 `http://localhost:8080`
- 在 Dashboard 中手动创建项目、上传参考图、生成资源
- 通过 Chat Drawer 唤起统一对话引擎进行 AI 生成

---

## 6. 技术栈

| 层级 | 技术 | 选型理由 |
|------|------|----------|
| **Server Runtime** | Python 3.11+ | Ren'Py 原生 Python，SDK 集成无障碍 |
| **MCP Framework** | `mcp` (official SDK) >=1.6.0 | 标准协议，支持 stdio + SSE |
| **HTTP Gateway** | FastAPI + uvicorn | 轻量、异步、原生支持 WebSocket |
| **Frontend** | React 18 + TypeScript + Vite | 开发快，组件生态成熟 |
| **Graph Viz** | `@xyflow/react` | 故事结构可视化行业标准 |
| **状态管理** | Zustand | 轻量，适合 Dashboard |
| **文件监控** | `watchdog` | 跨平台，实时索引 |
| **图像处理** | Pillow + `rembg` | 本地运行，不依赖网络 |
| **文本模型** | DeepSeek-V3 / 通义千问-Plus | 国内稳定、价格低、中文强 |
| **图像模型** | 即梦 API / 通义万相 | 支持参考图，角色一致性较好 |
| **视觉分析** | Qwen-VL / InternVL2.5 | 国产多模态模型，国内可用 |
| **解析器** | 简化版自定义行解析器 | 只读分析，无需完整 AST |
| **模板** | Jinja2 | 项目模板和 prompt 模板 |
| **CLI/安装** | `uv` + `rich` + `click` | 现代 Python 工具链 |

---

## 7. 核心创新：画风一致性锚定系统

### 7.1 问题定义
AI 生成的背景和人物如果画风不一致，整个项目会直接报废。这是视觉小说 AI 生成最痛的点，必须从架构层解决。

### 7.2 核心思路：双层锚定

```
全局风格锚定图 (Style Anchor)
    ├── 所有背景生成 → 引用 Style Anchor
    ├── 所有角色首图生成 → 引用 Style Anchor
    │       └── 角色锚定图 (Character Anchor)
    │           ├── 情绪图 1 → 引用 Style Anchor + Character Anchor
    │           ├── 情绪图 2 → 引用 Style Anchor + Character Anchor
    │           └── ...
    └── 任何新增资源 → 必须引用 Style Anchor
```

**规则：没有 Anchor 的生成请求，服务器直接拒绝。**

### 7.3 锚定图的生命周期

#### Step 1: 创建项目时选择画风预设
系统内置 5-8 种画风模板：
- 清新水彩
- 日系赛璐珞
- 复古像素
- 赛博朋克
- 油画厚涂
- 韩系扁平
- 黑白漫画

每种预设包含：
```json
{
  "preset_id": "watercolor_anime",
  "name": "清新水彩",
  "style_prompt": "soft watercolor painting, anime visual novel style, gentle pastel colors, clean lineart, dreamy atmosphere, 2D illustration",
  "negative_prompt": "3D render, realistic, photograph, messy lines, dark shadows"
}
```

#### Step 2: 生成风格锚定图
用户选择预设后，系统生成 3 张候选风格图：
```python
await asset_create_style_anchor(
    project_name="my_vn",
    preset_id="watercolor_anime"
)
# 返回 3 张候选图供用户/AI 选择
```

**候选图内容**：一张"无明确主题"但充分体现画风的中性场景（如窗边桌角、空旷街道），避免具体剧情元素干扰风格判断。

#### Step 3: 确认并锁定 Anchor
用户（或 AI 代用户）从 3 张候选图中选择 1 张，系统将其写入项目配置：
```
my_vn/
├── game/
└── .mcp/
    ├── style_anchor.png          # 全局锁定
    ├── config.json               # 项目配置
    └── characters/
        └── emi_anchor.png        # 各角色锚定图
```

**锁定后不可随意更换**，更换将触发"所有资源需重新生成"的确认弹窗。

#### Step 4: 所有后续生成强制引用
每次调用图像生成 API 时，必须同时上传 `style_anchor.png`：
- **背景生成**：`style_reference = style_anchor.png`
- **角色首图生成**：`style_reference = style_anchor.png`
- **角色情绪图生成**：`style_reference = style_anchor.png` + `character_reference = emi_anchor.png`

### 7.4 国产 API 适配策略

#### 即梦 API（推荐）
- 支持 `style_reference` 和 `character_reference` 参数
- 角色一致性在国内 API 中效果较好
- 实现方式：先传 style_anchor，再传 character_anchor

#### 通义万相
- 支持 `style_reference` 和 `subject_reference`
- 实现方式类似，但角色一致性的稳定性略逊于即梦

#### 本地上传兜底
如果用户不满意 AI 生成的锚定图，支持上传本地图片：
```python
asset_set_reference(
    project_name="my_vn",
    ref_type="style",
    image_path="用户本地图片路径"
)
```
这是保证画风一致性的**终极兜底方案**。

### 7.5 技术封装：生成器统一接口

所有图像生成后端（即梦、通义万相、未来可能扩展的 ComfyUI）都实现统一协议：

```python
class ImageGenerator(Protocol):
    async def generate_style_anchor(
        self, prompt: str, negative_prompt: str
    ) -> List[bytes]:
        """返回 3 张候选图"""
        ...

    async def generate_background(
        self, prompt: str, style_ref: bytes
    ) -> bytes:
        ...

    async def generate_character_anchor(
        self, prompt: str, style_ref: bytes
    ) -> List[bytes]:
        """返回 2-3 张候选图"""
        ...

    async def generate_character_emotion(
        self, prompt: str, style_ref: bytes, character_ref: bytes
    ) -> bytes:
        ...
```

### 7.6 后处理管线

所有生成图片必须经过本地后处理：
1. **角色图**：`rembg.remove()` → 透明 PNG
2. **标准化**：角色 resize 到 750px 高度，背景 resize 到 1920×1080
3. **格式转换**：角色 PNG，背景 JPG
4. **命名规范**：
   - `game/images/bg_{scene_name}.jpg`
   - `game/images/{char_name}_{emotion}.png`

---

## 8. MCP 工具设计（精简版，约 20 个）

### 8.1 命名规范
`{category}_{action}`

### 8.2 工具列表

#### 项目管理（4 个）
| 工具 | 描述 |
|------|------|
| `project_create` | 从模板创建项目，要求选择画风预设 |
| `project_list` | 列出工作区项目 |
| `project_delete` | 删除项目 |
| `project_get_config` | 读取项目配置 |

#### 文件操作（5 个）
| 工具 | 描述 |
|------|------|
| `file_list` | 列出文件 |
| `file_read` | 读取文件 |
| `file_write` | 写入文件 |
| `file_edit` | 查找替换编辑 |
| `file_delete` | 删除文件 |

#### 脚本生成（3 个）
| 工具 | 描述 |
|------|------|
| `script_generate` | 根据场景描述生成 Ren'Py 脚本块 |
| `script_validate` | 基础语法检查（缺失 define、错误缩进等） |
| `script_get_graph` | 返回只读的故事结构图数据 |

#### 资源生成（5 个）
| 工具 | 描述 |
|------|------|
| `asset_create_style_anchor` | 生成并锁定全局风格锚定图 |
| `asset_set_reference` | 上传本地图片作为风格/角色锚定图 |
| `asset_generate_background` | 生成背景（强制引用 style anchor） |
| `asset_generate_character_anchor` | 生成角色首图（强制引用 style anchor） |
| `asset_generate_character_emotions` | 批量生成角色情绪图 |

#### 构建与预览（2 个）
| 工具 | 描述 |
|------|------|
| `build_project` | 构建 Web 包 |
| `preview_start` / `preview_stop` | 启动/停止预览服务器 |

#### 视觉 QA（2 个）
| 工具 | 描述 |
|------|------|
| `visual_run_check` | 运行视觉质量检查 |
| `visual_compare_images` | 对比两张图的风格一致性 |

### 8.3 关键工具的 I/O 示例

#### `asset_create_style_anchor`

```json
{
  "name": "asset_create_style_anchor",
  "description": "为项目生成 3 张候选风格锚定图。用户确认后，后续所有图片生成都会参考这张图的画风。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "project_name": {"type": "string"},
      "preset_id": {
        "type": "string",
        "enum": ["watercolor_anime", "cel_shaded", "retro_pixel", "cyberpunk", "oil_painting", "korean_flat", "monochrome"]
      },
      "custom_prompt": {"type": "string", "description": "可选的自定义风格描述"}
    },
    "required": ["project_name", "preset_id"]
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "candidates": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "id": {"type": "string"},
            "file_path": {"type": "string"},
            "description": {"type": "string"}
          }
        }
      }
    }
  }
}
```

#### `asset_generate_character_emotions`

```json
{
  "name": "asset_generate_character_emotions",
  "description": "基于已确认的角色锚定图，批量生成该角色的多种情绪立绘。自动保持画风和面部一致性。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "project_name": {"type": "string"},
      "character_name": {"type": "string"},
      "emotions": {
        "type": "array",
        "items": {"type": "string"},
        "default": ["happy", "sad", "surprised", "angry"]
      },
      "extra_prompt": {"type": "string", "description": "额外的表情细节描述"}
    },
    "required": ["project_name", "character_name"]
  }
}
```

---

## 9. Visual QA Agent（视觉质量自动检查）

### 9.1 定位
不是替代用户肉眼检查，而是**在问题发生早期自动拦截并给出修改建议**。相当于一个 24 小时在线的"美术助理"。

### 9.2 架构

```
┌────────────────────────────────────────────────────────────┐
│                    Visual QA Agent                         │
├────────────────────────────────────────────────────────────┤
│  输入层                                                     │
│  ├── 静态合成图（Pillow 叠加 bg + character，无需启动游戏）  │
│  └── Bridge 截图（可选，真实运行状态，深度检查用）           │
├────────────────────────────────────────────────────────────┤
│  分析层                                                     │
│  ├── 规则引擎（本地运行，零成本）                           │
│  │   ├── 比例检测：角色是否过大/过小                        │
│  │   ├── 透明边检测：rembg 是否有白边/黑边/绿边             │
│  │   ├── 色彩和谐度：角色与背景色调差异（Lab 空间）          │
│  │   └── 拉伸检测：画面是否被非等比拉伸                      │
│  └── VLM 视觉模型（按需调用）                               │
│      ├── 画风一致性评判                                    │
│      ├── 违和感识别（现代角色出现在古风背景中）              │
│      └── 质量评分                                          │
├────────────────────────────────────────────────────────────┤
│  输出层                                                     │
│  └── 结构化问题 + 自然语言建议（由轻量 LLM 生成）            │
└────────────────────────────────────────────────────────────┘
```

### 9.3 检测项与触发策略

| 检测项 | 触发时机 | 执行方式 | 成本 |
|--------|---------|---------|------|
| **比例/尺寸** | 每次生成后自动 | 本地 Pillow | 免费 |
| **透明边质量** | 每次 rembg 后自动 | 本地边缘像素分析 | 免费 |
| **色彩和谐度** | 每次生成后自动 | 本地直方图/CLIP | 免费 |
| **画风一致性** | 生成新角色/背景后 | Qwen-VL / InternVL | ~0.01-0.03 元/张 |
| **深度美术建议** | 用户手动触发 | DeepSeek-V3 | ~0.001 元/次 |

### 9.4 用户界面表现

**Dashboard 中的表现形式：**

1. **资源卡片角标**：
   - 🟢 绿色：通过所有自动检查
   - 🟡 黄色：规则引擎发现轻微问题（如比例略大）
   - 🔴 红色：VLM 检测到严重画风不一致

2. **项目级视觉健康度**：
   - Dashboard 顶部显示进度条："视觉一致性 87%"
   - 点击展开详细报告

3. **一键修复建议**：
   ```
   ⚠️ 检测到问题
   角色 '艾米_开心' 与整体画风偏差较大（偏写实，项目为水彩风格）
   
   建议：
   1. 重新生成时加入 "watercolor texture, soft brush strokes"
   2. 或选择更匹配的风格锚定图
   
   [重新生成] [忽略] [查看对比]
   ```

### 9.5 与生成流程的集成

```text
用户请求生成新角色
    ↓
调用图像 API 生成
    ↓
本地后处理（rembg + resize）
    ↓
规则引擎快速扫描
    ↓
如发现异常 ──→ 调用 VLM 深度分析
    ↓
生成 QA 报告
    ↓
如果严重问题 ──→ 弹窗提示用户
如果轻微问题 ──→ 资源卡片显示黄色角标
如果通过 ──→ 资源卡片显示绿色角标
```

---

## 10. Web Dashboard 设计

### 10.1 页面结构（双轨制精简版）

| 页面 | 核心功能 | 用户价值 |
|------|---------|---------|
| **Project Explorer** | 文件树、新建/重命名/删除 | 让创作者有"项目"的实感 |
| **Script Editor** | Monaco 编辑器，Ren'Py 语法高亮 | 微调台词，满足控制欲 |
| **Visual Story Map** | **只读**节点图，展示标签和分支 | 让创作者"看见"自己的故事结构 |
| **Asset Gallery** | 图片网格、上传、重生成、QA 状态角标 | 核心工作区，管理所有视觉资源 |
| **Live Preview** | iframe 嵌入试玩 | 即时反馈，验证创意 |
| **Build & Export** | 一键构建、下载 zip | 最终产出，可分享 |
| **Chat Drawer** | 右下角悬浮 AI 助手入口 | 在 Dashboard 内直接唤起对话生成 |

### 10.2 砍掉的原设计页面

- ❌ Translation Manager（翻译）
- ❌ Variable Inspector（变量检查）
- ❌ Bridge Control Panel（实时调试）
- ❌ 复杂的 Story Map 可视化编辑（只读即可）

### 10.3 Chat Drawer 设计

**定位：** Chat Drawer 是**统一对话引擎在浏览器中的皮肤**。

**位置：** 固定在 Dashboard 右下角，点击后从右侧滑出抽屉（360px 宽）。

**功能：**
- 通过 WebSocket 连接到统一对话引擎
- 显示当前项目的对话历史
- 输入自然语言指令，引擎解析后调用 MCP tools
- 将引擎返回的结构化消息渲染为卡片（图片候选、进度条、确认按钮等）
- 操作结果通过 WebSocket 广播同步到 Dashboard 主区域

**示例交互：**
```
用户（Chat Drawer）："给第三章加一个选择支"
    ↓
统一对话引擎解析意图
    ↓
调用 script_generate
    ↓
引擎返回结构化消息：{type: "text", content: "已生成第三章的选择支"}
    ↓
Drawer 显示文字消息
    ↓
WS 广播 project_state_changed
    ↓
Dashboard 主区域：
  - Story Map 自动新增 choice 节点
  - Script Editor 中 chapter3.rpy 标记为"有更新"
```

### 10.4 核心交互流程

#### 流程：创作者首次打开 Dashboard

```
进入 Dashboard
    ↓
点击 "新建项目"
    ↓
输入项目名称
    ↓
选择画风预设（清新水彩 / 日系赛璐珞 / ...）
    ↓
系统生成 3 张风格锚定图候选
    ↓
用户点击选择第 2 张
    ↓
系统锁定 Style Anchor，提示"所有资源将基于此画风生成"
    ↓
进入 Asset Gallery（此时为空）
    ↓
右下角 Chat Drawer 提示："需要我帮你生成主角和第一章吗？"
```

#### 流程：在 Dashboard 中生成一个角色

```
Asset Gallery 中点击 "生成角色"
    ↓
输入角色名："艾米"
    ↓
输入描述："棕色短发咖啡师，绿色围裙，温暖笑容"
    ↓
点击生成
    ↓
系统调用 asset_generate_character_anchor
    ↓
显示 3 张候选图
    ↓
用户选择第 1 张 → 锁定 Character Anchor
    ↓
自动批量生成 happy/sad/surprised/angry
    ↓
每张图经过 rembg + resize
    ↓
规则引擎 QA 扫描
    ↓
显示在 Gallery 中，带 QA 状态角标
    ↓
WS 广播状态变更 → Chat 侧（如有活跃会话）收到"资源已更新"摘要
```

#### 流程：发现画风问题并修复

```
用户发现 'emi_angry' 有绿色透明边
    ↓
点击该图片
    ↓
弹出详情面板：
    - 大图预览
    - QA 报告："透明边检测未通过，边缘有绿色残留"
    - 操作建议："重新运行背景移除" 或 "重新生成"
    ↓
用户点击 "重新生成"
    ↓
系统仅重新生成 angry 情绪图
    ↓
自动替换旧文件
    ↓
WS 广播 → Chat Drawer 显示 "emi_angry 已更新"
```

---

## 11. AI 集成策略

### 11.1 模型选择

**文本生成：**
- **默认：DeepSeek-V3**（通过硅基流动/DeepSeek 官方 API）
- **备选：通义千问-Plus**（阿里云百炼平台）
- 选择标准：中文能力强、价格便宜、对创意写作友好

**图像生成：**
- **默认：即梦 API**（字节跳动，角色一致性较好）
- **备选：通义万相**（阿里云，风格参考支持稳定）
- 接入方式：统一封装在 `ImageGenerator` 协议后，可随时切换

**视觉分析：**
- **默认：Qwen-VL-Max**（阿里云百炼）
- **备选：InternVL2.5**（硅基流动）

### 11.2 Prompt 工程架构

**三层提示结构：**

1. **系统资源层**：MCP 服务器暴露 `renpy://syntax-guide`，包含 Ren'Py 基础语法和最佳实践
2. **工具文档层**：每个工具 docstring 包含用途说明 + 迷你语法指南 + few-shot 示例
3. **预处理层**：服务器将用户模糊的自然语言输入，先转化为结构化的"场景需求"（角色、地点、情绪、分支），再交给 LLM 生成代码

**示例预处理：**

用户输入："我想写一个咖啡店初次见面的场景，女主角叫艾米，是个开朗的店员。"

服务器预处理为：
```json
{
  "scene_type": "intro",
  "location": "cozy coffee shop, evening",
  "characters": [
    {
      "name": "艾米",
      "tag": "emi",
      "personality": "cheerful, warm",
      "emotion": "happy",
      "position": "center"
    }
  ],
  "dialogue_count": 3,
  "has_choice": false,
  "atmosphere": "warm and welcoming"
}
```

然后 LLM 基于这个结构化输入生成 Ren'Py 代码，降低"自由发挥导致走偏"的概率。

### 11.3 脚本生成的约束设计

为了降低生成错误率，服务器会对 LLM 输出做后处理：
- **强制插入 `define` 语句**：如果使用了新角色名但脚本中没有 `define`，自动在文件头部补全
- **禁止 `label start` 冲突**：子脚本中不允许出现 `label start`
- **强制 `return` 结尾**：生成的 label 块如果缺少 `return`，自动补全
- **图片引用检查**：脚本中引用的背景/角色图，如果没有对应文件，在 Dashboard 中标记为"待生成"

### 11.4 AI 回复模板标准化

Chat 侧 AI 每次执行完生成类操作后，回复应遵循固定模板：

```markdown
✅ 已完成以下操作：
- 生成场景：第一章「图书馆相遇」
- 生成角色：小林（5 种情绪）
- 生成背景：bg_library_evening

📊 项目状态：
- 当前共 3 个场景，2 个角色，4 张背景
- 视觉健康度：92%（1 张图待优化）

🔗 [在 Dashboard 中查看详情](http://localhost:8080/dashboard/lib_meet)
🎮 [直接试玩](http://localhost:8080/preview/lib_meet)
```

---

## 12. 构建与分发系统

### 12.1 Ren'Py SDK 获取策略

**问题**：Ren'Py 官网和 itch.io 在国内访问慢或不稳定。  
**解决方案**：

1. **默认国内镜像下载**
   - 在阿里云 OSS / 腾讯云 COS / Gitee Release 上托管 Ren'Py SDK 8.4.1 + web module
   - 提供 `RENPY_SDK_MIRROR` 环境变量，允许用户自定义镜像地址

2. **离线整合包（推荐给中国用户）**
   - 提供预打包的完整环境：Python 运行时 + 所有 pip 依赖 + Ren'Py SDK + 内置模型配置
   - 用户下载解压后，双击 `start.bat` / `start.sh` 即可运行
   - 适合完全不想折腾网络环境的用户

3. **pip 安装（进阶用户）**
   - `pip install renpy-mcp-creator -i https://pypi.tuna.tsinghua.edu.cn/simple`
   - 首次运行时自动从镜像下载 SDK

### 12.2 构建流程

```python
async def build_project(project_name: str) -> BuildResult:
    # 1. 调用 Ren'Py launcher lint（无头模式）
    # 2. 运行 renpy.sh launcher distribute --package web
    # 3. 后处理：解压 zip、拷贝 runtime、创建 game.zip
    # 4. 返回构建产物路径和预览 URL
```

**无头执行参数：**
```bash
RENPY_GL_ENVIRON="null" SDL_AUDIODRIVER="dummy" SDL_VIDEODRIVER="dummy" ./renpy.sh <project> lint
```

### 12.3 预览服务器

FastAPI 挂载静态文件：
```python
app.mount(f"/preview/{project_name}", StaticFiles(directory=build_path))
```

- 开启 CORS，允许 Dashboard iframe 嵌入
- 每个项目独立端口或统一走 `/preview/{project_name}` 路径

---

## 13. `vn-creator` CLI 设计

### 13.1 定位

`vn-creator` 是产品的**统一入口命令**。它不仅是启动器，更是**统一对话引擎在终端中的皮肤**。安装后，用户只需要记住一个命令。

### 13.2 两种运行模式

#### 模式 A：快捷命令（Command Mode）

适合习惯命令行的用户，快速执行常见操作：

```bash
# 启动服务并自动打开 Dashboard（最常用）
vn-creator start
vn-creator start --project ./my_vn

# 创建新项目（交互式）
vn-creator new

# 列出所有项目
vn-creator list

# 删除项目
vn-creator remove my_vn

# 构建指定项目
vn-creator build my_vn

# 用系统默认编辑器打开文件
vn-creator edit my_vn/game/script.rpy --line 42

# 检查环境
vn-creator doctor

# 配置管理（交互式设置 API Key）
vn-creator config
```

#### 模式 B：对话模式（Chat Mode）—— 核心形态

```bash
# 进入交互式 TUI 对话
vn-creator chat

# 直接进入某个项目的对话上下文
vn-creator chat --project my_vn
```

终端变成一个**纯文本版的 Chat Drawer**，连接统一对话引擎：

```
┌────────────────────────────────────────────────────────────┐
│  vn-creator  v0.1.0  |  项目: 我的恋爱小说                    │
│  ─────────────────────────────────────────────────────────  │
│                                                              │
│  🤖  需要我帮你做什么？                                       │
│      你可以说："生成第三章"、"给艾米加个伤心表情"、"构建试玩"  │
│                                                              │
│  👤  生成女主角，叫艾米，棕色短发咖啡师                        │
│                                                              │
│  🤖  正在生成角色 '艾米' 的候选图...                          │
│      [████████████████████░░░░]  80%                        │
│                                                              │
│  🤖  已生成 3 张候选图。请回复数字 1/2/3 确认，或说"重新生成"： │
│      [1] emi_neutral_1.png                                   │
│      [2] emi_neutral_2.png                                   │
│      [3] emi_neutral_3.png                                   │
│                                                              │
│  👤  2                                                       │
│                                                              │
│  🤖  已确认 [2]。正在批量生成情绪图...                        │
│      ✅ happy     ✅ sad      ✅ surprised    ✅ angry      │
│      视觉健康度: 94%                                         │
│      建议: 在 Dashboard 中查看大图 http://localhost:8080/... │
│                                                              │
│  > _                                                        │
└────────────────────────────────────────────────────────────┘
```

### 13.3 `start` 命令内部逻辑

```python
def start_command(project_path: Optional[str] = None, port: int = 8080):
    # Step 1: 环境检查
    ensure_sdk_installed()
    ensure_models_configured()
    
    # Step 2: 启动 MCP Server（HTTP 模式）
    server_process = subprocess.Popen(
        [sys.executable, "-m", "renpy_mcp.server", 
         "--transport", "http", 
         "--port", str(port),
         "--project", project_path or ""]
    )
    
    # Step 3: 等待服务就绪
    wait_for_server(port)
    
    # Step 4: 打开浏览器
    dashboard_url = f"http://localhost:{port}/dashboard"
    if project_path:
        dashboard_url += f"?project={os.path.basename(project_path)}"
    webbrowser.open(dashboard_url)
    
    # Step 5: 阻塞当前终端，显示日志
    print(f"🚀 vn-creator running at http://localhost:{port}")
    print(f"📊 Dashboard: {dashboard_url}")
    print("Press Ctrl+C to stop")
    server_process.wait()
```

### 13.4 TUI 技术实现

推荐 **`textual`**（Python TUI 框架）实现 `vn-creator chat`：

```python
from textual.app import App
from textual.widgets import Input, Markdown

class VNCreatorChatApp(App):
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_text = event.value
        # 发送到统一对话引擎
        response = await chat_engine.send_message(
            session_id=self.session_id,
            content=user_text,
            frontend_type="cli_tui"
        )
        # 根据 response.cards 渲染不同组件
        self.render_response(response)
```

**TUI 中的图片显示策略：**
- 检测到终端支持 Kitty/iTerm 图像协议 → 直接内嵌显示候选图
- 不支持 → 显示文本描述 + `[O] 在浏览器中打开` 快捷键

### 13.5 与 Dashboard 的实时协同

`vn-creator chat` 和 Dashboard Chat Drawer 连接的是**同一个统一对话引擎**。

```text
用户在终端输入："生成第三章"
    ↓
vn-creator TUI 发送 WS 消息到统一对话引擎
    ↓
引擎调用 script_generate + asset_generate_background
    ↓
引擎返回结构化消息给 TUI
    ↓
同时广播 project_state_changed 到所有客户端
    ↓
Dashboard 浏览器端：
    - Story Map 新增 chapter3 节点
    - Chat Drawer 追加系统消息："第三章已生成"
```

### 13.6 对 IDE 的支持：极简方案

我们不写任何 IDE Extension。如果用户需要用代码编辑器：

```bash
# vn-creator 提供最简单的编辑命令
vn-creator edit my_vn/game/script.rpy --line 42
```

内部逻辑：
1. 检测用户系统是否安装了 `code` / `cursor` / `zed`（按优先级）
2. 如检测到，调用 `[editor] --goto file:line`
3. 如未检测到，回退到系统默认打开方式（`open` / `xdg-open` / `start`）

### 13.7 离线整合包形态

```
vn-creator-portable/
├── vn-creator.exe      # 自包含 Python + 依赖
├── renpy-sdk/          # 内置 SDK
├── dashboard/          # 内置前端静态文件
└── start.bat           # 双击即运行 vn-creator start
```

**这是给中国用户最推荐的安装方式：** 下载解压，双击 `start.bat`，全自动。

---

## 14. 开发计划（MVP：9 周）

**当前进度速览（截至 2026-04-15）：**
- ✅ MCP Server 核心完成（70 个工具注册，82/82 测试通过）
- ✅ 项目/资源/构建/预览后端工具迁移完成（`create_project`、`generate_background`、`generate_character`、`build_project`、`start_web_preview` 等）
- ✅ `google-genai`、`.env` 配置就绪（Gemini API key 已配置，但免费配额耗尽，需准备备用图像后端）
- ⬜ Dashboard React 前端尚未搭建
- ⬜ 统一对话引擎（LLM 驱动 MCP）尚未实现
- ⬜ SDK 自动下载/国内镜像尚未实现

| 阶段 | 周期 | 交付内容 |
|------|------|---------|
| **Week 1-2: 骨架搭建** | 2 周 | MCP Server 核心 ✅、统一对话引擎（LLM function calling 驱动 70 个 MCP tools）、Dashboard React 骨架（Vite + React + TS）、`vn-creator` CLI 基础命令、SDK 国内镜像自动下载 |
| **Week 3-4: 脚本生成闭环** | 2 周 | `script_generate`（DeepSeek/通义千问接入，真正 AI 生成脚本）+ `script_validate`、Story Map 只读展示、Chat Drawer ↔ Dashboard 状态同步、候选图确认交互 |
| **Week 5-6: 资源管线** | 2 周 | 即梦/通义万相 API 对接（Gemini 配额兜底）、Style Anchor + Character Anchor 风格锚定系统、rembg 集成、Asset Gallery、TUI 中的图片预览 |
| **Week 7: Visual QA** | 1 周 | 规则引擎、Qwen-VL 集成、Dashboard QA 状态展示、TUI 中的 QA 报告文本版 |
| **Week 8: 构建预览优化** | 1 周 | Live Preview 页面、增量构建优化、端到端 30 分钟 Demo 流程跑通 |
| **Week 9: 整合发布** | 1 周 | 离线整合包打包（`start.bat` / `start.sh`）、示例项目、文档、内测 |

### 14.1 里程碑

- **M1 (Week 2)**：`create_project` + `generate_character`/`generate_background` + `build_project` + Dashboard 壳子 + LLM 对话引擎可运行
- **M2 (Week 4)**：统一对话引擎能处理中文对话并生成 3 场景脚本，Story Map 与 Chat Drawer 联动
- **M3 (Week 6)**：生成角色 + 背景并自动保持画风一致，Asset Gallery 和 TUI 都能管理候选图
- **M4 (Week 7)**：Visual QA 能自动检测并提示画风偏差
- **M5 (Week 8)**：端到端 30 分钟 Demo 流程跑通（Chat 生成 → Dashboard 确认 → 构建 → 试玩）
- **M6 (Week 9)**：发布内测版，收集首批创作者反馈

---

## 15. 风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|---------|
| **即梦/通义万相 API 不稳定或调价** | 高 | 抽象 `ImageGenerator` 接口，支持快速切换；准备本地 ComfyUI 作为高级备选 |
| **国产图像 API 角色一致性达不到预期** | 高 | 强调"风格锚定 + 角色锚定 + 人工确认"流程；提供本地上传参考图兜底；QA 系统及时拦截 |
| **Ren'Py SDK 镜像失效** | 中 | 多镜像备份（阿里云 + 腾讯云 + Gitee）；离线整合包不依赖实时下载 |
| **DeepSeek API 波动** | 中 | 同时接入通义千问作为秒级 fallback |
| **AI 生成内容合规风险** | 高 | 在 prompt 中植入安全过滤；图像生成走国产 API（自带内容审核）；用户协议明确使用规范 |
| **用户对"AI 生成"新鲜感快速消退** | 中 | 强调"画风一致性"和"零配置"的差异化价值，不只是"AI 能生成" |

---

## 16. 商业模式初探（非开发重点，但需明确方向）

| 层级 | 内容 |
|------|------|
| **免费版** | 基础脚本生成、基础画风预设、每月有限额的图像生成、带水印的 Web 预览 |
| **付费版** | 无限图像生成、高级画风预设、Visual QA 高级报告、优先构建队列、无水印导出 |
| **企业服务** | 私有化部署（本地 ComfyUI + 内部模型）、定制画风 LoRA、团队协作（远期） |

**关键：** 免费版的核心体验（30 分钟生成一个 Demo）必须完整且流畅，付费点在"更高质量、更多数量、更快速度"。

---

## 17. 附录：关键术语

- **Style Anchor**：全局风格锚定图，所有资源的画风基准
- **Character Anchor**：角色锚定图，用于保证同一角色不同情绪的一致性
- **Visual QA Agent**：视觉质量自动检查代理
- **ImageGenerator Protocol**：统一的图像生成后端接口
- **Unified Chat Engine**：统一对话引擎，产品的核心大脑，负责意图解析、工具编排、会话状态管理
- **vn-creator**：自研的统一 CLI 入口，包含快捷命令和对话式 TUI
- **Chat Drawer**：Dashboard 内置的 AI 对话抽屉，是统一对话引擎在浏览器中的皮肤
- **离线整合包**：包含所有依赖的预打包环境，解压即用

---

*设计方案完*
