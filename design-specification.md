# Ren'Py MCP Unified Server — 软件设计规格书

**版本:** 1.0  
**日期:** 2026-04-14  
**状态:** 设计提案

---

## 1. 执行摘要与产品愿景

### 愿景
打造一个统一、开源的 MCP（Model Context Protocol）服务器，将 Ren'Py 视觉小说开发从纯文本、反复试错的流程，转变为 AI 辅助、可视化、可专业调试的体验。

### 融合的两个项目
- **Project A (banjtheman/renpy_mcp_server):** 零配置 SDK 自动安装、AI 图像生成、情绪批量生成、Web 构建、适合新手的 Studio 面板。
- **Project B (youichi-uda/renpy-mcp-pro):** 轻量级独立 AST 解析器、60+ 专业工具集、基于文件的 Live Bridge 运行时调试、故事流分析、重构、翻译与自动化测试。

### 目标用户
1. **AI 辅助创作者** — 希望通过对话/提示词生成游戏的作家和爱好者。
2. **专业 VN 开发者** — 需要代码检查、重构、翻译管理、实时调试和 CI/CD 集成的团队。

### 成功标准
- 单个 Python 进程同时服务 `stdio`（Claude Desktop、Cursor）和 HTTP/SSE（独立面板）。
- 无需预装 Ren'Py SDK（首次运行时自动下载）。
- Live Bridge 在不向 Ren'Py 内部注入网络套接字的情况下实现运行时状态检查。
- 自定义解析器足够准确，可在不导入 Ren'Py 本身的情况下完成重构和图可视化。

---

## 2. 架构概览

### 2.1 高层架构图

```
┌─────────────────┐     stdio/SSE      ┌──────────────────────────────────────────────┐
│  AI Assistant   │◄──────────────────►│         Ren'Py MCP Unified Server            │
│(Claude/Cursor)  │                    │  (Python 3.11+ — single uvicorn process)     │
└─────────────────┘                    │                                              │
                                       │  ┌─────────────┐  ┌───────────────────────┐  │
                                       │  │  MCP Core   │  │   FastAPI Gateway     │  │
                                       │  │ (mcp SDK)   │  │  (HTTP + WebSocket)   │  │
                                       │  └──────┬──────┘  └───────────┬───────────┘  │
                                       │         │                     │              │
                                       │  ┌──────┴─────────────────────┴──────┐       │
                                       │  │         Unified Tool Router         │       │
                                       │  │  (registers 40-50 tools across      │       │
                                       │  │   categories, dispatches to svcs)   │       │
                                       │  └──────┬─────────────────────┬────────┘       │
                                       │         │                     │                │
                                       │  ┌──────┴──────┐    ┌─────────┴─────────┐      │
                                       │  │  Service    │    │  Service          │      │
                                       │  │   Layer     │    │    Layer          │      │
                                       │  │  (Project,  │    │  (Bridge, Build,  │      │
                                       │  │   Asset,    │    │   Preview, Test)  │      │
                                       │  │   Analysis) │    │                   │      │
                                       │  └──────┬──────┘    └─────────┬─────────┘      │
                                       │         │                     │                │
                                       └─────────┼─────────────────────┼────────────────┘
                                                 │                     │
                    ┌────────────────────────────┼─────────────────────┼────────────────┐
                    │                            │                     │                │
                    ▼                            ▼                     ▼                ▼
           ┌──────────────┐            ┌─────────────────┐    ┌──────────────┐   ┌─────────────┐
           │  File System │            │  Ren'Py SDK     │    │  Live Bridge │   │  AI Models  │
           │  (Projects)  │            │  (Launcher)     │    │  (file IPC)  │   │  (Gemini)   │
           └──────────────┘            └─────────────────┘    └──────────────┘   └─────────────┘
```

### 2.2 执行模式
1. **嵌入式模式** — MCP 客户端通过 `stdio` 启动服务器。FastAPI 网关启动在一个临时端口（默认 `0` 由 OS 分配），并通过 `notify` 工具向用户暴露本地面板 URL。
2. **独立模式** — 用户直接运行 `renpy-mcp-server --transport http --port 8080`。面板可直接访问；MCP-over-SSE 在 `/sse` 提供。

