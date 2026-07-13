# Ren'Py MCP Unified Server — 双 Agent 架构设计稿

**版本**: 1.0  
**日期**: 2026-04-16  
**状态**: 未来设计（已延期；以 `docs/ROADMAP.md` 为准）

---

## 1. 背景与问题

### 1.1 现状
当前 Ren'Py MCP Server 已注册约 70 个 MCP 工具，涵盖项目创建、脚本生成、资源生成、构建、实时调试、结构分析、Lint 检查等全链路能力。这些工具在单 Agent 的 ReAct 循环中统一暴露给 LLM，由 LLM 自主决定调用哪些工具、何时调用。

### 1.2 单 Agent 模式的结构性缺陷
在 Spec 模式 + 按 Scene/Chapter 分段生成的目标架构下，单 Agent 模式暴露出三个不可持续的问题：

1. **自我偏袒（Self-favoring Bias）**
   Agent 在生成内容后，倾向于选择性地调用审计工具，或轻描淡写地解释审计发现的问题，以维护自身生成行为的连贯性。

2. **上下文盲区（Context Blindness）**
   当生成 Scene 3 时，LLM 的上下文窗口可能已无法完整 hold 住 Scene 1 的关键设定（角色关系、伏笔、基调），导致 Scene 3 出现设定冲突。单 Agent 自身无法发现这种"跨时间窗口"的错误。

3. **权限混淆（Permission Confusion）**
   创作和审计的工具边界不清晰。Agent 可能在审计过程中"顺手"修改文件，导致审计痕迹不可追溯；也可能在生成过程中跳过必要的审计步骤，直接推进到下一个 Scene。

### 1.3 核心判断
**必须将创作与审计拆分为两个独立的 Agent，通过显式的"生成 → 审计 → 修复"闭环来保证输出质量。** 这不是过度工程化，而是 Spec 模式下质量控制的必要基础设施。

---

## 2. 核心设计目标

| 目标 | 说明 |
|------|------|
| **职责隔离** | Creator Agent 只写，Auditor Agent 只读。两者工具集零交集。 |
| **强制质检** | 每完成一个 Chapter（或高风险 Scene），必须触发 Auditor Agent，审计通过才能推进进度。 |
| **问题可追溯** | 审计发现的问题必须结构化输出（`AuditReport`），Creator Agent 的修复必须针对具体报告条目。 |
| **真实价值** | Auditor Agent 不做"语法复读机"（Lint 已足够），而是专注于跨 Scene 一致性、Blueprint 对齐、叙事基调等人类也难察觉的深层问题。 |

---

## 3. 架构设计

### 3.1 高层架构

```
用户确认 ProjectBlueprint
        ↓
┌─────────────────┐
│  Orchestrator   │  ← 协调器，维护进度状态，决定当前调用哪个 Agent
│   (ChatEngine)  │
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼ (仅在生成完成后触发)
┌────────┐  ┌────────┐
│Creator │  │Auditor │
│ Agent  │  │ Agent  │
└────┬───┘  └────┬───┘
     │           │
     ▼           ▼
Creative Tools  Audit Tools
(写文件/生图)   (只读分析/测试)
```

### 3.2 协调器（Orchestrator）职责

协调器是 `ChatEngine` 的核心升级，不直接调用 MCP tools，而是调度两个子 Agent：

- **状态维护**：跟踪当前项目的 `ProjectProgress`（生成到哪个 Scene/Chapter）。
- **调度策略**：
  - 用户输入为创作指令 → 调用 Creator Agent
  - 完成一个 Chapter 的所有 Scene → **强制调用 Auditor Agent**
  - 收到 `AuditReport` 且存在阻塞级问题 → 调用 Creator Agent 进行修复
  - 收到 `AuditReport` 且全部通过 → 更新进度，允许推进到下一 Chapter
- **会话隔离**：Creator Agent 和 Auditor Agent 各自维护独立的 LLM message history，避免审计结论污染创作提示词。

---

## 4. Agent 职责边界与工具权限

### 4.1 Creator Agent（创作 Agent）

**目标**：按 `ProjectBlueprint` 生成当前 Scene/Chapter 的脚本与资源。

**可调用工具**（Creative Tools，约 20-30 个）：

| 类别 | 示例工具 |
|------|---------|
| 项目 | `create_project`, `project_set_config` |
| 文件 | `edit_project_file`, `file_write` |
| 脚本 | `generate_script`, `attach_background_to_start` |
| 资源 | `generate_background`, `generate_character`, `asset_normalize` |
| 构建 | `build_project`, `preview_start` |

**核心约束**：
- 禁止调用任何 Audit Tool（`lint_project`、`story_find_dead_ends` 等）。
- 生成脚本前必须读取 `ProjectBlueprint`，确保不越级、不越界。
- 收到 `AuditReport` 后，必须逐条回应修复方案，不得忽略阻塞级（blocking）问题。

### 4.2 Auditor Agent（审计 Agent）

**目标**：对已生成的 Scene/Chapter 进行系统性只读检查，输出结构化 `AuditReport`。

**可调用工具**（Audit Tools，约 30-40 个）：

| 类别 | 示例工具 |
|------|---------|
| 代码质量 | `script_validate`, `lint_project`, `compile_project` |
| 结构分析 | `story_get_flow_graph`, `story_find_dead_ends`, `story_find_orphans` |
| 资源审计 | `asset_find_unused`, `list_project_files` |
| 运行时调试 | `bridge_get_state`, `test_run_scenario` |
| 文档查询 | `docs_search`（用于判定某语法是否为 Ren'Py 官方推荐写法） |

**核心约束**：
- **绝对禁止调用任何会修改文件系统或生成资源的工具**。
- 审计输入必须包含：当前 Blueprint、已生成的 `.rpy` 文件内容、项目索引（ProjectIndex）。
- 输出必须为严格格式的 `AuditReport`（Pydantic 模型），不得输出模糊的自然语言建议。

---

## 5. 工作流程：生成-审计-修复闭环

### 5.1 宏观流程

```
用户确认 Blueprint
    ↓
Creator Agent 生成 Scene 1.1
    ↓
Creator Agent 生成 Scene 1.2
    ↓
...（Chapter 1 的所有 Scene 生成完毕）
    ↓
【触发点】Orchestrator 强制调用 Auditor Agent
    ↓
Auditor Agent 执行五维审计
    ↓
输出 AuditReport
    ├─ 全部通过 → Orchestrator 标记 Chapter 1 confirmed，触发 build + preview
    └─ 存在阻塞问题 → Orchestrator 将 AuditReport 转交给 Creator Agent
              ↓
        Creator Agent 执行修复（最多 2 轮自纠正）
              ↓
        Auditor Agent 复验
              ↓
        通过 → 推进进度 / 不通过 → 暂停并通知用户人工介入
```

### 5.2 触发策略

| 触发时机 | 审计范围 | 说明 |
|---------|---------|------|
| **每 Chapter 结束** | 当前 Chapter 的所有 Scene + 关联资源 | 默认强制触发，覆盖率最高 |
| **高风险 Scene 结束** | 单个 Scene | 当 Blueprint 标记该 Scene 涉及关键分支或新角色首次登场时触发 |
| **用户手动触发** | 全项目 | 用户在 Dashboard 点击"运行全面审计" |
| **Spec 修改后** | 所有受影响的 Scene | Blueprint 变更后，自动将相关 Scene 状态重置为 pending，并在重新生成后触发审计 |

