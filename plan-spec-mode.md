# Ren'Py MCP — Spec 模式重构计划书

**版本**: 1.0  
**日期**: 2026-04-16  
**状态**: 计划待审批  

---

## 1. 引言与核心判断

### 1.1 背景
当前项目已完成 MCP Server 双通道（stdio + HTTP）、70 个工具注册、Chat Engine ReAct 循环、SDK 自动下载及 Dashboard React 骨架。Day 5 硬目标（Chat Drawer 自然语言创建项目）已跑通，正处于**基础验证向功能闭环过渡**的关键窗口。

### 1.2 核心判断
现有 Chat Engine 采用"需求 → 直接工具调用"的裸 ReAct 模式，存在以下不可持续的结构性缺陷：
- **一致性风险**：LLM 在多轮生成中容易自由发挥，导致角色名突变、画风偏离、分支逻辑断裂。
- **错误传播**：第一章的设定错误会连锁污染第二章及后续资源，修正成本指数级上升。
- **用户控制感缺失**：AI 可能在 30 秒内狂写多个文件、生成大量资源，创作者产生"被绑架感"。
- **上下文瓶颈**：随着脚本累积，长上下文导致 LLM 中间遗忘，第六章可能"复活"第三章已写死的角色。

**结论**：必须在当前窗口引入 **Spec 模式 + 按 Scene/Chapter 分段生成**，将创作流程从"即兴表演"升级为"先定大纲、再分镜拍摄"。

---

## 2. Spec 模式的好处

| 维度 | 无 Spec（现状） | 有 Spec（目标） |
|------|----------------|----------------|
| **一致性** | 靠 prompt 约束，随轮数衰减 | Spec 作为项目"宪法"，所有生成工具强制引用 |
| **可控性** | AI 一次性生成全部内容，用户被动接受 | 每 Scene/Chapter 后确认，修正范围可控 |
| **上下文压力** | 全量脚本 + 资源历史塞入 LLM | 每次只需当前 Scene + Spec 摘要 |
| **错误修复成本** | 发现错误时可能需要重写多个文件 | 只回滚当前 Scene 及其直接关联资源 |
| **Dashboard 价值** | 文件浏览器 + 代码编辑器 | 可视化大纲 + 进度导航 + 结构质检 |
| **可扩展性** | 新增工具需反复调 prompt | 新增工具只需声明读取 Spec 的哪些字段 |

---

## 3. 新模式下的用户使用流程

### 3.1 宏观流程

```
用户自然语言输入
    ↓
【Phase 1: 需求收敛】
Agent 通过多轮提问细化需求（题材、风格、角色、预估章节数）
    ↓
【Phase 2: Spec 生成】
Agent 输出结构化 ProjectBlueprint 草案
    ↓
【Phase 3: Spec 确认】
用户在 Chat Drawer / Dashboard 中查看、修改并确认 Blueprint
    ↓
【Phase 4: 分段生成】
按 Chapter → Scene 的粒度逐段生成脚本与资源
    ↓
【Phase 5: 章节确认与试玩】
每完成一个 Chapter，自动构建并启动 Preview，用户试玩后选择：
    ├─ 继续下一章
    ├─ 修改当前章（Execution 级小修）
    └─ 回改大纲（Spec 级大修）
    ↓
【Phase 6: 发布】
全部章节确认后，导出最终 Web 包
```

### 3.2 关键原则

- **Planning vs Execution 分离**：任何涉及角色增删、场景结构变更、结局走向修改的操作，必须先回到 Spec 层；台词微调、单张图重生成、位置调整属于 Execution 层。
- **Scene 为原子单元**：AI 一次只生成 1 个 Scene（1 个 `label` 块）。
- **Chapter 为确认批次**：每 2-4 个 Scene 组成 1 个 Chapter，完成后触发构建 + 试玩。
- **进度锁**：`generate_script` 等工具在执行前校验当前预期 Scene，拒绝越级生成。

