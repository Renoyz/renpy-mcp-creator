# 前后端对接方案：后端改造重点

## 一、当前后端现状

| 维度 | 现状 |
|------|------|
| **框架** | FastAPI + MCP (FastMCP) + WebSocket Chat |
| **项目存储** | 纯文件系统（`workspace/<project_name>/`），无结构化元数据 |
| **API 能力** | 项目列表、创建、选择、编译、构建、脚本读写、资产遍历、静态分析（flow graph/labels/assets） |
| **对话能力** | `/ws/chat` WebSocket，基于 `ChatEngine` ReAct 循环，直接调用 MCP tools |
| **状态管理** | 仅有 `request.session["current_project_name"]`，无项目生命周期状态（draft/editing 等） |
| **蓝图生成** | 无！目前 LLM 只能通过 `generate_script` tool 写单个 `.rpy` 文件，没有“生成完整 Blueprint YAML + 章节结构”的能力 |
| **异步任务** | 无！Build/Compile 是同步阻塞调用，没有任务队列和进度推送机制 |

**结论**：后端目前是一套“面向 MCP Agent 的文件操作工具集”，但缺少“面向 Dashboard UI 的项目生命周期与蓝图编排服务层”。

---

## 二、对接目标

Dashboard 前端已演进为具备以下阶段的状态机：
- `idle` → `collecting`（Agent 对话收集需求）
- `reviewing`（展示摘要，等待用户确认）
- `generating`（后台生成 Blueprint + 场景脚本）
- `editing`（正常创作）

后端需要补全对应的数据持久化、状态流转、异步生成、进度推送四大能力。

---

## 三、后端改造清单（按优先级）

### P0：数据模型与持久化（最底层）

#### 3.1 新增/改造 `models.py`
目前只有 `ProjectInfo`（name, path, created_at, updated_at）。需要扩展为：

```python
class ProjectStatus(str, Enum):
    draft = "draft"
    blueprinting = "blueprinting"
    blueprinted = "blueprinted"
    generating = "generating"
    editing = "editing"
    completed = "completed"

class BlueprintPhase(str, Enum):
    idle = "idle"
    collecting = "collecting"
    reviewing = "reviewing"
    generating = "generating"
    editing = "editing"

class CharacterInfo(BaseModel):
    id: str
    name: str
    personality: str
    description: str
    avatar: str | None = None

class SceneChoice(BaseModel):
    id: str
    text: str
    next_scene_id: str | None = None
    condition: str | None = None

class SceneInfo(BaseModel):
    id: str
    chapter_id: str
    name: str
    status: str  # pending / generating / generated / confirmed / audit_fail
    order: int
    type: str = "normal"  # normal / branch_point / ending / hidden
    choices: list[SceneChoice] = []
    is_ending: bool = False

class ChapterInfo(BaseModel):
    id: str
    name: str
    description: str
    scene_count: int
    order: int
    scenes: list[SceneInfo] = []

class EndingInfo(BaseModel):
    id: str
    name: str
    condition: str

class ProjectBlueprint(BaseModel):
    title: str
    genre: str
    tone: str
    characters: list[CharacterInfo]
    chapters: list[ChapterInfo]
    endings: list[EndingInfo] = []
    branch_style: str = "linear"  # linear / light / heavy

class ProjectMeta(BaseModel):
    id: str  # directory name
    name: str
    description: str
    genre: str
    status: ProjectStatus
    blueprint_phase: BlueprintPhase
    created_at: datetime
    updated_at: datetime
    chapter_count: int
    scene_count: int
    confirmed_scenes: int
    cover: str | None = None
```

#### 3.2 持久化策略
**推荐方案**：每个项目目录下新增 `meta/project.json`（或 `meta/blueprint.yaml`），不引入外部数据库：

```
workspace/
  campus_romance/
    meta/
      project.json   ← ProjectMeta（状态、统计）
      blueprint.yaml ← ProjectBlueprint（可编辑）
      chat_history.json ← 对话历史（替代现有根目录 logs/chat-history.json）
    game/
      ...
```

**改造点**：
- `services/project_manager.py`：
  - `list_projects()` 不再只扫描目录名，而是读取 `meta/project.json`，回退时自动生成（兼容旧项目）。
  - 新增 `read_project_meta(name)` / `write_project_meta(name, meta)`。
  - 新增 `read_blueprint(name)` / `write_blueprint(name, blueprint)`。
  - `create_project()` 初始化时写入 `meta/project.json`（status=`draft`, blueprint_phase=`idle`）。

---

### P1：蓝图生成 MCP Tool + API

#### 3.3 新增 `tools/blueprint.py`
注册 MCP tool：`generate_blueprint(project_name, requirement_summary: str)`