---

## 6. Auditor Agent 的五维审计模型

Auditor Agent 必须产出**真实且不可替代**的价值。为此，定义五个审计维度，每个维度对应具体的检查逻辑和输出格式。

### 6.1 维度一：跨 Scene 一致性审计（Continuity Audit）

**问题定义**：Creator Agent 在生成 Scene N 时，因上下文遗忘，导致与 Scene 1-N-1 的设定冲突。

**检查逻辑**：
1. 提取所有已生成 Scene 中的关键事实（角色关系、事件结果、玩家选择后果）。
2. 检查当前 Scene 的台词/旁白是否与之矛盾。

**示例发现**：
> Scene 1 中艾米明确表示"我从不喝咖啡"，但 Scene 3 中出现了艾米品尝咖啡的台词。建议将 Scene 3 中的饮品改为茶或果汁。

**输出字段**：
- `inconsistency_type`: `"character_knowledge"` | `"timeline"` | `"causality"`
- `source_scene`: `"scene_1_1"`
- `target_scene`: `"scene_1_3"`
- `description`: 冲突描述
- `suggested_fix`: 修复建议

### 6.2 维度二：Blueprint-现实对齐审计（Blueprint Fidelity Audit）

**问题定义**：生成的 `.rpy` 内容偏离了用户已确认的 Blueprint 意图。

**检查逻辑**：
1. 对比 `Blueprint.scenes[scene_id]` 的元数据与 `.rpy` 实际内容。
2. 检查：`has_choice`、`cast`、`location` 等字段是否被忠实执行。

**示例发现**：
> Blueprint 中 Scene 2.1 的 `has_choice: true`，但生成的 `.rpy` 中未包含 `menu:` 块。需补充分支选项。

**输出字段**：
- `deviation_type`: `"missing_choice"` | `"unauthorized_character"` | `"wrong_location"`
- `expected`: Blueprint 中的预期值
- `actual`: `.rpy` 中的实际值
- `suggested_fix`: 修复建议

### 6.3 维度三：资源-脚本双向对齐审计（Asset Coverage Audit）

**问题定义**：脚本引用了尚未生成的资源，或已生成资源未被脚本引用。

**检查逻辑**：
1. 解析 `.rpy` 中的所有 `show`、`scene`、`image`、`play` 语句。
2. 与文件系统 + Blueprint `assets` 清单做交叉比对。

**示例发现**：
> 脚本引用了 `show emi_happy`，但 `game/images/emi_happy.png` 不存在，且 Blueprint 中 `emi` 的 `emotions_generated` 列表也未包含 `happy`。

**输出字段**：
- `asset_type`: `"character"` | `"background"` | `"audio"`
- `asset_name`: `"emi_happy"`
- `status`: `"missing"` | `"unused"` | `"mismatch"`
- `suggested_fix`: `"调用 generate_character 补全 happy 情绪图"`

### 6.4 维度四：叙事基调审计（Tone Alignment Audit）

**问题定义**：某一 Scene 的情绪基调与项目整体 `narrative.tone` 发生偏离。

**检查逻辑**：
1. 将 Scene 的台词摘要 + `narrative.tone` 传入轻量 LLM（或本地情感分析模型）。
2. 要求评判一致性，给出具体偏离点。

**示例发现**：
> 项目基调为"温馨治愈"，但 Scene 2.2 出现了大量血腥描写（"血液在地板上蔓延"）。建议修改为更柔和的表达方式，或将其调整为悬疑/恐怖类项目。

**输出字段**：
- `target_tone`: `["温馨", "治愈"]`
- `detected_tone`: `"恐怖"`
- `severity`: `"blocking"` | `"warning"`
- `affected_lines`: `[12, 15, 18]`
- `suggested_fix`: 修改建议

### 6.5 维度五：可玩性预审（Playability Audit）

**问题定义**：脚本语法正确，但玩家可能在某分支后进入死胡同或无法触发结局。

**检查逻辑**：
1. 调用 `story_find_dead_ends`、`story_find_orphans`。
2. 结合 `test_run_scenario` 做关键路径遍历。
3. 检查：`start` 是否可到达所有标记为 `has_choice` 的选项？每个选项后的跳转目标是否存在且最终会 `return`？

**示例发现**：
> Scene 2.1 的菜单选项 "接受告白" 跳转到 `label confession_accepted`，但该 label 在当前项目中未定义。

**输出字段**：
- `issue_type`: `"dead_end"` | `"orphan_label"` | `"unreachable_choice"` | `"missing_return"`
- `location`: `"scene_2_1.rpy:23"`
- `severity`: `"blocking"`
- `suggested_fix`: 修复建议

---

## 7. 数据模型：AuditReport

```python
from pydantic import BaseModel
from typing import List, Literal, Optional

class AuditIssue(BaseModel):
    dimension: Literal[
        "continuity",           # 跨 Scene 一致性
        "blueprint_fidelity",   # Blueprint 对齐
        "asset_coverage",       # 资源-脚本对齐
        "tone_alignment",       # 叙事基调
        "playability",          # 可玩性
    ]
    severity: Literal["blocking", "warning", "info"]
    title: str
    description: str
    affected_scene: Optional[str] = None
    affected_file: Optional[str] = None
    affected_lines: Optional[List[int]] = None
    expected: Optional[str] = None
    actual: Optional[str] = None
    suggested_fix: str

class AuditReport(BaseModel):
    project_name: str
    audited_chapter: Optional[str] = None
    audited_scenes: List[str]
    timestamp: str
    overall_status: Literal["pass", "fail", "pass_with_warnings"]
    issues: List[AuditIssue]
    summary: str
```

### 7.1 `overall_status` 判定规则

- **`pass`**：零 issue，或仅有 `info` 级别 issue。
- **`pass_with_warnings`**：存在 `warning` 级别 issue，但无 `blocking`。允许推进进度，但会在 Dashboard 中显示黄色角标。
- **`fail`**：存在至少一个 `blocking` 级别 issue。必须修复后才能推进到下一 Chapter。

---

## 8. 实施路线图

### Phase 1：软分离（当前 Sprint，零架构改动）
- 在 `ChatEngine` 的 system prompt 中增加强制规则：
  > "每完成一个 Chapter 的所有 Scene 生成后，你必须调用 `script_validate`、`story_find_dead_ends` 和 `asset_find_unused` 进行自我检查。"
- 观察 LLM 是否能自发产出有价值的跨 Scene 一致性检查。

### Phase 2：硬分离（发布后 2-3 周）
- 在 `chat_engine/` 中拆分 `CreatorEngine` 和 `AuditorEngine`。
- `CreatorEngine` 只注册 Creative Tools；`AuditorEngine` 只注册 Audit Tools。
- 实现 `Orchestrator` 的调度逻辑：Chapter 生成完毕后自动触发 `AuditorEngine`。
- 定义 `AuditReport` Pydantic 模型，并打通到 WebSocket 协议（Dashboard 可渲染审计结果）。

### Phase 3：五维审计落地（发布后 4-6 周）
- 逐个实现五维审计的具体检查逻辑。
- 优先级：Playability > Blueprint Fidelity > Asset Coverage > Continuity > Tone Alignment。
- Dashboard 新增 "Audit Report" 页面，按维度分组展示 issue，支持一键跳转 Script Editor 修复。