### 2.3 数据流
1. **项目变更** → `watchdog` 触发 `IndexService` → 增量 AST 更新 → WebSocket 广播到面板。
2. **AI 工具调用** → `Tool Router` → `Service Layer` → 文件 I/O 或 SDK 子进程 → 结果 + 更新后的索引返回给 LLM。
3. **实时调试** → `BridgeService` 写入 `cmd.json` → 注入的 `_mcp_bridge.rpy` 轮询、执行、写入 `status.json` → `BridgeService` 读取并返回给调用方。

---

## 3. 技术栈

| 层级 | 技术 | 选型理由 |
|------|------|----------|
| **Server Runtime** | Python 3.11+ | Ren'Py 本身就是 Python；SDK 集成容易，生态丰富。 |
| **MCP Framework** | `mcp` (official SDK) `>=1.6.0` | 标准、符合规范，支持 `stdio` 和 `sse` 传输。 |
| **HTTP Gateway** | FastAPI + `uvicorn` | 类型安全、原生 WebSocket 支持、默认异步。 |
| **Frontend** | React 18 + TypeScript + Vite | 开发周期快，图编辑器生态优秀。 |
| **Graph Viz** | `@xyflow/react` (React Flow) | 节点-边图表的行业标准；可主题化。 |
| **State Mgmt** | Zustand | 轻量、无样板代码，适合面板 UI 状态。 |
| **File Watching** | `watchdog` | 跨平台、可靠、支持增量索引。 |
| **Image Processing** | Pillow + `rembg` | Project A 验证过的背景移除方案。 |
| **AI Generation** | `google-genai` (Gemini 2.5 Flash) | 多情绪角色批量生成的最佳性价比。 |
| **Parser** | Custom recursive-descent + regex | 避免导入 Ren'Py；快到足以实时索引。 |
| **Templating** | Jinja2 | 项目模板和 bridge 脚本生成。 |
| **CLI / Setup** | `uv` + `rich` + `click` | 现代 Python 打包、美观的 CLI 输出。 |

---

## 4. 模块拆分

### 4.1 仓库目录结构
```
renpy-mcp-unified/
├── pyproject.toml
├── README.md
├── src/
│   └── renpy_mcp/
│       ├── __init__.py
│       ├── main.py                 # 入口：解析 --transport，启动服务器
│       ├── config.py               # Pydantic Settings（环境变量、路径、端口）
│       ├── server.py               # MCP 服务器生命周期
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── router.py           # 中心化工具注册与 ACL
│       │   ├── schemas.py          # 每个工具 I/O 的 Pydantic 模型
│       │   └── categories/
│       │       ├── project.py
│       │       ├── files.py
│       │       ├── assets.py
│       │       ├── script.py
│       │       ├── story.py
│       │       ├── bridge.py
│       │       ├── build.py
│       │       ├── refactor.py
│       │       ├── translate.py
│       │       ├── testing.py
│       │       └── docs.py
│       ├── services/
│       │   ├── project_service.py
│       │   ├── file_service.py
│       │   ├── asset_pipeline.py
│       │   ├── analysis_service.py
│       │   ├── bridge_service.py
│       │   ├── build_service.py
│       │   └── preview_service.py
│       ├── analysis_engine/
│       │   ├── parser.py
│       │   ├── ast_nodes.py
│       │   ├── indexer.py
│       │   ├── graph_builder.py
│       │   └── watchers.py
│       ├── bridge/
│       │   ├── protocol.py         # Command/Status 数据类
│       │   ├── injector.py         # 注入/移除 bridge.rpy
│       │   ├── serializer.py       # 安全 JSON 转换
│       │   ├── poller.py           # 带超时读取 status.json
│       │   └── templates/
│       │       └── _mcp_bridge.rpy.j2
│       ├── web/
│       │   ├── api.py              # FastAPI REST 路由
│       │   ├── websocket.py        # WS 端点（实时数据）
│       │   ├── state.py            # 共享服务器状态对象
│       │   └── static/             # 构建后的 React 面板
│       ├── templates/              # Ren'Py 项目模板
│       │   ├── minimal/
│       │   └── advanced/
│       └── docs_index/             # 离线 Ren'Py 文档片段
└── dashboard/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── components/
        ├── pages/
        ├── hooks/
        ├── stores/
        └── lib/
```

### 4.2 组件职责