### 3.3 典型会话示例

> **用户**：我想做一个校园恋爱视觉小说。
>
> **Agent**：好的！为了帮你规划，我需要确认几个细节：
> 1. 你希望有几个主要角色？（建议 1-2 个）
> 2. 预计多少章节？（建议 3 章）
> 3. 想要的画风？（清新水彩 / 日系赛璐珞 / 复古像素）
>
> **用户**：女主角樱，男主玩家视角，3 章，清新水彩。
>
> **Agent**：已为你生成项目蓝图：
> - 项目名：`campus_romance`
> - 角色：樱（元气系，棕色短发）
> - 章节：
>   - Chapter 1「图书馆相遇」— 2 个 Scene
>   - Chapter 2「社团活动」— 2 个 Scene
>   - Chapter 3「告白结局」— 2 个 Scene
> 需要我先创建项目并生成第一章吗？
>
> **用户**：好的。
>
> **Agent**：【生成 Scene 1.1】→ 生成背景 `bg_library` → 生成角色 `sakura_neutral` → 写入脚本 → **Chapter 1 完成，构建试玩中...**
>
> **用户**：女主表情有点僵硬，重新生成一下。
>
> **Agent**：重新生成 `sakura_happy`，仅替换该资源，不重写脚本。
>
> **用户**：第三章改成悲剧结局吧。
>
> **Agent**：这是 Spec 级修改，我先更新蓝图，你再确认后继续生成。

---

## 4. ProjectBlueprint 数据结构

### 4.1 核心 Schema（YAML/JSON）

```yaml
version: "1.0"
project_name: "campus_romance"

narrative:
  premise: "小林在图书馆偶遇樱，经历社团活动后迎来告白结局"
  tone: ["温馨", "治愈"]
  template_preset: "romance"

cast:
  - tag: "sakura"
    name: "樱"
    role: "女主角"
    archetype: "元气系"
    appearance: "棕色短发，绿色发带"
    emotions: ["neutral", "happy", "sad", "blush"]

  - tag: "player"
    name: ""
    role: "男主角"
    is_player_proxy: true
    emotions: []

chapters:
  - id: "ch_1"
    title: "图书馆相遇"
    scenes:
      - id: "sc_1_1"
        title: "初见"
        location: "学校图书馆"
        cast: ["sakura", "player"]
        has_choice: false
        status: "pending"    # pending | generating | generated | confirmed
      - id: "sc_1_2"
        title: "借书"
        location: "学校图书馆"
        cast: ["sakura"]
        has_choice: false
        status: "pending"

  - id: "ch_2"
    title: "社团活动"
    scenes:
      - id: "sc_2_1"
        title: "邀请"
        location: "社团教室"
        cast: ["sakura", "player"]
        has_choice: true
        choices:
          - text: "接受邀请"
            flag: "join_club"
          - text: "婉拒"
            flag: "no_club"
        status: "pending"

assets:
  style_anchor:
    preset: "watercolor_anime"
    locked: true
  backgrounds:
    - name: "bg_library"
      description: "安静的学校图书馆，午后阳光透过窗户"
      status: "pending"
  characters:
    - tag: "sakura"
      anchor_status: "pending"
      emotions_generated: []

metadata:
  current_chapter_idx: 0
  current_scene_idx: 0
  is_frozen: false
```

### 4.2 设计约束

- **不存台词**：Blueprints 只存元设定，具体台词在 `.rpy` 文件中。
- **不存像素数据**：只存资源名称、描述和生成状态。
- **状态字段驱动 UI**：`status` 字段直接映射到 Dashboard 的进度指示器。

---

## 5. UI 与交互设计

### 5.1 Chat Drawer 层（对话侧）