### Phase 4：审计规则模板化（远期）
- 允许 `ProjectBlueprint` 中声明自定义审计规则：
  ```yaml
  audit_rules:
    - dimension: "continuity"
      severity: "blocking"
    - dimension: "tone_alignment"
      severity: "warning"
  ```
- 不同 `template_preset`（如 `mystery` vs `romance`）可以绑定不同的默认审计规则集。

---

## 9. 风险与收益分析

### 9.1 收益

| 收益点 | 说明 |
|--------|------|
| **质量跃升** | 从"能编译"升级到"能游玩且体验一致"。 |
| **用户信任** | 创作者看到系统主动发现并修复了连自己都注意不到的错误，控制感大幅增强。 |
| **错误收敛** | 在 Chapter 级别拦截错误，避免其污染后续所有 Scene。 |
| **可扩展性** | 新增审计规则只需扩展 `AuditorEngine`，不影响 `CreatorEngine` 的稳定性。 |

### 9.2 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| **审计成本（Token + 延迟）** | 中 | 只在 Chapter 结束后触发，不做每 Scene 审计；五维审计可并行执行。 |
| **Auditor 误报** | 中 | 引入 `severity` 分级，只有 `blocking` 才阻塞流程；`warning` 允许用户手动忽略。 |
| **修复循环过长** | 中 | 限制 Creator Agent 最多 2 轮自纠正，仍不通过则暂停并通知用户人工介入。 |
| **架构复杂度增加** | 低 | Phase 1 先用 prompt 验证价值，确认后再做硬分离。 |

---

## 10. 关键设计原则总结

1. **Creator 只写，Auditor 只读。** 工具权限零交集。
2. **审计不是可选步骤，是推进进度的闸口。**
3. **Auditor 的价值在于发现 Lint 发现不了的问题。** 语法错误交给 `lint_project`，Auditor 专注一致性、对齐性、可玩性。
4. **所有审计结果必须结构化。** `AuditReport` 是 Creator 修复的唯一输入，也是 Dashboard 展示的唯一数据源。
5. **渐进实施。** 先软分离验证假设，再硬分离落地架构。

---

*设计稿完*


---

## 11. Orchestrator 状态机详细设计

### 11.1 状态定义

Orchestrator 维护每个 `ChatSession` 的 `PipelineState`：

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel

class PipelineStage(str, Enum):
    IDLE = "idle"                           # 等待用户输入
    PLANNING = "planning"                   # 正在收敛需求/生成 Blueprint
    AWAITING_BLUEPRINT_CONFIRM = "awaiting_blueprint_confirm"
    CREATING = "creating"                   # Creator Agent 正在生成 Scene/Chapter
    AUDITING = "auditing"                   # Auditor Agent 正在执行检查
    FIXING = "fixing"                       # Creator Agent 正在根据 AuditReport 修复
    AWAITING_USER_FIX_CONFIRM = "awaiting_user_fix_confirm"
    BUILDING = "building"                   # 触发 build + preview
    COMPLETED = "completed"                 # 当前 Chapter 全部完成

class PipelineState(BaseModel):
    stage: PipelineStage = PipelineStage.IDLE
    current_chapter_id: Optional[str] = None
    current_scene_id: Optional[str] = None
    fix_round: int = 0                      # 当前修复轮次（限制最多 2 轮）
    last_audit_report: Optional[AuditReport] = None
    block_reason: Optional[str] = None      # 当 stage 卡住时，向用户解释原因
```

### 11.2 状态转移图

```
[IDLE]
  │ 用户输入创作需求
  ▼
[PLANNING] ──(Blueprint 草案生成)──► [AWAITING_BLUEPRINT_CONFIRM]
                                          │ 用户确认 Blueprint
                                          ▼
[CREATING] ◄────┬──┬──┬──┬──┬──┬──┬──┬──┘
  │             │  │  │  │  │  │  │  │
  │ 生成完一个 Scene
  │
  ├─ 还有下一个 Scene ──► [CREATING] (继续生成)
  │
  └─ 当前 Chapter 的 Scene 全部完成
      │
      ▼
  [AUDITING]
      │
      ├─ AuditReport.status == "pass"
      │       │
      │       ▼
      │   [BUILDING] ──(构建+试玩成功)──► [COMPLETED]
      │
      ├─ AuditReport.status == "pass_with_warnings"
      │       │
      │       ▼
      │   [AWAITING_USER_FIX_CONFIRM] ──(用户选择忽略)──► [BUILDING]
      │
      └─ AuditReport.status == "fail" & fix_round < 2
              │
              ▼
          [FIXING] ──(修复完成)──► [AUDITING] (复验)
              │
              └─ fix_round >= 2
                  │
                  ▼
              [AWAITING_USER_FIX_CONFIRM] (人工介入)
```

### 11.3 关键规则

- **从 `CREATING` 到 `AUDITING` 的转移是强制的**，不可被 Creator Agent 跳过。
- **从 `FIXING` 到 `AUDITING` 最多循环 2 次**。第 3 次失败时，Orchestrator 将 `last_audit_report` 和当前文件快照一起推送给用户，请求人工决策。
- **`BUILDING` 阶段失败**（如 `lint_project` 在构建时报出新错误），状态回退到 `FIXING`，由 Creator Agent 处理构建日志。

---

## 12. Agent 接口定义

### 12.1 CreatorAgent

```python
class CreatorAgent:
    def __init__(
        self,
        mcp: FastMCP,
        provider: BaseProvider,
        creative_tools: list[str],
    ) -> None:
        self.mcp = mcp
        self.provider = provider
        # 只注册 Creative Tools 的 schema
        self.adapter = CreativeToolAdapter(mcp, whitelist=creative_tools)

    async def generate_scene(
        self,
        blueprint: ProjectBlueprint,
        chapter_id: str,
        scene_id: str,
        messages: list[dict],
    ) -> CreatorResult:
        """
        生成单个 Scene。
        返回：写入的文件路径、脚本内容摘要、调用的工具链。
        """
        ...

    async def fix_issues(
        self,
        blueprint: ProjectBlueprint,
        audit_report: AuditReport,
        messages: list[dict],
    ) -> CreatorResult:
        """
        根据 AuditReport 执行修复。
        返回：修改的文件路径、修复摘要。
        """
        ...

class CreatorResult(BaseModel):
    success: bool
    affected_files: list[str]
    summary: str
    tool_calls: list[dict]
    error: Optional[str] = None
```

### 12.2 AuditorAgent

```python
class AuditorAgent:
    def __init__(
        self,
        mcp: FastMCP,
        provider: BaseProvider,
        audit_tools: list[str],
    ) -> None:
        self.mcp = mcp
        self.provider = provider
        # 只注册 Audit Tools 的 schema
        self.adapter = AuditToolAdapter(mcp, whitelist=audit_tools)

    async def run_audit(
        self,
        blueprint: ProjectBlueprint,
        chapter_id: Optional[str],
        scene_ids: list[str],
        messages: list[dict],
    ) -> AuditReport:
        """
        对指定范围执行五维审计。
        """
        # 1. 调用本地工具收集硬数据（lint、dead_ends、orphans、asset_unused）
        hard_data = await self._collect_hard_data(blueprint.project_name)
        # 2. 将硬数据 + 脚本内容 + blueprint 一起送入 LLM，执行软审计（continuity、tone）
        soft_issues = await self._run_soft_audit(blueprint, scene_ids, hard_data, messages)
        # 3. 合并为 AuditReport
        return self._merge_report(blueprint, chapter_id, scene_ids, hard_data, soft_issues)

    async def _collect_hard_data(self, project_name: str) -> HardAuditData:
        """并行调用本地分析工具，零 LLM 成本。"""
        ...

    async def _run_soft_audit(
        self,
        blueprint: ProjectBlueprint,
        scene_ids: list[str],
        hard_data: HardAuditData,
        messages: list[dict],
    ) -> list[AuditIssue]:
        """调用 LLM 进行 continuity 和 tone alignment 分析。"""
        ...