| 模块 | 职责 |
|------|------|
| `main.py` | 解析 CLI 参数，启动 MCP 循环（stdio 或 SSE），并在同一进程中条件挂载 FastAPI 网关。 |
| `server.py` | 实例化 `mcp.Server`，附加工具/资源，处理初始化握手。 |
| `tools/router.py` | 基于装饰器的注册表。强制执行 silent vs app-only 注解。将调用路由到正确服务。 |
| `services/*` | 纯业务逻辑。不感知传输层。每个服务都是带 async 方法的类。 |
| `analysis_engine/` | 完全与 Ren'Py 运行时隔离。将 `.rpy` 文件解析为项目索引。 |
| `bridge/` | 管理注入的 bridge 脚本、文件 I/O 协议、游戏状态的安全序列化。 |
| `web/` | 提供 React 构建包，并为面板暴露 REST/WebSocket API。 |

---

## 5. MCP 工具设计

### 5.1 命名约定
`{category}_{action}` — 例如 `asset_generate_background`、`story_find_dead_ends`。

### 5.2 分类工具列表（46 个工具）

#### A. 项目管理 (`project_*`)
| 工具 | 描述 |
|------|------|
| `project_create` | 从模板初始化新的 Ren'Py 项目。 |
| `project_list` | 列出工作区中的所有项目。 |
| `project_delete` | 永久删除项目目录。 |
| `project_get_config` | 读取 `options.rpy` 和 `gui.rpy` 设置。 |
| `project_set_config` | 安全地修改配置变量。 |
| `project_analyze` | 运行完整 lint + 未使用资源扫描 + 索引报告。 |

#### B. 文件操作 (`file_*`)
| 工具 | 描述 |
|------|------|
| `file_list` | 列出文件，支持 glob 过滤。 |
| `file_read` | 读取文本或 base64 编码的二进制文件。 |
| `file_write` | 创建或覆盖文件。 |
| `file_edit` | 应用统一 diff 或查找替换补丁。 |
| `file_delete` | 删除文件。 |

#### C. 资源生成 (`asset_*`)
| 工具 | 描述 |
|------|------|
| `asset_generate_background` | 通过 Gemini 生成 16:9 背景图。 |
| `asset_generate_character` | 生成 2:3 角色立绘（批量 5 种情绪）。 |
| `asset_remove_background` | 对 sprite 运行 `rembg`，输出透明 PNG。 |
| `asset_normalize` | 将图片 resize 并格式化为项目标准。 |
| `asset_list` | 列出图片/音频，附带尺寸/时长。 |
| `asset_find_unused` | 将项目索引与文件系统交叉比对，找出未使用资源。 |

#### D. 脚本编辑 (`script_*`)
| 工具 | 描述 |
|------|------|
| `script_generate` | AI 辅助脚本生成并持久化到文件。 |
| `script_validate` | 静态分析：缺失定义、禁用标签、缺少 `at` 子句等。 |
| `script_lint` | 对项目运行 Ren'Py launcher lint。 |
| `script_get_graph` | 返回一个或多个脚本文件的节点/边图表示。 |
| `script_find_definition` | 定位角色/图片/标签的定义位置（文件:行号）。 |

#### E. 故事分析 (`story_*`)
| 工具 | 描述 |
|------|------|
| `story_get_flow_graph` | 构建完整项目故事图（标签、跳转、菜单）。 |
| `story_find_dead_ends` | 检测没有 `return` 或出跳且无法到达 `start` 的标签。 |
| `story_find_orphans` | 列出从 `start` 不可达的标签。 |
| `story_get_character_map` | 返回角色到台词、情绪、场景的映射。 |
| `story_track_variables` | 列出 persistent/defined 变量及其变更点。 |
| `story_check_consistency` | 标记连续性错误（如角色在定义前就被 show）。 |

#### F. 实时桥接 (`bridge_*`)
| 工具 | 描述 |
|------|------|
| `bridge_inject` | 将 bridge 脚本注入运行中的项目。 |
| `bridge_get_state` | 返回当前标签、变量和调用栈。 |
| `bridge_eval` | 在运行中的游戏内执行 Python 表达式。 |
| `bridge_jump_to_label` | 将游戏跳转到指定标签（可附带变量状态）。 |
| `bridge_set_variable` | 在运行时设置游戏变量。 |
| `bridge_screenshot` | 通过 bridge 捕获当前游戏画面。 |
| `bridge_notify` | 在游戏内显示一条 toast/消息。 |

#### G. 构建与预览 (`build_*`)
| 工具 | 描述 |
|------|------|
| `build_project` | 编译项目（默认 web 包）。 |
| `build_get_status` | 返回上次构建日志和成功/失败状态。 |
| `preview_start` | 为项目启动本地 HTTP 预览服务器。 |
| `preview_stop` | 停止预览服务器。 |

