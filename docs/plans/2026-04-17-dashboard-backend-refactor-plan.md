# Ren'Py Dashboard/Backend 契约化重构 Checklist

## 使用原则
- [ ] 不清理当前目录，不删除未跟踪设计文件。
- [ ] 不直接切到全新 `git worktree`；如果必须隔离执行，先复制 `backend-refactor-plan.md`、`docs/dual-agent-design.md`、`docs/ui-redesign-analysis.md`、`new_design/`。
- [ ] 后端改造范围限定在 `src/renpy_mcp/`、`tests/`。
- [ ] 前端改造以 `new_design/design1_extracted/app` 为 UI 新标准，生产承载目录仍是 `dashboard/`。
- [ ] 不长期保留两套并行 Dashboard；迁移完成后，旧工作区页面与旧消息模型逐步退出。
- [ ] 所有阶段按小批次提交，始终保持后端可启动、前端可构建、核心测试可跑。
- [ ] **强制执行 TDD**：每一批改动必须先补或先写测试，再做实现；禁止“先写功能、最后补测试”。
- [ ] **TDD 最小循环固定为**：写失败测试 -> 运行并确认失败 -> 写最小实现 -> 运行目标测试通过 -> 运行相关回归测试。
- [ ] 如果某一项确实无法先写自动化测试，必须在执行摘要里明确说明原因、风险和替代验证方式，不能静默跳过。

## Phase 1：冻结契约与持久化
- [ ] 先为新增模型和 `ProjectManager` 持久化行为补失败测试，再开始实现。
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
- [ ] 先为每个新增 API 写失败测试或扩展现有 API 测试，再实现接口。
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
- [ ] 先补前端组件/页面级测试或最小可验证用例，再迁移对应 UI。
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
- [ ] 先为 WS/SSE 协议和 Blueprint 阶段流转写失败测试，再实现编排逻辑。
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

## Phase 5：生成单章节可读可视的最小原型
- [ ] 先为“Blueprint -> Chapter -> Scene -> Script -> Build/Preview”最小流水线补失败测试，再实现端到端编排。
- [ ] 明确 Phase 5 的交付目标是：基于已确认的 Blueprint，自动生成 **1 个章节、2-4 个场景**、**中文可正常显示**、**带最小视觉资产并可预览** 的原型，而不是一次性生成全项目。
- [ ] 新增最小原型编排入口，允许从已确认 Blueprint 触发“生成可玩原型”流程。
- [ ] 在后端确定“默认选取哪个章节作为原型章节”的规则；若 Blueprint 只有摘要信息，允许先生成/细化该章节下的 2-4 个 Scene 草案。
- [ ] 为原型章节生成结构化 Scene 数据，并写入 `meta/index.json` 或等价索引，确保 `scene_id -> file + label` 映射完整可读。
- [ ] 为原型章节的 2-4 个 Scene 生成可执行的 `.rpy` 脚本内容，并通过现有 `generate_script` / 文件写回能力落地到项目目录。
- [ ] 保证生成后的脚本不是孤立文件：需要把入口 `label start`、章节入口、场景跳转、基础 choice/branch 关系串起来，形成最小可玩闭环。
- [ ] 为原型流程定义“最低玩法标准”：至少能启动、进入第一个场景、完成 2-4 个场景推进，并在关键节点出现基础分支或继续推进逻辑。
- [ ] 接入最小视觉资产生成与挂接策略：Phase 5 至少保证章节入口和关键场景生成并接入基础背景资源；角色立绘和完整资源覆盖不是本阶段硬要求。
- [ ] 资源生成不能只停留在文件落盘：需要完成 `asset -> scene/location -> script` 的实际绑定，确保生成后的 `.rpy` 脚本引用真实背景资源，而不是长期停留在 `scene black` 占位。
- [ ] 为原型运行态补齐中文文本显示保障：至少在 Web 预览中提供稳定的 CJK 字体配置或等价方案，避免中文 narration/对话显示为方块字。
- [ ] 若资源生成失败，允许短期回退到脚本可运行但资源占位的状态；但 Phase 5 关闭前必须把“至少一个真实背景资源可见”纳入验收，而不是永久接受纯 `scene black` 方案。
- [ ] 把原型生成过程纳入现有 runtime session / progress 体系，让前端能看到“章节选择 / Scene 生成 / 写脚本 / 构建”这些阶段进度。
- [ ] 在 Dashboard 中补最小原型生成后的读取与展示：工作区不仅能读取真实 Scene 脚本、章节结构、StoryMap，还要提供至少一种**可读场景视图**，不能只把 `.rpy` 原文作为唯一展示方式。
- [ ] 将原型生成完成后的 build/preview 作为 Phase 5 的终态交付之一：至少有一条自动或半自动链路能把原型构建为可预览 web 版本。
- [ ] 为“原型生成成功后可直接预览”补集成测试 / E2E：覆盖 Blueprint 确认 -> 生成单章节原型 -> 生成并绑定最小背景资源 -> build 成功 -> preview 可打开。
- [ ] 为“中文在 workspace 与 web preview 中可正常显示”补测试：至少覆盖 CJK 字体配置生效、预览页不出现方块字、场景阅读视图可正确展示中文内容。
- [ ] 为“原型生成失败时的安全回退”补测试：失败时要么停在可恢复阶段，要么给出明确错误，不得留下半损坏的主流程状态。
- [ ] 把 `ChatEngine` 中后续会复用的“工具白名单”和“系统提示生成”抽离为更清晰的可复用接口，但以服务当前原型生成流水线为限，不提前做双 Agent 架构。