```

### 12.3 ToolAdapter 权限隔离

```python
class CreativeToolAdapter(ToolAdapter):
    """只暴露 Creative Tools 的 Adapter。"""
    def __init__(self, mcp: FastMCP, whitelist: list[str]) -> None:
        self.mcp = mcp
        self.whitelist = set(whitelist)

    def list_mcp_tools(self) -> list[Any]:
        all_tools = self.mcp._tool_manager.list_tools()
        return [t for t in all_tools if t.name in self.whitelist]

class AuditToolAdapter(ToolAdapter):
    """只暴露 Audit Tools 的 Adapter。"""
    def __init__(self, mcp: FastMCP, whitelist: list[str]) -> None:
        self.mcp = mcp
        self.whitelist = set(whitelist)

    def list_mcp_tools(self) -> list[Any]:
        all_tools = self.mcp._tool_manager.list_tools()
        return [t for t in all_tools if t.name in self.whitelist]
```

---

## 13. WebSocket 协议扩展

为了让 Dashboard 能实时渲染审计结果，需要在现有 WebSocket 消息协议中新增以下类型：

### 13.1 服务端 → 客户端

#### `audit_started`
```json
{
  "type": "audit_started",
  "session_id": "sess_abc123",
  "project_name": "campus_romance",
  "chapter_id": "ch_1",
  "scene_ids": ["sc_1_1", "sc_1_2"],
  "timestamp": 1713123456
}
```

#### `audit_completed`
```json
{
  "type": "audit_completed",
  "session_id": "sess_abc123",
  "project_name": "campus_romance",
  "chapter_id": "ch_1",
  "report": {
    "overall_status": "fail",
    "summary": "发现 2 个阻塞问题、1 个警告",
    "issues": [
      {
        "dimension": "playability",
        "severity": "blocking",
        "title": "缺失的跳转目标",
        "description": "Scene 1.2 的 menu 选项 '接受告白' 跳转至不存在的 label 'confession_accepted'",
        "affected_scene": "sc_1_2",
        "affected_file": "scripts/scene_1_2.rpy",
        "affected_lines": [23],
        "suggested_fix": "将 jump confession_accepted 改为 jump ending_happy"
      }
    ]
  },
  "next_stage": "fixing",
  "timestamp": 1713123462
}
```

#### `fix_started` / `fix_completed`
```json
{
  "type": "fix_started",
  "session_id": "sess_abc123",
  "project_name": "campus_romance",
  "fix_round": 1,
  "timestamp": 1713123465
}
```

```json
{
  "type": "fix_completed",
  "session_id": "sess_abc123",
  "project_name": "campus_romance",
  "fix_round": 1,
  "summary": "已修复 1/2 个阻塞问题（修改了 scene_1_2.rpy 第 23 行）",
  "timestamp": 1713123470
}
```

### 13.2 客户端 → 服务端

#### `user_audit_action`
用于用户在 Dashboard 中对审计结果做出决策：

```json
{
  "type": "user_audit_action",
  "session_id": "sess_abc123",
  "project_name": "campus_romance",
  "action": "approve_warnings",   // 或 "request_fix", "ignore_warning", "manual_edit"
  "target_issue_index": 2         // 当 action 为 ignore_warning 时指定
}
```

---

## 14. Dashboard 审计结果展示设计

### 14.1 Chat Drawer 层

当 `audit_completed` 消息到达时，Chat Drawer 渲染 `AuditReportCard`：

- **顶部**：状态色块（绿色=pass，黄色=pass_with_warnings，红色=fail）
- **中间**：折叠面板，按 `dimension` 分组展示 issue
  - 每个 issue 显示 `severity` 图标、`title`、`description`
  - `blocking` issue 下方出现"查看修复建议"按钮
- **底部**：
  - pass → "审计通过，正在构建试玩..."
  - pass_with_warnings → "存在警告，是否继续构建？"（[继续] [去 Dashboard 查看详情]）
  - fail → "存在阻塞问题，正在自动修复..."（修复中显示进度条）

### 14.2 Dashboard 主界面：Audit Report 页面（新增）

**左侧导航**：Projects / Blueprint / Story Map / **Audit Report** / Asset Gallery / Preview

**Audit Report 页面结构**：

```
┌────────────────────────────────────────────────────────────┐
│  Chapter 1「图书馆相遇」 审计结果                             │
│  ┌─────────┐                                              │
│  │  🔴 Fail │  2 blocking  ·  1 warning  ·  0 info         │
│  └─────────┘                                              │
│  [重新审计]  [一键应用修复建议]  [导出报告]                  │
├────────────────────────────────────────────────────────────┤
│  按维度筛选: [全部] [可玩性] [一致性] [Blueprint] [资源] [基调]│
├────────────────────────────────────────────────────────────┤
│  ┌─ Playability ───────────────────────────────────────┐  │
│  │ 🔴 缺失的跳转目标                                    │  │
│  │    scene_1_2.rpy:23                                  │  │
│  │    建议: 将 jump confession_accepted 改为...         │  │
│  │    [在编辑器中打开]  [标记为已修复]                  │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌─ Continuity ─────────────────────────────────────────┐  │
│  │ 🟡 角色设定冲突                                       │  │
│  │    Scene 1.1 中艾米讨厌咖啡，但 Scene 1.2 中...       │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

**交互细节**：
- 点击 issue 卡片中的"在编辑器中打开"，右侧 `ScriptEditor` 自动滚动到对应行号。
- 用户手动修改文件并保存后，Orchestrator 收到 `project_state_changed` 事件，自动提示"检测到文件变更，是否重新审计？"

---

## 15. 完整时序图示例：Chapter 1 的生成-审计-修复闭环