#### H. 重构 (`refactor_*`)
| 工具 | 描述 |
|------|------|
| `refactor_rename_label` | 重命名标签并更新所有 jump/call 引用。 |
| `refactor_rename_character` | 重命名 `define e = Character(...)` 及其所有对话标签。 |
| `refactor_extract_route` | 将一段台词提取为新标签。 |
| `refactor_insert_dialogue` | 插入新对话行，保持缩进。 |

#### I. 翻译 (`translate_*`)
| 工具 | 描述 |
|------|------|
| `translate_get_stats` | 返回每种语言的完成百分比。 |
| `translate_find_missing` | 列出某语言的未翻译字符串。 |
| `translate_auto_block` | AI 翻译特定对话块到目标语言。 |
| `translate_export` | 生成 `.po` 或 `.rpy` 翻译文件。 |

#### J. 测试 (`test_*`)
| 工具 | 描述 |
|------|------|
| `test_create_scenario` | 录制或编写自动化试玩场景。 |
| `test_run_scenario` | 通过 bridge 或 headless runner 执行场景。 |
| `test_get_report` | 返回带截图的通过/失败报告。 |

#### K. 文档 (`docs_*`)
| 工具 | 描述 |
|------|------|
| `docs_search` | 模糊搜索离线 Ren'Py 文档索引。 |
| `docs_get_topic` | 返回文档主题的完整文本（内置 89 个主题）。 |

### 5.3 示例 I/O 模式 (`asset_generate_character`)

```json
{
  "name": "asset_generate_character",
  "description": "使用 Gemini 2.5 Flash 生成 2:3 角色立绘，包含 5 种情绪（neutral, happy, sad, surprised, angry）。图片会自动透明化处理并放入 game/images/。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "project_name": {"type": "string"},
      "character_name": {"type": "string"},
      "description": {"type": "string", "description": "给 AI 的视觉描述。"},
      "style_prompt": {"type": "string", "description": "可选的艺术风格修饰词。"},
      "remove_background": {"type": "boolean", "default": true}
    },
    "required": ["project_name", "character_name", "description"]
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "emotions": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "emotion": {"type": "string"},
            "file_path": {"type": "string"},
            "dimensions": {"type": "object", "properties": {"width": {"type": "integer"}, "height": {"type": "integer"}}}
          }
        }
      }
    }
  }
}
```

---

## 6. Live Bridge 系统

### 6.1 设计哲学
采用 Project B 的**文件 IPC** 方案，因为：
- 不需要在 Ren'Py 内部使用**网络套接字**（沙箱友好）。
- **跨平台**（Windows、macOS、Linux）。
- 只要 bridge 脚本存在，就能在 Ren'Py 重启后存活。

### 6.2 文件布局（项目内部）
```
game/
└── _mcp/
    ├── cmd.json          # 服务器在此写入命令
    ├── status.json       # bridge 在此写入状态更新
    ├── screenshot.png    # bridge 在此写入截图
    ├── tracking.json     # 持久化试玩热力图
    └── bridge.rpy        # 注入的 bridge 脚本
```

### 6.3 Bridge 脚本 (`_mcp_bridge.rpy`)
从 `bridge/templates/_mcp_bridge.rpy.j2` 渲染，注入到 `game/_mcp/bridge.rpy`。

**关键行为：**
- 在 `init -999 python:` 中运行，以在几乎所有游戏代码之前注册。
- 通过 `config.periodic_callbacks` 注册回调，每 **0.5 秒**轮询一次。
- 每 **2 秒**向 `status.json` 写入心跳。
- 读取 `cmd.json`；如果 `seq` 序号是新的，执行命令，然后删除 `cmd.json`（或标记为已消费）。

**命令协议（JSON）：**
```json
{
  "seq": 42,
  "command": "jump_to_label",
  "args": {
    "label": "chapter2_start",
    "variables": {"affinity": 5}
  }
}
```

**状态协议（JSON）：**
```json
{
  "seq": 42,
  "heartbeat": 1713123456,
  "current_label": "chapter2_start",
  "call_stack": ["chapter2_start"],
  "variables_snapshot": {"affinity": 5, "player_name": "Alex"},
  "screen_hierarchy": ["say", "choice"],
  "pending_screenshot": false,
  "error": null
}
```