| 交互阶段 | UI 表现 |
|---------|--------|
| **需求收敛** | Agent 以问卷气泡形式提问，用户逐条回复 |
| **Spec 草案展示** | 渲染 `BlueprintCard`：折叠面板展示角色列表 + 章节时间线 |
| **Spec 确认** | 卡片底部出现"确认并生成" / "修改设定" 两个按钮 |
| **Scene 生成中** | 显示进度条："正在生成 Scene 1.1 — 初见" |
| **Chapter 完成** | 返回结构化消息："第一章已完成" + 试玩链接 + "继续第二章" 快捷按钮 |
| **资源候选确认** | 2 列网格展示候选图，每张带"确认"/"重生成"按钮 |

### 5.2 Dashboard 层（面板侧）

#### 页面 A：Blueprint Overview（新增）
- **顶部**：项目名、画风预设卡片、视觉健康度进度条
- **左侧 Cast 栏**：角色头像 + 名称 + 已生成情绪数角标
- **中间 Chapter 时间线**：垂直时间轴，每个 Chapter 可展开查看内部 Scene
  - Scene 状态色标：灰色（pending）、蓝色（generating）、绿色（confirmed）
- **右侧 操作区**：
  - "修改蓝图" 按钮 → 弹出 YAML 编辑器
  - "试玩当前进度" 按钮

#### 页面 B：Story Map（现有，改造）
- 从只读升级为**蓝图驱动**的只读图
- 节点数据来源：`ProjectBlueprint.chapters.scenes`，而非实时扫描 `.rpy`
- 新增"跳转至 Scene 生成"的快捷操作

#### 页面 C：Asset Gallery（现有，兼容）
- 资源卡片增加"所属 Scene"标签（如"Scene 1.1 — 初见"）
- 按 Chapter 分组展示，支持折叠

### 5.3 关键组件清单

| 组件名 | 用途 | 前端位置 |
|--------|------|---------|
| `BlueprintCard` | Chat Drawer 内展示 Spec 摘要 | `dashboard/src/components/BlueprintCard.tsx` |
| `ChapterTimeline` | Dashboard 内的章节进度轴 | `dashboard/src/components/ChapterTimeline.tsx` |
| `SceneStatusBadge` | 标识 Scene 的 pending/generating/confirmed 状态 | `dashboard/src/components/SceneStatusBadge.tsx` |
| `ProgressNavigator` | 顶部浮条，显示当前生成进度 | `dashboard/src/components/ProgressNavigator.tsx` |

---

## 6. 当前已有功能与目标功能之间的 Gap 分析

### 6.1 后端 Gap

| 模块 | 已有能力 | 缺失能力 | 影响等级 |
|------|---------|---------|---------|
| `ChatEngine` | 单轮 ReAct，`run_turn()` 直接调工具 | **Planning Phase 缺失**：没有需求收敛 + Spec 生成阶段 | 🔴 高 |
| `ConfirmationState` | Tool 级确认（如候选图） | **Blueprint 级确认**：不支持对整个 Spec 的审批状态机 | 🔴 高 |
| `ToolAdapter` | Schema 转换完整 | 无需改动 | 🟢 无 |
| `generate_script` | 写入 `.rpy`，自动更新 `script.rpy` | **无 Spec 校验**：不检查角色/场景是否越级或越界 | 🟡 中 |
| `ProjectManager` | 创建目录、拷贝模板 | **无 Blueprint 管理**：创建项目时不生成 `.mcp/blueprint.yaml` | 🔴 高 |
| `Asset Pipeline` | 生成背景/角色、rembg、标准化 | 无改动，但需按 Scene 需求触发 | 🟡 中 |
| `BuildManager` | Web 构建完整 | 需支持"增量构建到当前 Chapter" | 🟡 中 |

### 6.2 前端 Gap

