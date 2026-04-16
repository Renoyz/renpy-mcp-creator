# Ren'Py Dashboard/Backend 契约化重构 Checklist

## 使用原则
- [ ] 不清理当前目录，不删除未跟踪设计文件。
- [ ] 不直接切到全新 `git worktree`；如果必须隔离执行，先复制 `backend-refactor-plan.md`、`docs/dual-agent-design.md`、`docs/ui-redesign-analysis.md`、`new_design/`。
- [ ] 后端改造范围限定在 `src/renpy_mcp/`、`tests/`。
- [ ] 前端改造以 `new_design/design1_extracted/app` 为 UI 新标准，生产承载目录仍是 `dashboard/`。
- [ ] 不长期保留两套并行 Dashboard；迁移完成后，旧工作区页面与旧消息模型逐步退出。
- [ ] 所有阶段按小批次提交，始终保持后端可启动、前端可构建、核心测试可跑。

## Phase 1：冻结契约与持久化
- [ ] 新建 `src/renpy_mcp/blueprint/models.py`，定义 `ProjectStatus`、`PipelineStage`、`ProjectMeta`、`ProjectBlueprint`、`ChapterSummary`、`SceneSummary`、`SceneScript`、`FlowNode`、`FlowEdge`。
- [ ] 新建 `src/renpy_mcp/chat_engine/audit_models.py`，定义结构化 `AuditIssue` 和 `AuditReport`。
- [ ] 保留现有 `src/renpy_mcp/models.py` 中的 `ProjectInfo`、`BuildRequest`、`BuildResult` 作为兼容层。
- [ ] 确定项目元数据目录结构为 `meta/project.json`、`meta/blueprint.yaml`、`meta/chat_history.json`、`meta/index.json`。
- [ ] 扩展 `src/renpy_mcp/services/project_manager.py`，新增 `read_project_meta`、`write_project_meta`、`read_blueprint`、`write_blueprint`、`read_project_index`、`write_project_index`。
- [ ] 让 `list_projects()` 优先读取 `meta/project.json`，旧项目没有元数据时自动回退生成。
- [ ] 让项目初始化同时创建 `game/`、`meta/` 和默认 `project.json`，默认状态为 `draft + idle`。
- [ ] 将聊天历史改为优先写入 `meta/chat_history.json`，同时兼容读取旧 `logs/chat-history.json`。
- [ ] 为上述模型与 `ProjectManager` 新增单元测试。

## Phase 2：打通只读快照 API
- [ ] 保持 `GET /api/projects`、`POST /api/projects`、`GET /api/projects/current` 兼容现有前端。
- [ ] 新增 `GET /api/projects/{name}/meta`。
- [ ] 新增 `PUT /api/projects/{name}/meta`。
- [ ] 新增 `GET /api/projects/{name}/blueprint`。
- [ ] 新增 `PUT /api/projects/{name}/blueprint`。
- [ ] 新增 `GET /api/projects/{name}/scenes`。
- [ ] 新增 `GET /api/projects/{name}/storymap`。
- [ ] 新增 `GET /api/projects/{name}/scenes/{scene_id}/script`。
- [ ] 让 `GET /api/projects` 返回完整 `ProjectMeta` 列表，但保持 `{projects:[...]}` 外层结构不变。
- [ ] 让 `GET /api/projects/{name}/scenes` 固定返回 `{chapters:[...]}`。
- [ ] 让 `GET /api/projects/{name}/storymap` 固定返回 `{nodes:[...], edges:[...]}`。
- [ ] 让 `GET /api/projects/{name}/scenes/{scene_id}/script` 返回结构化 `SceneScript`。
- [ ] 用 `meta/index.json` 或 Blueprint 推导 `scene_id -> file + label` 映射。
- [ ] 暂时保留 `/api/graph`、`/api/script/parse`、`/api/assets` 作为旧页面兼容接口。
- [ ] 为新 API 添加单元测试和集成测试。