### 6.4 安全考量
- **路径 Jail:** 服务器拒绝在解析后的项目路径之外写入 `cmd.json`。
- **命令白名单:** 只有 `bridge/protocol.py` 中定义的命令才会被接受。未知命令在写入文件前即被拒绝。
- **Eval 沙箱:** `bridge_eval` 在 Ren'Py 的 Python 环境中运行。我们不尝试对 Ren'Py 本身进行沙箱化；而是明确告知用户，bridge 等同于在游戏中运行任意 Python 代码。
- **Ren'Py 内无网络:** bridge 脚本仅执行本地文件 I/O。游戏不会发起 HTTP 请求。
- **原子写入:** 服务器先写入 `cmd.json.tmp`，再重命名为 `cmd.json`，防止 bridge 读取部分写入的命令。

### 6.5 Warp 实现
要在不破坏 Ren'Py 状态机的情况下跳转到标签：
1. 服务器写入 `cmd.json`，命令为 `jump_to_label`，并附带 `variables` 预设。
2. Bridge 设置 `renpy.session["_mcp_pending_warp_spec"] = {"label": "...", "variables": {...}}`。
3. Bridge 抛出 `renpy.errors.FullRestartException`。
4. Ren'Py 在顶层重启；`after_load` 或 `start` 钩子检查 session 键并重定向到目标标签。

---

## 7. 项目分析引擎

### 7.1 解析器设计
在 `analysis_engine/parser.py` 中实现一个**独立、零依赖的解析器**，**不**导入 Ren'Py。

**方法：**
- **分词:** 按行处理。使用正则表达式检测 Ren'Py 语句（`label`、`menu`、`jump`、`call`、`show`、`scene`、`define`、`image`、`return`、`$`、`if`、`elif`、`else`）。
- **缩进跟踪:** 维护缩进栈以分组块级子节点（如菜单选项、嵌套 `if` 块）。
- **恢复:** 遇到无法识别的语法时，解析器回退到通用的 `RawLineNode` 并继续解析。这确保了对新 Ren'Py 语法的韧性。

### 7.2 AST 节点结构
定义在 `analysis_engine/ast_nodes.py`：

```python
class BaseNode:
    type: str
    line: int
    file: str
    children: List['BaseNode']

class LabelNode(BaseNode):
    name: str
    parameters: List[str]

class SayNode(BaseNode):
    who: Optional[str]   # 角色标签或 None（旁白）
    what: str

class MenuNode(BaseNode):
    choices: List[ChoiceNode]

class ChoiceNode(BaseNode):
    text: str
    condition: Optional[str]
    block: List[BaseNode]

class JumpNode(BaseNode):
    target: str
    expression: bool   # True 表示 `jump expression`

class CallNode(BaseNode):
    target: str
    expression: bool
    from_invoked: Optional[str]

class ShowNode(BaseNode):
    image_name: str
    at_list: List[str]
    zorder: Optional[int]

class DefineNode(BaseNode):
    varname: str
    value_repr: str   # 为安全起见解析为字符串
```

### 7.3 索引器设计
`analysis_engine/indexer.py` 维护**项目索引** — 单一事实来源。

**索引模式（内存中的 Pydantic 模型）：**
```python
class ProjectIndex:
    version: int   # 每次更新递增
    files: Dict[str, FileIndex]
    labels: Dict[str, LabelRecord]
    screens: Dict[str, ScreenRecord]
    characters: Dict[str, CharacterRecord]
    images: Dict[str, ImageRecord]
    transforms: Dict[str, TransformRecord]
    variables: Dict[str, VariableRecord]
    testcases: Dict[str, TestCaseRecord]
    asset_files: Dict[str, AssetRecord]

class LabelRecord:
    file: str
    line: int
    outgoing_edges: List[Edge]
    incoming_edges: List[Edge]

class Edge:
    kind: Literal["jump", "call", "menu_choice", "fallthrough"]
    target: str
    source_line: int
```

**更新策略：**
- `watchdog` 观察者监控 `*.rpy`、`*.rpyc`、`images/` 和 `audio/` 目录。
- 文件变更时，仅重新解析变更的文件。
- 索引器将新 AST 合并到现有索引中，全局更新边引用。
- **500ms** 防抖，防止快速保存时的抖动。

### 7.4 图构建器
`analysis_engine/graph_builder.py` 遍历索引，生成 React-Flow 兼容的图：

```json
{
  "nodes": [
    {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "data": {"file": "script.rpy", "line": 1}},
    {"id": "menu_12", "type": "choice", "position": {"x": 0, "y": 100}, "data": {"choices": ["Go left", "Go right"]}}
  ],
  "edges": [
    {"id": "e1", "source": "start", "target": "menu_12", "type": "smoothstep"}
  ]
}
```