```
User          Chat Drawer    Orchestrator    CreatorAgent    AuditorAgent    MCP Tools    Dashboard
 │                │               │               │               │              │            │
 │ ──"确认生成第一章"────────►   │               │               │              │            │
 │                │ ──user_message────────►      │               │              │            │
 │                │               │              │               │              │            │
 │                │               │── generate_scene(blueprint, ch_1, sc_1_1)──►│            │
 │                │               │               │── call_tool(generate_script)────────────►│
 │                │               │               │◄── success ──│              │            │
 │                │               │◄── CreatorResult ──│          │              │            │
 │                │◄── tool_result + "Scene 1.1 已生成" ──│       │              │            │
 │                │               │              │               │              │            │
 │                │               │── generate_scene(blueprint, ch_1, sc_1_2)──►│            │
 │                │               │               │── call_tool(generate_script)────────────►│
 │                │               │               │◄── success ──│              │            │
 │                │               │◄── CreatorResult ──│          │              │            │
 │                │◄── "Scene 1.2 已生成" ──│           │              │              │            │
 │                │               │              │               │              │            │
 │                │               │── Chapter 结束，进入 AUDITING ──►│            │            │
 │                │◄── "正在审计 Chapter 1..." ──│       │              │              │            │
 │                │               │              │               │── run_audit()──►│           │
 │                │               │              │               │── call_tool(lint_project)──►│
 │                │               │              │               │◄── result ────│            │
 │                │               │              │               │── call_tool(story_find_dead_ends)──►│
 │                │               │              │               │◄── result ────│            │
 │                │               │              │               │── LLM soft audit ──►│       │
 │                │               │              │               │◄── issues ────│            │
 │                │               │              │               │              │            │
 │                │               │◄────────── AuditReport ──────│              │            │
 │                │               │              │               │              │            │
 │                │               │   [发现 blocking 问题]        │              │            │
 │                │               │── fix_issues(AuditReport)──►│              │            │
 │                │◄── "正在修复..." ──│          │               │              │            │
 │                │               │               │── call_tool(edit_project_file)──────────►│
 │                │               │               │◄── success ──│              │            │
 │                │               │◄── CreatorResult ──│          │              │            │
 │                │               │              │               │              │            │
 │                │               │── 复验：run_audit() ───────►│              │            │
 │                │               │              │               │── (同上审计流程) ──►│       │
 │                │               │◄────────── AuditReport(pass) ─│              │            │
 │                │               │              │               │              │            │
 │                │               │── build_project + preview_start ──►│        │            │
 │                │◄── "Chapter 1 完成，试玩链接：..." ──│      │              │            │
 │                │               │              │               │              │            │
 │                │────────────── broadcast: audit_completed + build_success ───────────────►│
 │                │               │              │               │              │            │
 │◄──"试玩链接+Dashboard 链接"──│               │               │              │            │
 │                │               │              │               │              │            │
```

---

## 16. 与现有 ChatEngine 的迁移方案

### 16.1 当前代码结构

当前 `ChatEngine` 位于 `src/renpy_mcp/chat_engine/engine.py`，核心方法是：

```python
class ChatEngine:
    async def run_turn(self, messages: list[dict]) -> dict[str, Any]:
        # 1. 获取全部 tools
        # 2. 调用 provider.chat()
        # 3. 执行 tool_calls
        # 4. 返回结果
```

### 16.2 最小侵入式迁移路径

**步骤 1：新建 `chat_engine/orchestrator.py`**
- 引入 `PipelineState` 和 `PipelineStage`。
- `Orchestrator.run(session_id, user_input)` 替代现有 `ChatEngine.run_turn` 的入口角色。

**步骤 2：改造 `ChatEngine` 为 `CreatorEngine`**
- 重命名文件/类，删除 `max_react_iterations` 中与审计相关的 prompt 片段。
- 在 `ToolAdapter` 层增加 `whitelist` 过滤，只暴露 Creative Tools。

**步骤 3：新建 `chat_engine/auditor.py`**
- 实现 `AuditorEngine`，只注册 Audit Tools。
- 先复用与 `CreatorEngine` 相同的 `BaseProvider`，只是 tools 不同、system prompt 不同。

**步骤 4：修改 `web/chat_ws.py`**
- 在 `/ws/chat` 路由中，将 `ChatEngine.run_turn` 替换为 `Orchestrator.run`。
- 新增对 `audit_started`、`audit_completed`、`fix_started`、`fix_completed` 消息的广播。

**步骤 5：渐进切换**
- 通过一个环境变量 `USE_DUAL_AGENT=true/false` 控制是否启用 Orchestrator。
- Phase 1 保持 `false`（软分离），Phase 2 切换为 `true`（硬分离）。

---

## 17. 性能优化：五维审计并行化策略

### 17.1 硬审计并行（本地工具调用）

`AuditorAgent._collect_hard_data()` 中的本地分析工具可以**完全并行**：

```python
async def _collect_hard_data(self, project_name: str) -> HardAuditData:
    results = await asyncio.gather(
        self.mcp.call_tool("lint_project", {"project_name": project_name}),
        self.mcp.call_tool("story_find_dead_ends", {"project_name": project_name}),
        self.mcp.call_tool("story_find_orphans", {"project_name": project_name}),
        self.mcp.call_tool("asset_find_unused", {"project_name": project_name}),
        self.mcp.call_tool("script_validate", {"project_name": project_name}),
    )
    return HardAuditData(
        lint=results[0],
        dead_ends=results[1],
        orphans=results[2],
        unused_assets=results[3],
        validation=results[4],
    )
```

### 17.2 软审计串行（LLM 调用）

`continuity` 和 `tone_alignment` 需要 LLM，成本较高，但可以**合并为一次 LLM 调用**：

```python
async def _run_soft_audit(...) -> list[AuditIssue]:
    prompt = f"""
    你是一位视觉小说编辑，正在审查以下已生成的 Scene 脚本。
    请从两个维度进行检查，并输出结构化问题列表：

    1. Continuity（跨 Scene 一致性）：检查当前 Scene 是否与前面 Scene 的设定冲突。
    2. Tone Alignment（叙事基调）：检查当前 Scene 的情绪是否与项目整体基调 {blueprint.narrative.tone} 一致。

    Blueprint: {blueprint_json}
    前面 Scene 的关键设定: {previous_facts}
    当前 Scene 脚本: {current_script}

    输出格式（JSON）：
    [
      {{
        "dimension": "continuity",
        "severity": "blocking",
        "title": "...",
        "description": "...",
        "suggested_fix": "..."
      }}
    ]
    如果没有问题，输出空数组 []。
    """
    response = await self.provider.chat(messages=[...], system=prompt)
    return json.loads(response.text)
```

### 17.3 缓存策略

- **Blueprint 未变 + Scene 文件未变** → 审计结果可以缓存 5 分钟，避免重复调用 LLM。
- **Hard Data 缓存**：`lint_project` 的结果可以缓存在 `AuditorAgent` 的内存中，直到检测到文件变更事件。

### 17.4 延迟预期

| 阶段 | 预期耗时 | 优化后 |
|------|---------|--------|
| 硬审计（5 个本地工具并行） | ~1-2 秒 | ~0.5-1 秒 |
| 软审计（1 次 LLM 调用） | ~2-4 秒 | ~2-3 秒 |
| 总审计时间 | ~3-6 秒 | **~2.5-4 秒** |
| 修复（1 轮） | ~3-5 秒 | ~3-5 秒 |
| 复验 | ~2.5-4 秒 | ~1 秒（缓存命中时） |

**结论**：一次完整的生成-审计-修复闭环，理想情况下可以控制在 **10-15 秒** 内，对创作者来说是可以接受的。

---

## 18. 总结

本设计稿在双 Agent 的核心理念基础上，进一步细化了：

1. **Orchestrator 的状态机**，确保审计是强制触发的流程闸口。
2. **Agent 接口定义**，明确了 Creator 和 Auditor 的输入输出边界。
3. **WebSocket 协议扩展**，让 Dashboard 能实时感知审计状态。
4. **Dashboard UI 设计**，将审计结果从后台日志转化为创作者可交互的质量面板。
5. **完整时序图**，让开发团队能直观理解 Chapter 级别的闭环流程。
6. **迁移方案**，确保从现有单 Agent 架构到双 Agent 架构的切换是渐进且低风险的。
7. **性能优化策略**，通过并行化和缓存将审计延迟控制在可接受范围内。