| 模块 | 已有能力 | 缺失能力 | 影响等级 |
|------|---------|---------|---------|
| `ChatDrawer` | 消息气泡、tool_start/tool_result 渲染 | **BlueprintCard 渲染**、进度条、快捷按钮 | 🟡 中 |
| `ProjectSelectPage` | 项目列表、新建项目弹窗 | 无需改动 | 🟢 无 |
| `Story Map` | 尚未实现完整图可视化 | 需改为**蓝图驱动**的图 | 🟡 中 |
| `Asset Gallery` | 尚未实现 | 需支持按 Chapter/Scene 分组 | 🟡 中 |
| `Blueprint Overview` | 完全缺失 | 需新增页面 | 🔴 高 |

### 6.3 协议 Gap

| 协议 | 已有能力 | 缺失能力 | 影响等级 |
|------|---------|---------|---------|
| WebSocket `/ws/chat` | `user_message` ↔ `assistant_delta` / `tool_start` / `tool_result` | **`blueprint_draft` 消息类型**、**`awaiting_blueprint_confirmation`** | 🔴 高 |
| REST `/api/projects` | CRUD 项目元数据 | **Blueprint CRUD 端点** | 🟡 中 |

---

## 7. 改造计划

### 7.1 阶段一：Spec 基础设施（预计 3-4 天）

**目标**：让 Spec 成为项目的第一公民，Chat Engine 能识别并生成它。

#### 后端任务
1. **设计 `ProjectBlueprint` Pydantic 模型**（`src/renpy_mcp/models.py` 或新建 `src/renpy_mcp/blueprint/models.py`）
2. **实现 `BlueprintManager`**（`src/renpy_mcp/services/blueprint_manager.py`）
   - `create_default(project_name, template_preset)`
   - `load(project_name)` / `save(project_name, blueprint)`
   - `get_next_pending_scene(project_name)`
   - `validate_script_drift(project_name, script_content)`
3. **改造 `create_project`**：项目创建后自动生成 `.mcp/blueprint.yaml`
4. **新增 Planning Phase 到 `ChatEngine`**
   - 增加 `IntentClassifier`：判断输入是 "planning" / "execution" / "chat"
   - 增加 `Planner`：调用 LLM 生成 blueprint draft（只输出 JSON，不调工具）
   - 新增返回类型 `"awaiting_blueprint_confirmation"`
5. **改造 `generate_script`**：增加读取 blueprint 和校验越级的逻辑（先 warning，稳定后改 error）

#### 前端任务
1. **实现 `BlueprintCard` 组件**：在 Chat Drawer 中渲染角色列表和章节时间线
2. **扩展 WS 消息协议**：前端能识别并渲染 `blueprint_draft` 和 `awaiting_blueprint_confirmation`

**验收标准**：
- Chat Drawer 输入"帮我做一个恋爱小说" → 看到 Agent 提问 → 最终看到 BlueprintCard → 点击"确认" → `.mcp/blueprint.yaml` 被创建

---

### 7.2 阶段二：分段生成与进度锁（预计 3-4 天）

**目标**：让生成流程严格按 Scene/Chapter 推进，每章结束后可试玩。

#### 后端任务
1. **在 `ChatEngine` 中维护 `ProjectProgress`**
   - 记录 `current_chapter_idx` / `current_scene_idx`
   - 每次 `generate_script` 后自动推进指针
2. **强化 `generate_script` 校验**
   - `script_name` 必须匹配 `get_next_pending_scene()`
   - 脚本中的角色 tag 必须在 `cast` 中预定义
   - 越级生成直接返回 error
3. **新增 `generate_next_scene` 工具（可选）**
   - 封装"读取 blueprint → 生成脚本 → 更新进度"的完整流程，降低 LLM 的调用复杂度
4. **改造 Build 触发策略**
   - 每完成一个 Chapter，自动调用 `build_project` + `preview_start`
   - 或在 Chapter 完成时返回给用户一个"构建并试玩"的快捷操作