## Phase 6：完善质量、审计与扩展能力
- [ ] 先为 `AuditReport` 持久化、读取和前端消费写失败测试，再实现功能。
- [ ] 在后端实现 `AuditReport` 的持久化与读取接口。
- [ ] 第一版允许将现有 lint、graph、asset 检查结果汇总成结构化 `AuditReport`。
- [ ] 让 Dashboard 主页面增加 Audit 标签页。
- [ ] 让工作区页面和聊天面板消费同一份 `AuditReport`。
- [ ] 点击 issue 时能跳转或定位到对应 `scene_id`。
- [ ] 在 Phase 5 的“单章节可读可视原型”基础上，扩展到多章节生成、更完整的角色立绘/CG/音频资源覆盖、增量重生成、失败恢复和质量提升能力。
- [ ] 将审计流程接入生成流水线，形成“生成 -> 检查 -> 修正 -> 再验证”的可扩展闭环。
- [ ] 将资源链路从“最小背景资源”扩展到更完整的资产体系：角色立绘、CG、UI 资源、音频与资源一致性检查。
- [ ] 强化 continuity / branching / asset binding / script quality 的系统性校验，避免多章节扩展后出现剧情断裂、资源丢失或脚本不可运行问题。
- [ ] 为后续 `CreatorAgent` / `AuditorAgent` 预留不破坏现有协议的接管点。
- [ ] 双 Agent 真正落地时遵循 `docs/dual-agent-design.md`，但在本阶段仍以渐进接入为原则，不做脱离现有主线的大重写。

## 回归测试与交付检查
- [ ] `tests/unit/test_services_project_manager.py` 保持通过。
- [ ] `tests/chat_engine/test_confirmation_state.py` 保持通过。
- [ ] Dashboard 相关 e2e 不因新契约破坏 Build/Preview/Project Select 基础能力。
- [ ] 前端构建通过。
- [ ] 后端应用启动通过。
- [ ] 新工作区页面能读取真实项目、Blueprint、章节、StoryMap、Scene 脚本。
- [ ] 聊天面板能渲染真实的 Blueprint、进度消息；审计消息的完整接入允许延后到 Phase 6。
- [ ] Phase 5 完成时，至少有一个项目能从已确认 Blueprint 自动生成单章节原型，满足以下条件：2-4 个场景、中文在 workspace 与 web preview 中正常显示、至少一个真实背景资源已生成并接入脚本、并成功 build / preview。
- [ ] 旧页面仍可在迁移期作为兜底入口使用。