**实现逻辑**：
1. 调用 LLM（复用 `chat_engine/providers.py`），Prompt 要求输出标准 YAML 结构。
2. LLM 返回 YAML 字符串。
3. 后端解析 YAML，填充 `ProjectBlueprint` 模型。
4. 写入 `meta/blueprint.yaml`。
5. 同步生成初始空场景文件到 `game/scenes/ch1.rpy`、`game/scenes/ch2.rpy` 等（仅 label 骨架）。
6. 更新 `project.json`：status → `editing`, blueprint_phase → `editing`。

**Prompt 模板示例**（后端需维护）：
```yaml
system: |
  你是一位视觉小说编剧。请根据用户需求生成 Ren'Py 项目蓝图。
  必须输出以下 YAML 格式，不要包含任何解释性文字：
  title: "..."
  genre: "..."
  tone: "..."
  characters:
    - id: c1
      name: "..."
      personality: "..."
      description: "..."
  chapters:
    - id: ch1
      name: "..."
      description: "..."
      scene_count: 3
  endings:
    - id: ending_good
      name: "..."
      condition: "..."
  branch_style: "light"
```

#### 3.4 FastAPI 新增 REST Endpoint
在 `fastapi_app.py` 中新增：

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/projects/{name}/meta` | 读取 `ProjectMeta` |
| PUT | `/api/projects/{name}/meta` | 更新 `ProjectMeta`（如 description、genre） |
| GET | `/api/projects/{name}/blueprint` | 读取 `ProjectBlueprint` |
| PUT | `/api/projects/{name}/blueprint` | 手动保存用户编辑后的 Blueprint YAML/JSON |
| POST | `/api/projects/{name}/blueprint/generate` | 提交生成请求，返回 `task_id` |
| GET | `/api/projects/{name}/blueprint/generate/status` | 查询生成任务进度 |

---

### P2：异步任务与进度推送

#### 3.5 引入后台任务机制
**最小可行方案**：使用 FastAPI `BackgroundTasks` + 内存字典 `_task_store`。
**生产方案**：引入 Celery + Redis（如果后续需要水平扩展）。

**以最小可行方案为例**：

```python
_task_store: dict[str, dict] = {}