**节点分类：**
- `start` — `label start:` 节点。
- `normal` — 其他任何标签。
- `choice` — `menu` 块。
- `dead_end` — 没有出边且没有 `return` 的标签。
- `orphan` — 零入边（`start` 除外）的标签。

---

## 8. 资源管线

### 8.1 管线阶段
每个生成或导入的资源都经过可配置的管线：

```
[生成/导入] → [后处理] → [校验] → [放置] → [索引更新]
```

### 8.2 生成阶段
**基于插件的生成器**实现通用协议：

```python
class AssetGenerator(Protocol):
    async def generate_background(self, prompt: str, size: Tuple[int, int]) -> bytes: ...
    async def generate_character(self, prompt: str, emotions: List[str]) -> Dict[str, bytes]: ...
```

**默认插件:** 使用 `google-genai` 的 `GeminiGenerator`（Gemini 2.5 Flash 图像生成）。  
**配置:** 通过 `config.py` 或环境变量设置（`GEMINI_API_KEY`、`OPENAI_API_KEY` 等）。

### 8.3 后处理阶段
在 `services/asset_pipeline.py` 中实现：

| 步骤 | 逻辑 |
|------|------|
| **背景移除** | 对角色立绘运行 `rembg.remove()`。 |
| **标准化** | 最长边调整为 **750px**（Project A 标准）。背景标准化为 **1920×1080**。 |
| **格式转换** | Sprite 输出 PNG（透明），背景输出 JPG（更小），可选 WebP。 |
| **命名约定** | `game/images/{character_name}_{emotion}.png`，`game/images/bg_{scene_name}.jpg` |

### 8.4 校验阶段
- **尺寸检查:** 确保背景为 16:9，角色为 2:3。
- **重复检测:** 感知哈希比较，警告接近重复的图片。
- **引用检查:** 放置后，索引器验证图片标签是否在脚本或 `options.rpy` 中声明。

### 8.5 未使用资源检测
`asset_find_unused` 将 `ProjectIndex.images` 和 `ProjectIndex.asset_files` 交叉比对：
- 如果 `game/images/` 或 `game/audio/` 中的文件在索引中没有被 `show`、`scene` 或 `play` 引用，则标记。
- 用户会收到包含文件路径和最后修改日期的列表。

---

## 9. Web 面板设计

### 9.1 面板架构
面板是一个 **Vite 构建的 React SPA**，从 `web/static/` 作为静态文件提供。它通过以下方式与 Python 后端通信：

- **REST API** — 用于有状态请求（文件列表、构建触发）。
- **WebSocket** (`/ws/projects/{project_name}`) — 用于实时 bridge 遥测、索引器更新和构建进度流。

### 9.2 页面清单

| 页面 | 特性 |
|------|------|
| **Project Explorer** | 项目文件树形视图。创建/重命名/删除。 |
| **Script Editor** | 带 Ren'Py 语法高亮的 Monaco 编辑器。与 AST 图并排。 |
| **Visual Story Map** | 整个 VN 的交互式 React Flow 图。点击节点可读取脚本或通过 **bridge warp** 跳转到该标签。 |
| **Asset Gallery** | 图片/音频网格。预览、删除、重新生成。支持拖拽上传。 |
| **Live Preview** | iframe 嵌入 web 构建。叠加 bridge 控制（截图、变量检查器、跳转）。 |
| **Build & Deploy** | 一键构建。构建日志。Zip 下载。 |
| **Translation Manager** | 源文本/目标文本并排。缺失字符串高亮。 |
| **Settings** | SDK 路径、API 密钥、模板默认设置、bridge 轮询频率。 |

### 9.3 前后端通信模式
- **索引器推送:** 文件变更时，后端通过项目 WebSocket 发送 `{"event": "index_updated", "version": 7}`。
- **Bridge 遥测:** 后端将 `status.json` 心跳转发为 `{"event": "bridge_status", "payload": {...}}`。
- **构建流:** 构建子进程 stdout 通过 WS 逐行流式传输。

### 9.4 面板专属 vs 静默工具
以 `ui_` 为前缀的工具（如 `ui_get_assets`）是使用 `@modelcontextprotocol/ext-apps` 注册的 **App-only** 工具。它们对 CLI MCP 客户端隐藏，仅通过 REST 暴露给面板前端。

---