#### 前端任务
1. **实现 `ChapterTimeline` 和 `SceneStatusBadge`**
2. **Dashboard 新增 `Blueprint Overview` 页面**
3. **Chat Drawer 渲染进度消息**："正在生成 Scene 1.1"、"Chapter 1 完成"

**验收标准**：
- 用户确认 Blueprint 后，Agent 自动生成 Scene 1.1 → 生成对应资源 → Scene 1.2 → Chapter 1 结束后返回试玩链接
- 如果用户说"直接写第三章"，Agent 拒绝并解释需要先完成 Chapter 2

---

### 7.3 阶段三：Dashboard 整合与闭环打磨（预计 3-4 天）

**目标**：Dashboard 成为 Spec 的可视化确认中心和进度驾驶舱。

#### 后端任务
1. **新增 REST API**
   - `GET /api/projects/{name}/blueprint`
   - `POST /api/projects/{name}/blueprint`（支持用户手动编辑后保存）
   - `GET /api/projects/{name}/progress`
2. **Story Map 数据源切换**
   - `script_get_graph` 优先从 blueprint 读取章节结构，`.rpy` 文件作为补充
3. **完善 Spec 级修改的回退逻辑**
   - 用户修改 blueprint 后，自动将受影响的 Scene 状态重置为 `pending`

#### 前端任务
1. **`Blueprint Overview` 页面联调**
2. **Story Map 接入 Blueprint 数据**
3. **Asset Gallery 按 Chapter/Scene 分组**
4. **错误边界和空状态处理**

**验收标准**：
- 用户在 Dashboard `Blueprint Overview` 修改角色名后保存 → 受影响的 Scene 状态变灰 → Chat Drawer 收到系统通知"Blueprint 已更新"
- 从 Story Map 点击任意 Scene 节点，能跳转试玩或查看脚本

---

### 7.4 阶段四：E2E 验证与发布（预计 2-3 天）

**目标**：完整跑通"从零需求到可玩 Demo"的全链路。

#### 验证清单
1. **30 分钟 Demo 压力测试**
   - 非技术用户独立完成：需求输入 → Spec 确认 → 3 Chapter 生成 → 试玩
2. **分段生成边界测试**
   - 验证越级生成被拦截
   - 验证单张图重生成不触发全量重写
3. **Spec 修改传播测试**
   - 修改 blueprint 角色名后，已生成的 Scene 标记为待更新
4. **双端一致性测试**
   - Chat Drawer 中确认的 Spec，Dashboard 中实时同步

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Planning Phase 延迟过高 | 中 | 先用轻量 prompt 跑通，必要时缓存常见题材的预设模板 |
| 用户对 Spec 确认感到繁琐 | 中 | 提供"一键确认默认设定"按钮；允许在生成过程中随时精简 blueprint |
| `generate_script` 校验过严导致误报 | 低 | 第一阶段先 warning 后 error；保留绕过校验的开发者开关 |
| Story Map 与 `.rpy` 内容不同步 | 中 | Story Map 主数据来自 blueprint（结构层），`.rpy` 只填充细节（内容层），天然解耦 |
| 前端开发进度滞后 | 中 | Chat Drawer 的 BlueprintCard 优先做；Dashboard 的 Blueprint Overview 可以先用纯 YAML 编辑器兜底 |

---

## 9. 里程碑重排（基于本计划）

| 时间 | 里程碑 | 关键交付 |
|------|--------|---------|
| **Week 1** | Spec 基础设施 | `BlueprintManager`、`ProjectBlueprint` 模型、Chat Drawer 能展示并确认 Spec |
| **Week 2** | 分段生成闭环 | 按 Scene/Chapter 生成、进度锁、每章后自动构建试玩 |
| **Week 3** | Dashboard 整合 | `Blueprint Overview`、Story Map 蓝图驱动、Asset Gallery 分组 |
| **Week 4** | E2E 验证与发布 | 30 分钟 Demo 测试、文档补齐、内测发布 |

---

*计划书完*