双 Agent 架构不是"为了拆分而拆分"，而是让**创作有自由、质量有守门、进度有闸口**。这是从"AI 辅助写代码"升级为"AI 辅助做游戏"的关键一跃。

---

*设计稿补充章节完*


---

## 19. 测试策略与验收标准

### 19.1 单元测试

#### `tests/chat_engine/test_orchestrator.py`
- 测试 `PipelineState` 的所有状态转移是否合法。
- 测试 `Orchestrator` 在生成完 Chapter 最后一个 Scene 后，是否**必定**触发 `AuditorAgent`。
- 测试 `fix_round >= 2` 且审计仍失败时，是否正确进入 `AWAITING_USER_FIX_CONFIRM`。

#### `tests/chat_engine/test_creator_agent.py`
- Mock `ToolAdapter`，验证 `CreatorAgent.generate_scene()` 只能调用 whitelist 内的工具。
- 验证 `CreatorAgent` 尝试调用审计工具时，是否抛出 `ToolNotAllowedError`。

#### `tests/chat_engine/test_auditor_agent.py`
- Mock 所有本地工具，验证 `_collect_hard_data()` 是并行调用的（通过 `asyncio.gather`）。
- 验证 `AuditorAgent` 尝试调用创作工具时，是否抛出 `ToolNotAllowedError`。
- 验证 `AuditReport` 的 `overall_status` 计算逻辑：
  - 零 issue → `pass`
  - 仅有 warning → `pass_with_warnings`
  - 存在 blocking → `fail`

### 19.2 集成测试

#### `tests/integration/test_audit_pipeline.py`
- 创建测试项目，写入两个故意冲突的 Scene 脚本。
- 调用 `AuditorAgent.run_audit()`，断言 `AuditReport` 中：
  - `continuity` 维度发现角色设定冲突
  - `playability` 维度发现死分支

#### `tests/integration/test_ws_audit_flow.py`
- 通过 `TestClient` 连接 `/ws/chat`。
- 模拟用户确认 Blueprint → 生成 Chapter 1 → 接收 `audit_started` → 接收 `audit_completed(fail)` → 接收 `fix_started` → 接收 `fix_completed` → 接收 `audit_completed(pass)`。
- 断言消息顺序和字段完整性。

### 19.3 E2E 验收标准

| 验收项 | 通过标准 |
|--------|---------|
| **强制审计触发** | 在任意前端（Chat Drawer / CLI TUI）完成 Chapter 生成后，10 秒内自动触发审计，成功率 100% |
| **权限隔离** | Creator Agent 连续生成 20 个 Scene，未调用任何 Audit Tool；Auditor Agent 连续审计 20 次，未修改任何文件 |
| **修复闭环** | 注入一个已知 blocking 问题（如缺失 label），系统在 2 轮自纠正内修复并复验通过，成功率 ≥ 80% |
| **Dashboard 同步** | Chat Drawer 触发审计后，Dashboard Audit Report 页面在 3 秒内显示结果，无需手动刷新 |
| **用户介入降级** | 当修复超过 2 轮仍失败时，系统暂停并向用户展示 AuditReport + 修改建议，用户确认后继续 |

---

## 20. 与现有 ConfirmationState 的集成

当前 `ChatEngine` 已有一个 `ConfirmationState`（`src/renpy_mcp/chat_engine/confirmation.py`），用于处理候选图确认等 Tool 级确认。双 Agent 架构需要将其扩展为支持三种确认层级：

### 20.1 确认层级模型

```python
class ConfirmationLevel(str, Enum):
    TOOL = "tool"           # 现有：候选图确认、覆盖确认等
    BLUEPRINT = "blueprint" # 新增：Blueprint 草案确认
    AUDIT = "audit"         # 新增：审计修复方案确认

class ConfirmationState(BaseModel):
    confirmation_id: str
    level: ConfirmationLevel
    prompt: str
    options: list[dict]     # 选项列表（候选图 / 同意/修改/拒绝 / 应用修复/人工编辑）
    on_confirm: callable    # 确认后的回调
    metadata: dict          # 附加数据（如 blueprint_draft、audit_report）
```

### 20.2 三种确认的具体表现

#### 1) Tool 级确认（现有）
- **场景**：`generate_character` 生成 3 张候选图，用户需要选 1 张。
- **UI**：Chat Drawer 中展示 2 列图片网格，每张图下方有"确认"按钮。
- **触发时机**：Creator Agent 执行 `generate_character` 的过程中。

#### 2) Blueprint 级确认（新增）
- **场景**：Planning Phase 结束，Agent 输出 Blueprint 草案。
- **UI**：Chat Drawer 渲染 `BlueprintCard`，底部有"确认并生成" / "修改设定" 两个按钮。
- **触发时机**：Orchestrator 从 `PLANNING` 转移到 `AWAITING_BLUEPRINT_CONFIRM` 时。
- **回调**：用户点击"确认" → Orchestrator 将 Blueprint 持久化，状态转移到 `CREATING`。

#### 3) Audit 级确认（新增）
- **场景**：
  - `AuditReport.status == "pass_with_warnings"`：系统询问用户是否忽略警告继续构建。
  - `fix_round >= 2` 且仍失败：系统询问用户是"查看建议手动修复"还是"强制继续"。
- **UI**：Chat Drawer 渲染 `AuditDecisionCard`，展示 issue 摘要和决策按钮。
- **触发时机**：Orchestrator 从 `AUDITING` 或 `FIXING` 转移到 `AWAITING_USER_FIX_CONFIRM` 时。

### 20.3 Orchestrator 中的集成伪代码

```python
class Orchestrator:
    async def handle_audit_report(self, session, report: AuditReport):
        if report.overall_status == "pass":
            session.pipeline_state.stage = PipelineStage.BUILDING
            await self.start_build(session)

        elif report.overall_status == "pass_with_warnings":
            session.pipeline_state.stage = PipelineStage.AWAITING_USER_FIX_CONFIRM
            self.confirmation.request_confirmation(
                confirmation_id=f"audit_warn_{session.session_id}",
                level=ConfirmationLevel.AUDIT,
                prompt="审计发现警告，是否继续构建？",
                options=[
                    {"label": "继续构建", "action": "proceed"},
                    {"label": "去 Dashboard 查看详情", "action": "inspect"},
                ],
                on_confirm=lambda action: self._on_audit_warn_confirm(session, action),
                metadata={"audit_report": report.model_dump()},
            )

        else:  # fail
            if session.pipeline_state.fix_round < 2:
                session.pipeline_state.stage = PipelineStage.FIXING
                session.pipeline_state.fix_round += 1
                session.pipeline_state.last_audit_report = report
                await self.creator_agent.fix_issues(
                    blueprint=session.blueprint,
                    audit_report=report,
                    messages=session.messages,
                )
                # 修复完成后自动回到 AUDITING
                session.pipeline_state.stage = PipelineStage.AUDITING
                await self.auditor_agent.run_audit(...)
            else:
                session.pipeline_state.stage = PipelineState.AWAITING_USER_FIX_CONFIRM
                self.confirmation.request_confirmation(
                    confirmation_id=f"audit_fail_{session.session_id}",
                    level=ConfirmationLevel.AUDIT,
                    prompt="自动修复 2 轮后仍存在阻塞问题，请人工介入",
                    options=[
                        {"label": "在 Dashboard 中手动编辑", "action": "manual_edit"},
                        {"label": "忽略并强制继续", "action": "force_proceed"},
                        {"label": "回退到上一版本", "action": "rollback"},
                    ],
                    on_confirm=lambda action: self._on_audit_fail_confirm(session, action, report),
                    metadata={"audit_report": report.model_dump()},
                )
```