## 10. 构建与分发系统

### 10.1 SDK 自动安装
如果未设置 `RENPY_SDK_PATH`，服务器自动下载 SDK：

1. 检测操作系统（Windows、macOS、Linux）。
2. 下载 Ren'Py SDK 8.4.1（或最新 LTS）到 `~/.renpy-mcp/sdk/`。
3. 下载并安装 **web 支持模块**。
4. 将路径缓存到 `~/.renpy-mcp/config.json`。

### 10.2 构建管线
`build_service.py` 编排以下流程：

```python
async def build_project(project_name: str, package: str = "web") -> BuildResult:
    # 1. Lint 检查
    # 2. 运行 renpy.sh launcher distribute --package web <project>
    # 3. 后处理 web 构建
    # 4. 返回构建产物
```

**Web 构建后处理：**
1. 将生成的 `.zip` 解压到 `builds/{project}/web/`。
2. 如缺失则拷贝运行时 web 文件。
3. 修补 `index.html` 以禁用默认的启动拦截器（用于嵌入预览）。
4. 从优化后的资源集创建 `game.zip`。
5. 写入包含构建元数据的 `manifest.json`。

### 10.3 预览服务器
`preview_service.py` 挂载一个 FastAPI 子应用：

```python
app.mount(f"/preview/{project_name}", StaticFiles(directory=build_path), name=f"preview_{project_name}")
```

- **CORS:** 为 `localhost` 来源启用，使面板 iframe 可以嵌入。
- **生命周期:** 通过 `preview_start` / `preview_stop` 启动/停止预览服务器。

### 10.4 无头执行
对于 lint 和 CI 构建，Ren'Py 使用虚拟驱动启动：
```bash
RENPY_GL_ENVIRON="null" SDL_AUDIODRIVER="dummy" SDL_VIDEODRIVER="dummy" ./renpy.sh <project> lint
```

---

## 11. AI 集成策略

### 11.1 提示工程架构
不将提示仅塞入工具 docstring，而是采用**分层方法**：

1. **系统资源:** MCP 服务器暴露一个只读资源 `renpy://syntax-guide`，包含核心 Ren'Py 语法参考。客户端（Claude）在会话开始时获取一次。
2. **工具 Docstring:** 每个工具 docstring 包含：
   - 一行用途说明。
   - 针对该工具的**迷你语法指南**（例如 `script_generate` 如何写 `define` 语句）。
   - 1-2 个 **few-shot 示例**，放在 `<example>` XML 标签中。
3. **生成模板:** 对于 `script_generate`，服务器不完全依赖 LLM 的原始输出。而是发送结构化模板提示，要求 LLM 填写 JSON schema，然后服务器将其渲染为合法的 Ren'Py 脚本。

### 11.2 示例 Docstring 模式
```python
@mcp.tool()
async def script_generate(project_name: str, scene_description: str, tone: str = "casual"):
    """
    生成一段 Ren'Py 脚本块并持久化到项目中。

    ## Ren'Py 语法提醒
    - 标签: `label my_label:`
    - 对话: `e "Hello!"`  (其中 `e` 是角色标签)
    - 选项: `menu:` 后跟缩进的 ` "选项文本":` 块
    - 显示: `show alice happy at left`
    - 场景: `scene bg cafe`

    ## 示例
    <example>
    输入: "A cafe meeting where the player chooses tea or coffee."
    输出:
    label cafe_meeting:
        scene bg cafe
        show alice happy at center
        Alice "What would you like?"
        menu:
            "Tea":
                Alice "Coming right up!"
            "Coffee":
                Alice "Bold choice."
        return
    </example>
    """
    ...
```

### 11.3 图像生成集成
- **背景:** LLM 提供自然语言描述；服务器以 16:9 宽高比锁定发送给 Gemini。
- **角色:** LLM 提供描述。服务器使用**一次 Gemini API 调用**的多提示图像生成，将 5 种情绪批量生成，然后切片处理。
- **风格一致性:** 全局 `style_prompt`（每个项目存储在 `mcp_config.json` 中）会附加到所有图像生成提示中，以保持艺术风格一致。

### 11.4 模型无关性
服务器与客户端无关。任何兼容 MCP 的助手都可以连接。对于不支持资源的客户端，语法指南会自动作为文本提示附加到首次工具调用响应中。

---

## 12. 可扩展性与插件架构

### 12.1 插件发现
插件从 `~/.renpy-mcp/plugins/` 加载，也可从工作区内的 `plugins/` 目录加载。