## Phase 3：以 `new_design` 为标准迁移生产前端
- [ ] 确认生产前端继续使用 `dashboard/` 作为唯一构建入口。
- [ ] 以 `new_design/design1_extracted/app` 的工作区布局为目标，重建 `dashboard/src/pages/ProjectWorkspacePage.tsx`。
- [ ] 将 `BlueprintView`、`ChapterTimeline`、`MainContent`、`SceneView`、`StoryMapView`、`AuditReportView` 的结构迁移到 `dashboard/src/`。
- [ ] 将 `BlueprintCard`、`ProgressCard`、`AuditReportCard`、`ResourceCandidateCard` 的卡片体系迁移到 `dashboard/src/components/`。
- [ ] 重构 `dashboard/src/context/ProjectContext.tsx`，让它能加载 `meta`、`blueprint`、`scenes`、`storymap`、`audit`。
- [ ] 允许引入更适合新工作区复杂度的状态层组织方式，但禁止保留本地 `simulate*` 流程。
- [ ] 不迁移 `new_design` 的 mock 数据、伪生成逻辑和本地状态推进逻辑。
- [ ] `ProjectWorkspacePage.tsx` 不再沿用“Build/Preview + 3 张入口卡片”的旧范式。
- [ ] `LegacyIframePage` 仅作为过渡期兜底，不再作为目标体验。
- [ ] 让新工作区页面优先消费项目级新 API，而不是旧 `/api/graph` 或文件路径接口。
- [ ] 为新工作区页面补最少可用的交互测试或页面验收用例。

## Phase 4：重做 Chat 协议与 Blueprint 流程
- [ ] 保留 `/ws/chat` 作为唯一聊天入口。
- [ ] 将服务端事件协议升级为 `message`、`blueprint_draft`、`confirmation_request`、`progress`、`audit_completed`、`error`。
- [ ] 保持客户端请求协议只有 `user_message` 和 `confirmation_response`。
- [ ] 让后端在事件中显式返回 `pipeline_stage`，前端不再用关键字猜阶段。
- [ ] 重构 `dashboard/src/components/ChatDrawer.tsx` 或其替代组件，使其支持结构化卡片渲染。
- [ ] 让前端能渲染 `BlueprintCard`、`ProgressCard`、`AuditReportCard` 和普通文本消息。
- [ ] 原 `tool_start`、`tool_result` 仅保留为兼容兜底显示。
- [ ] 在 `src/renpy_mcp/web/chat_ws.py` 中实现最小 Orchestrator。
- [ ] 让最小 Orchestrator 支持 `idle -> collecting -> reviewing -> generating -> editing`。
- [ ] 让聊天历史写入 `meta/chat_history.json`。
- [ ] 第一版 Blueprint 访谈由后端维护阶段和摘要，LLM 只生成自然语言。
- [ ] “确认生成”必须通过 `confirmation_request` / `confirmation_response` 显式完成。
- [ ] 新增 `POST /api/projects/{name}/blueprint/generate`。
- [ ] 新增 `GET /api/projects/{name}/tasks/{task_id}`。
- [ ] 新增 SSE `GET /api/projects/{name}/events`。
- [ ] 明确 REST 负责快照、WS 负责对话、SSE 负责进度，不混用。
- [ ] 为 WS/SSE 新协议补集成测试。

## Phase 5：接入审计结果并预留双 Agent 骨架
- [ ] 在后端实现 `AuditReport` 的持久化与读取接口。
- [ ] 第一版允许将现有 lint、graph、asset 检查结果汇总成结构化 `AuditReport`。
- [ ] 让 Dashboard 主页面增加 Audit 标签页。
- [ ] 让工作区页面和聊天面板消费同一份 `AuditReport`。
- [ ] 点击 issue 时能跳转或定位到对应 `scene_id`。
- [ ] 把 `ChatEngine` 中“工具白名单”和“系统提示生成”抽离为可复用接口。
- [ ] 为后续 `CreatorAgent` / `AuditorAgent` 预留不破坏现有协议的接管点。
- [ ] 双 Agent 真正落地时遵循 `docs/dual-agent-design.md`，但不在本阶段提前实现。

## 回归测试与交付检查
- [ ] `tests/unit/test_services_project_manager.py` 保持通过。
- [ ] `tests/chat_engine/test_confirmation_state.py` 保持通过。
- [ ] Dashboard 相关 e2e 不因新契约破坏 Build/Preview/Project Select 基础能力。
- [ ] 前端构建通过。
- [ ] 后端应用启动通过。
- [ ] 新工作区页面能读取真实项目、Blueprint、章节、StoryMap、Scene 脚本。
- [ ] 聊天面板能渲染真实的 Blueprint、进度和审计消息。
- [ ] 旧页面仍可在迁移期作为兜底入口使用。