### 20.4 Dashboard 与 Chat Drawer 的协同

- **Chat Drawer**：适合快速决策（"忽略警告继续？" / "强制继续？"）。
- **Dashboard Audit Report 页面**：适合深度查看详情、逐条 issue 审阅、手动编辑脚本。
- 当用户从 Chat Drawer 点击"去 Dashboard 查看详情"时，前端打开新标签页到 Audit Report 页面，同时 Chat Drawer 进入等待状态（不超时），直到用户从 Dashboard 触发 `user_audit_action` 消息。

---

## 21. 关键决策记录（ADR）

### ADR-1：为什么不做每 Scene 审计，而是每 Chapter 审计？

- **决策**：默认在 Chapter 结束后触发审计，高风险 Scene 可单独标记触发。
- **原因**：
  - 减少 LLM 调用成本（每 Chapter 审计一次 vs 每 Scene 审计一次，成本降低 50-70%）。
  - 跨 Scene 一致性审计需要至少 2 个 Scene 才能发现冲突，单 Scene 审计价值有限。
  - 创作者的心理确认节点更适合在"一章 playable demo"后，而不是"一个镜头"后。

### ADR-2：为什么 Creator Agent 修复后 Auditor Agent 必须复验，而不是直接放行？

- **决策**：每次修复后必须由 Auditor Agent 重新跑完整审计。
- **原因**：
  - Creator Agent 可能在修复 A 问题时引入 B 问题（如改了一个 label 名但漏改了 jump 引用）。
  - 复验的成本（2-4 秒）远低于漏发问题到下一 Chapter 的修正成本。

### ADR-3：为什么 Auditor Agent 的软审计（continuity/tone）必须依赖 LLM，而不是纯规则引擎？

- **决策**：硬审计用本地规则引擎，软审计用 LLM。
- **原因**：
  - "艾米讨厌咖啡但 Scene 3 喝了咖啡"这类跨 Scene 语义冲突，无法用正则或 AST 检测。
  - "基调偏离"属于审美判断，规则引擎无法定义。
  - LLM 软审计成本可控（按 Chapter 触发，每个项目约 3-5 次）。

### ADR-4：为什么不直接让 Creator Agent 兼任 Auditor（单 Agent 但换 system prompt）？

- **决策**：必须硬分离为两个 Agent，不能仅靠 prompt 切换角色。
- **原因**：
  - 实验表明（AutoScriptPlugin 及类似项目），同一 LLM 在生成后自我审计时，会倾向于为自己的输出辩护（confirmation bias）。
  - 两个独立 message history 能有效减少这种偏袒。
  - 工具权限白名单提供了工程级保障，防止"边写边改"的审计失效。

---

## 22. 下一步行动清单

| 优先级 | 任务 | 负责人 | 交付物 |
|--------|------|--------|--------|
| P0 | 实现 `ProjectBlueprint` Pydantic 模型 | 后端 | `src/renpy_mcp/blueprint/models.py` |
| P0 | 实现 `BlueprintManager` | 后端 | `src/renpy_mcp/services/blueprint_manager.py` |
| P0 | 改造 `create_project` 自动生成 `.mcp/blueprint.yaml` | 后端 | PR |
| P1 | 在 `ChatEngine` system prompt 中加入软分离规则 | 后端 | prompt 模板更新 |
| P1 | 实现 `AuditReport` Pydantic 模型 | 后端 | `src/renpy_mcp/chat_engine/audit_models.py` |
| P1 | 设计并实现 `AuditReportCard` 前端组件 | 前端 | `dashboard/src/components/AuditReportCard.tsx` |
| P2 | 拆分 `CreatorEngine` 和 `AuditorEngine` | 后端 | `src/renpy_mcp/chat_engine/creator.py` + `auditor.py` |
| P2 | 实现 `Orchestrator` 状态机 | 后端 | `src/renpy_mcp/chat_engine/orchestrator.py` |
| P2 | 扩展 WebSocket 协议（`audit_started`/`audit_completed`/...） | 前后端 | 协议文档 + 代码 |
| P3 | Dashboard 新增 Audit Report 页面 | 前端 | `dashboard/src/pages/AuditReportPage.tsx` |
| P3 | 编写 `test_audit_pipeline.py` 集成测试 | 后端 | 测试用例 |

---

*设计稿最终章节完*


---

## 23. Dashboard UI 与双 Agent 架构的匹配性重构

### 23.1 当前 UI 的核心问题

当前 Dashboard（`dashboard/src/`）采用**传统 IDE 式布局**：左侧固定导航（项目、Story Map、脚本编辑、资源管理），右侧主内容区展示对应页面，右下角悬浮 Chat Drawer。这种设计假设用户是**主动在多个功能模块间切换的开发者**。

但 Spec + 双 Agent 架构彻底改变了用户心智模型：
- 用户不再是"打开代码编辑器写脚本"，而是"确认大纲后看 AI 逐章生成"。
- 核心状态不再是"有哪些文件"，而是"当前生成到第几章、审计是否通过"。
- Chat Drawer 不再是"辅助查询工具"，而是**整个创作流程的主控台**。

### 23.2 六大约束与当前 UI 的冲突

| 冲突点 | 当前 UI 表现 | 用户使用场景中的痛苦 |
|--------|-------------|---------------------|
| **P1: 无 Blueprint 入口** | ProjectWorkspacePage 只有 Build/Preview + 三个卡片 | "我刚在 Chat 里确认了大纲，现在想看看它长什么样，但 Dashboard 里完全没有" |
| **P2: 无进度可视化** | 没有 Chapter/Scene 状态指示器 | "我让 AI 生成第一章，过了 30 秒不知道它生成到哪了，是不是卡住了" |
| **P3: ChatDrawer 不支持新消息** | 没有 `blueprint_draft`、`audit_completed` 的渲染分支 | "审计说有 3 个问题，但 Chat 里只显示成一段普通文字，看不清细节" |
| **P4: iframe 割裂** | Story Map / Script Editor / Assets 都是 `LegacyIframePage` | "我在 Story Map 里看到一个节点，想改台词，结果切到 Script Editor 找了半天" |
| **P5: 导航以工具为中心** | 侧边栏是"项目、Story Map、脚本编辑、资源管理" | "我想看第二章第三个 Scene 的脚本，但导航里没有 Scene 列表" |
| **P6: Build 与进度脱节** | Build/Preview 是全局按钮，不与 Chapter 绑定 | "我只想看第一章的效果，但 Preview 必须从游戏开头玩" |

### 23.3 重构方向：从"功能模块导航"到"进度驾驶舱"

新的 Dashboard 必须围绕**创作进度**重新组织信息架构：

```
项目列表（/projects）
    ↓
项目驾驶舱（/projects/:name） ← 核心页面
    ├── 顶部：项目标题 + Chapter 进度条 + Build/Preview
    ├── 左侧：Chapter 时间线（可展开 Scene，带状态色标）
    ├── 中间主区域：标签页动态切换
    │       ├── Blueprint（默认）
    │       ├── Scene 详情（脚本 + 资源 + 审计）
    │       ├── Story Map
    │       └── Audit Report
    └── 右侧边栏：资源快速预览 / 属性面板
```