**清单 (`manifest.json`)：**
```json
{
  "name": "my-generator-plugin",
  "version": "1.0.0",
  "entrypoints": {
    "tools": "tools.py",
    "generators": "generators.py",
    "dashboard_widgets": "widgets.tsx"
  }
}
```

### 12.2 工具插件
Python 模块可通过导入全局路由器注册额外工具：

```python
# my_plugin/tools.py
from renpy_mcp.tools.router import register_tool

@register_tool(category="custom")
async def custom_tool(project_name: str) -> str:
    return "Hello from plugin!"
```

### 12.3 解析器插件
插件可注册新的 AST 节点处理器：

```python
from renpy_mcp.analysis_engine.parser import register_statement

@register_statement(keyword="my_custom_statement")
def parse_custom_statement(parser, line):
    return CustomNode(text=line.strip())
```

### 12.4 面板微件插件
React 组件通过插件注册表被面板动态导入。面板在加载时扫描 `/api/plugins`，并将注册的小件挂载到指定的扩展点（例如资源库侧边栏）。

### 12.5 资源生成器插件
实现 `AssetGenerator` 协议即可接入第三方（如 Stable Diffusion API、ComfyUI、本地 ONNX 模型）。

---

## 13. 开发与部署计划

### 13.1 阶段路线图

| 阶段 | 周期 | 交付物 |
|------|------|--------|
| **Phase 1: 基础** | 4 周 | MCP 服务器核心、项目/文件工具、SDK 自动安装、基础构建/预览。 |
| **Phase 2: 分析与面板** | 4 周 | 自定义解析器、索引器、文件监视器、面板外壳、Project Explorer、Script Editor。 |
| **Phase 3: Bridge 与高级工具** | 4 周 | Live Bridge 注入、运行时工具、故事图可视化、重构、翻译。 |
| **Phase 4: AI 资源与打磨** | 3 周 | 资源管线、Gemini 集成、图像后处理、Asset Gallery、AI 脚本生成。 |
| **Phase 5: 可扩展性与发布** | 3 周 | Plugin API、文档、测试套件、CI/CD、v1.0 发布。 |

### 13.2 里程碑
- **M1 (第 4 周):** `create_project`、`build_project`、`preview_start` 在 Claude Desktop 中端到端可用。
- **M2 (第 8 周):** 面板可浏览文件并实时查看故事图。
- **M3 (第 12 周):** Live Bridge 支持从面板跳转到任意标签；重构工具安全且经过测试。
- **M4 (第 15 周):** AI 能在一个会话中生成包含角色和背景的完整 3 场景 VN。
- **M5 (第 18 周):** 在 GitHub 上发布公开测试版，附带完整文档和插件示例。

### 13.3 关键风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| **解析器与 Ren'Py 语法偏离** | 高 | 保持解析器模块化。添加回退的 "raw line" 模式。所有重构在实际应用前先用 Ren'Py launcher 验证。 |
| **Live Bridge 延迟** | 中 | 使用原子文件写入。如果 0.5s 轮询感觉 sluggish，提供可选的 localhost WebSocket bridge 作为高级插件。 |
| **Gemini API 成本/不可用** | 中 | 将生成抽象到 `AssetGenerator` 协议后。提供本地回退（如占位彩色矩形）用于离线工作。 |
| **Ren'Py SDK 下载不稳定** | 中 | 积极缓存。提供手动 `RENPY_SDK_PATH` 覆盖。在文档中提供镜像链接。 |
| **`bridge_eval` 安全性** | 中 | 明确文档说明 eval 等同于任意代码执行。要求每个项目显式用户 opt-in。 |

### 13.4 开源策略
- **License:** MIT（与两个父项目相同）。
- **治理:** 轻量级 BDFN（Benevolent Dictator For Now）模式，基于 Project A 的 `CONTRIBUTING.md`。
- **社区入口:** 为新的模板和解析器语句处理器提供 `good-first-issue` 标签。

---

## 附录 A: 术语表

- **MCP:** Model Context Protocol — 连接 AI 助手与外部工具的开放协议。
- **Bridge:** 注入的 Ren'Py 脚本，使运行中的游戏与 MCP 服务器能够双向通信。
- **Index:** 通过静态分析导出的 Ren'Py 项目的内存表示（标签、图片、变量等）。
- **Live Preview:** 本地提供的 HTTP 端点，显示项目的编译后 web 构建。

---

*设计规格书完*