@app.post("/api/projects/{name}/blueprint/generate")
async def api_generate_blueprint(name: str, request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    requirement_summary = body.get("requirement_summary", "")
    task_id = f"bp_{name}_{int(time.time())}"
    _task_store[task_id] = {"status": "pending", "percent": 0, "step": "排队中...", "error": None}
    background_tasks.add_task(_run_blueprint_generation, name, requirement_summary, task_id)
    return {"task_id": task_id}

def _run_blueprint_generation(name, requirement_summary, task_id):
    # 1. 更新 project meta: blueprint_phase -> generating
    # 2. 逐步更新 _task_store percent/step
    # 3. 调用 LLM generate_blueprint tool
    # 4. 成功/失败更新 _task_store 和 project meta
```

#### 3.6 SSE 进度推送（供 Dashboard GeneratingView 使用）
新增 Endpoint：

```python
@app.get("/api/projects/{name}/events")
async def api_project_events(request: Request, name: str):
    async def event_generator() -> AsyncGenerator[str, None]:
        while True:
            # 读取项目当前状态或任务进度
            yield f"data: {json.dumps(progress)}\n\n"
            await asyncio.sleep(1)
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

Dashboard `GeneratingView.tsx` 可用 `EventSource` 订阅此接口，实时更新进度条。

---

### P3：多轮对话状态对接（Chat WebSocket 改造）

#### 3.7 `chat_ws.py` 状态感知
当前 `chat_websocket` 是无状态的 ReAct 循环，每次用户消息都直接丢给 `engine.run_turn(messages)`。需要引入**对话阶段状态机**：

**改造方案**：
1. 在 `meta/project.json` 或内存/Redis 中维护每个项目的 `blueprint_phase`。
2. 当 `blueprint_phase == "collecting"` 时，LLM system prompt 切换为 **Blueprint Interview Prompt**：
   - 要求 LLM 扮演“蓝图需求收集 Agent”，按固定轮次提问。
   - 限制 tool access：此时**不允许**调用 `generate_blueprint`，只允许自然语言对话。
3. 当用户回复满足条件（如轮次 >= 2），LLM 输出需求摘要，后端自动将 `blueprint_phase` 设为 `reviewing`。
4. 当用户明确说“确认/生成”时，后端调用 `generate_blueprint` tool 并进入 `generating`。

**具体实现建议**：
- 新增 `ChatEngine` 的 system prompt 模板切换逻辑；或
- 更简单的做法：在 `chat_ws.py` 的 `handleUserMessage` 等价层（后端 Python）显式控制阶段，而不是完全依赖 LLM 自律。

**参考前端已有的 `simulateBlueprintInterview` 逻辑**：后端可复刻一套 Python 版本，用正则/规则判断轮次，不依赖 LLM 做状态判断，只让 LLM 生成自然语言回复。

#### 3.8 聊天记录格式扩展
当前 `chat-history.json` 只存 `role`/`content`。扩展为支持 `type` 和 `data`（与前端 `ChatMessage` 对齐）：

```json
{
  "messages": [
    {"role": "assistant", "type": "text", "content": "..."},
    {"role": "assistant", "type": "blueprint", "content": "项目蓝图已生成", "data": {...}},
    {"role": "assistant", "type": "progress", "content": "正在生成 Scene 1.1...", "data": {"percent": 25}}
  ]
}
```

---

### P4：静态分析数据对接 Dashboard 新视图

Dashboard 已新增：
- `StoryMapView`（需要 `FlowEdge`）
- `SceneView`（需要解析 `menu`/`jump`/`call`）
- `BlueprintView`（需要 `endings`/`branchStyle`）

后端已有 `api/graph` 返回 nodes/edges，但缺少与 Dashboard 类型对齐的接口：

**推荐新增 API**：

| Method | Path | 说明 |
|--------|------|------|
| GET | `/api/projects/{name}/storymap` | 返回 `nodes[]` + `edges[]`，格式与前端 `FlowEdge` 对齐 |
| GET | `/api/projects/{name}/scenes` | 返回所有 scenes 列表（含 choices、script content） |
| GET | `/api/projects/{name}/scenes/{scene_id}/script` | 返回某个场景的 Ren'Py 脚本文本 |

**注意**：后端目前的 `/api/script/parse` 是按文件路径查询的。Dashboard 希望按 `scene_id`（如 `s1-1`）查询。需要在后端建立 `scene_id → rpy file + label` 的映射索引（可在 `meta/index.json` 中维护，或由 Blueprint 推导）。

---

### P5：前端适配层（API Client）

当前前端 `appStore.tsx` 全部是 mock 数据和本地状态。对接时需要：
1. 引入 `axios` 或原生 `fetch` 封装。
2. `appStore` 改造为：初始化时 `fetchProjectMeta()` / `fetchBlueprint()`，后续 mutation 调用对应 REST API。
3. `ChatPanel` 的 WebSocket 消息格式需要与后端对齐（目前 Dashboard 的 `ChatStore` 使用模拟本地回复，需要接入真实的 `/ws/chat`）。

**本计划重点在于后端改造，前端适配仅作为对接边界说明。**

---

## 四、改造优先级与里程碑

### Phase 1：元数据与 Blueprint 读写（1 周）
- `models.py` 扩展
- `project_manager.py` 增加 `meta/` 读写
- `fastapi_app.py` 新增 `/meta`、`/blueprint` REST 接口
- 前端 `appStore` 对接读取（可看到真实项目的 draft/editing 状态）

### Phase 2：蓝图生成异步任务（1 周）
- 新增 `tools/blueprint.py` + LLM Prompt
- `fastapi_app.py` 新增 `/blueprint/generate` + BackgroundTasks + SSE
- Dashboard `GeneratingView` 接入 SSE

### Phase 3：Chat 多轮状态机（1 周）
- `chat_ws.py` 引入 `blueprint_phase` 感知
- 后端实现 `BlueprintInterviewAgent`
- Dashboard `OnboardingView` + `ChatPanel` 对接真实 WS

### Phase 4：Scene/StoryMap API（0.5 周）
- 新增 `/storymap`、`/scenes`、`/scenes/{id}/script`
- Dashboard `StoryMapView`、`SceneView` 对接

---

## 五、关键技术决策

| 决策点 | 推荐方案 | 理由 |
|--------|---------|------|
| 项目元数据存储 | 每个项目目录下 `meta/project.json` + `meta/blueprint.yaml` | 零外部依赖，兼容现有文件系统架构，便于版本控制 |
| 异步任务 | FastAPI `BackgroundTasks` + 内存 `_task_store` + SSE | 最小侵入，足够支撑单机演示；后期可无缝迁移到 Celery |
| 进度推送 | SSE (`/api/projects/{name}/events`) | 比 WebSocket 更轻量，单向推送 perfectly fits |
| LLM 调用 | 复用现有的 `providers.py`（Anthropic/Kimi/DeepSeek/Qwen） | 已有统一封装，无需新增依赖 |
| Chat 状态机 | 后端规则驱动（Python 判断轮次）+ LLM 生成文案 | 避免过度依赖 LLM 自律，成本低、可控性高 |

---

## 六、总结：后端核心缺口

1. **没有 Blueprint 概念**：当前后端只有文件级别的 `generate_script`，没有“生成项目级 YAML 蓝图并落盘”的能力。
2. **没有项目状态机**：`ProjectInfo` 过于简单，无法支撑 Dashboard 的 `draft` → `collecting` → `generating` → `editing` 生命周期。
3. **没有异步任务与进度推送**：Build/Compile 都是同步阻塞，生成蓝图中途无反馈。
4. **Chat 无阶段感知**：`/ws/chat` 是无状态的通用 ReAct 循环，没有针对 Blueprint 生成的 Interview/Review 模式。
5. **Scene 级别 API 缺失**：现有 API 面向文件路径，Dashboard 希望面向 `scene_id` 和结构化 `choices`。