### 23.4 关键修改项

#### 修改 A：ProjectWorkspacePage 升级为"项目驾驶舱"

**当前结构**：标题 + Build/Preview + 三个入口卡片
**目标结构**：
- 左侧 ChapterTimeline 显示项目所有 Chapter 和 Scene 的状态
- 中间主内容区默认展示 `BlueprintOverview`
- 底部状态栏显示："最后审计: 通过 ✅ | 视觉健康度: 92% | 3 张图待优化"

**设计理由**：创作者进入项目后的第一需求是"看整体进度和大纲"，而不是"打开编辑器"。

#### 修改 B：ChatDrawer 升级为"流程控制中心"

新增消息卡片类型：
- **`BlueprintCard`**：展示角色列表 + Chapter 时间线 + "确认并生成" / "修改设定" 按钮
- **`ProgressCard`**：展示当前生成进度条（"正在生成 Scene 1.2 — 社团教室背景"）
- **`AuditReportCard`**：顶部状态色块（绿/黄/红）+ 按维度折叠的 issue 列表 + 决策按钮
- **`ResourceCandidateCard`**：2 列网格展示候选图 + 每张图的"确认"/"重生成"按钮

**设计理由**：Chat Drawer 是统一对话引擎的核心皮肤。如果它不支持 Spec 和审计的消息类型，后端再强大的双 Agent 架构也无法被用户感知。

#### 修改 C：废弃 LegacyIframePage，改为内联组件

- **Story Map**：用 `@xyflow/react` 实现只读故事图，点击节点可跳转到对应 Scene 详情
- **Script Editor**：内联 Monaco Editor，支持外部传入 `file_path` 和 `line_number` 自动定位
- **Asset Gallery**：内联 React 组件，按 Chapter/Scene 分组展示资源

**设计理由**：iframe 与外层 React 应用处于不同的 JS 运行环境，无法做节点到代码的联动跳转，也不适合高频切换的创作 workflow。

#### 修改 D：新增 Audit Report 页面

作为项目驾驶舱主内容区的一个常驻标签页：
- 顶部显示最近一次审计的总体状态
- 按五维审计维度分组展示 issue 卡片
- 每个 issue 支持一键跳转 Script Editor 对应行号、一键请求重生成关联资源

**设计理由**：审计是双 Agent 架构的核心差异化能力。没有 Audit Report 页面，Auditor Agent 的输出只能埋没在 Chat Drawer 的消息流中。

### 23.5 用户收益对照表

| 用户痛点（当前 UI） | 重构后体验 |
|-------------------|-----------|
| "大纲在哪里？我在 Chat Drawer 里翻历史消息找 Blueprint。" | Dashboard 主页面默认展示 Blueprint，结构化、可折叠。 |
| "AI 生成到哪里了？我是不是卡住了？" | Chapter 时间线实时显示每个 Scene 的状态，generating 状态有旋转动画。 |
| "审计说有 3 个问题，但我只记得其中 1 个。" | Audit Report 页面集中展示所有 issue，支持按维度筛选，一键跳转修复。 |
| "我想改 Scene 2 的一句台词，但从 Story Map 切到 Script Editor 找了半天。" | 点击 Chapter 时间线的 Scene 2，主内容区直接显示脚本标签，自动定位。 |
| "这张背景图是哪一章用的？" | 资源展示按 Scene 分组，每张图都有"被引用处"标签。 |
| "我只想看第一章的效果。" | Chapter 节点旁有"试玩本章"按钮。 |

### 23.6 UI 重构的实施优先级

| 优先级 | 任务 | 涉及文件 |
|--------|------|---------|
| P0 | 重构 `ProjectWorkspacePage` 为三栏驾驶舱布局 | `dashboard/src/pages/ProjectWorkspacePage.tsx` |
| P0 | 实现 `ChapterTimeline` 组件 | `dashboard/src/components/ChapterTimeline.tsx` |
| P0 | ChatDrawer 扩展消息类型解析 | `dashboard/src/components/ChatDrawer.tsx` |
| P1 | 实现 `BlueprintCard` 和 `AuditReportCard` | `dashboard/src/components/BlueprintCard.tsx` + `AuditReportCard.tsx` |
| P1 | 新增 `AuditReportPage` | `dashboard/src/pages/AuditReportPage.tsx` |
| P2 | Story Map / Script Editor / Asset Gallery 内联化 | `dashboard/src/components/StoryMapGraph.tsx` + `ScriptEditor.tsx` + `AssetGallery.tsx` |
| P3 | Build/Preview 与 Chapter 绑定 | `ProjectWorkspacePage.tsx` + Preview iframe overlay |

---

## 24. 完整设计稿附录

### 24.1 相关文档索引

- 当前状态与实施优先级：`docs/ROADMAP.md`
- 本设计稿完整版本：`docs/dual-agent-design.md`
- 配套 UI 重构分析报告：`docs/archive/[COMPLETED]-2026-04-28-ui-redesign-analysis.md`
- 产品设计方案（Creator 聚焦版）：`docs/archive/[SUPERSEDED]-2026-04-14-product-design-proposal.md`
- 原始设计规格书：`docs/archive/[SUPERSEDED]-2026-04-14-design-specification.md`
- 用户流程分析：`docs/archive/[SUPERSEDED]-2026-04-14-user-workflow-analysis.md`

### 24.2 关键术语表

| 术语 | 定义 |
|------|------|
| **ProjectBlueprint** | 项目的轻量级结构化规格书，包含角色、场景、资源、叙事基调等元设定 |
| **Creator Agent** | 负责生成脚本与资源的 AI Agent，拥有 Creative Tools 的调用权限 |
| **Auditor Agent** | 负责审计与质检的 AI Agent，只拥有 Audit Tools 的只读权限 |
| **Orchestrator** | ChatEngine 的调度核心，维护 PipelineState，强制触发审计与推进进度 |
| **AuditReport** | 结构化审计报告，包含跨 Scene 一致性、Blueprint 对齐、资源覆盖、基调、可玩性五个维度 |
| **Chapter Timeline** | Dashboard 中的垂直时间轴组件，展示各 Chapter 和 Scene 的创作/审计状态 |
| **LegacyIframePage** | 当前 Dashboard 中用于嵌入旧版页面的 iframe 方案，计划逐步废弃 |

---

## 25. 结语

本设计稿从问题诊断出发，提出了 **Spec 模式 + 双 Agent 架构 + 进度驾驶舱式 UI** 的三位一体改革方案：

1. **Spec 模式** 解决"生成一致性"问题，让创作有宪法可依；
2. **双 Agent 架构** 解决"自我偏袒与盲区"问题，让质量有守门人；
3. **进度驾驶舱式 UI** 解决"用户控制感缺失"问题，让创作过程可视、可控、可回溯。

三者缺一不可。如果只有 Spec 而无双 Agent，Blueprint 容易沦为形式；如果只有双 Agent 而无新 UI，审计结果无法被用户有效消费；如果只有 UI 而无底层架构支撑，则只是空壳。

本方案当前延期。只有在真实用户验证通过、GameIR/资产协议/人工修改保护稳定后，才重新评估 Creator/Auditor 质量门；恢复实施时必须先依据 `docs/ROADMAP.md` 重写当前计划。

---

*设计稿全文完*
