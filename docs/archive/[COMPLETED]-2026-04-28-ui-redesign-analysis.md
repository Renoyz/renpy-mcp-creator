# Ren'Py MCP Dashboard UI 重构分析报告

**版本**: 1.0  
**日期**: 2026-04-16  
**分析对象**: 当前 Dashboard React 前端（`dashboard/src/`）与 Spec + 双 Agent 新架构的匹配度  

---

## 1. 摘要

当前 Dashboard UI 是为"传统 IDE 式开发工具"设计的：左侧固定导航（项目、Story Map、脚本编辑、资源管理），右侧主内容区展示对应页面，右下角悬浮 Chat Drawer。这种设计假设用户是**主动在多个功能模块间切换的开发者**。

但新的 Spec + 双 Agent 架构彻底改变了用户心智模型：
- 用户不再是"打开代码编辑器写脚本"，而是"确认大纲后看 AI 逐章生成"
- 核心状态不再是"有哪些文件"，而是"当前生成到第几章、审计是否通过"
- Chat Drawer 不再是"辅助查询工具"，而是**整个创作流程的主控台**

**结论：当前 UI 与新架构存在结构性不匹配，必须进行以"进度驾驶舱"为核心的重构。**

---

## 2. 当前 UI 结构回顾

### 2.1 路由与页面

```
/                    → 重定向到 /projects
/projects            → ProjectSelectPage（项目列表）
/projects/:name      → ProjectWorkspacePage（项目工作区）
/story-map           → LegacyIframePage（iframe 嵌入旧页面）
/script-editor       → LegacyIframePage（iframe 嵌入旧页面）
/assets              → LegacyIframePage（iframe 嵌入旧页面）
```

### 2.2 当前导航（AppShell）

侧边栏固定四项：
- **项目** — 回到项目列表
- **Story Map** — iframe 加载故事流程图
- **脚本编辑** — iframe 加载 Monaco 编辑器
- **资源管理** — iframe 加载资源库

顶部栏：项目名 + "AI 助手" 按钮（打开 Chat Drawer）+ 版本号

### 2.3 当前项目工作区（ProjectWorkspacePage）

```
┌─ 项目名称 + 路径 ─┐
│ [Build] [Preview] │
│ 构建状态提示       │
├───────────────────┤
│ [Story Map]  [脚本编辑]  [资源管理] │
│ （三个入口卡片）   │
└───────────────────┘
```

### 2.4 当前 ChatDrawer

支持的消息类型：`user`, `assistant`, `tool_start`, `tool_result`, `error`
确认面板：文字提示 + candidates 网格 + 确认/取消按钮

---

## 3. 不匹配分析：从用户使用场景出发

### 场景 A：创作者首次进入项目 — "我的大纲在哪？"

**用户预期**：
> "我刚刚在 Chat Drawer 里确认了一个 Blueprint，说要做 3 章校园恋爱小说。现在我想看看这个大纲长什么样，确认 AI 没有理解错。"

**当前 UI 的问题**：
- ProjectWorkspacePage 完全没有 Blueprint 的展示区域。
- 侧边栏没有"大纲"或"蓝图"入口。
- 用户只能回到 Chat Drawer 向上滚动看历史消息，但历史消息是文本气泡，不是结构化的可编辑大纲。

**设计缺陷**：
> **新架构的核心产出物（ProjectBlueprint）在 UI 中没有任何一席之地。**

---

### 场景 B：生成过程中 — "现在生成到哪了？"

**用户预期**：
> "我让 AI 生成第一章。过了 30 秒，我想知道是还在写 Scene 1.1，还是已经写到 Scene 1.2 了，或者是不是卡住了。"

**当前 UI 的问题**：
- ProjectWorkspacePage 没有任何进度指示器。
- 用户只能看 Chat Drawer 里的 tool_start/tool_result 消息来推测进度，但这些消息是零散的、技术性的（如 `generate_script` 成功），不是面向用户的进度叙事（"Scene 1.1 已完成，正在生成背景图..."）。
- 更没有审计状态的展示（"正在审计 Chapter 1..." 完全不可见）。

**设计缺陷**：
> **UI 把创作流程当成了"黑盒"，用户只能盯着 Chat Drawer 的日志流猜测状态。**

---

### 场景 C：审计失败后 — "问题出在哪？我该怎么改？"

**用户预期**：
> "系统提示第一章审计没通过，说有角色设定冲突。我想快速定位到具体文件和行号，看看是什么问题。"

**当前 UI 的问题**：
- ChatDrawer 不支持 `audit_completed` 消息类型的渲染（当前代码中完全没有对应的 `if` 分支）。
- 即使通过 WebSocket 收到了审计报告，也只会显示为一段普通 assistant 文本，无法展开 issue 详情、无法跳转到具体位置。
- Dashboard 中没有 Audit Report 页面，用户无法在一个集中的地方审阅所有问题。

**设计缺陷**：
> **双 Agent 架构中的关键闸口（审计）在 UI 中没有专属的信息呈现层。**

---

### 场景 D：生成完成后试玩 — "我生成的游戏在哪？"

**用户预期**：
> "第一章写完了，我想立刻试玩一下这一章的效果。"

**当前 UI 的问题**：
- 虽然有 Build 和 Preview 按钮，但它们是与项目绑定的全局操作，不是与 Chapter 绑定的。
- 用户不知道当前 Preview 是"全游戏"还是"只有第一章"。
- 如果只想试玩 Scene 1.1 的某个分支，没有快速入口。

**设计缺陷**：
> **试玩入口与生成进度（Chapter/Scene）是脱节的。**

---

### 场景 E：从 Story Map 跳转到脚本编辑 — "为什么我在两个页面间来回切？"

**用户预期**：
> "我在 Story Map 里看到 Chapter 2 的一个分支节点，想直接修改这个节点对应的台词。"

**当前 UI 的问题**：
- Story Map 和 Script Editor 都是 `LegacyIframePage`，各自在一个独立的 iframe 中运行。
- 两者之间没有联动：点击 Story Map 节点不会自动打开 Script Editor 并定位到对应 label。
- 导航切换是全页面刷新式的体验（从 /story-map 切到 /script-editor）。

**设计缺陷**：
> **iframe 架构导致了严重的功能割裂，不适合需要高频联动的创作-审阅 workflow。**

---

### 场景 F：资源确认 — "这是第几章用的图？"

**用户预期**：
> "我在资源管理页看到一张背景图，想知道它是哪一章、哪个 Scene 用的。"

**当前 UI 的问题**：
- 资源管理是 iframe 页面，它只能按文件类型（images/audio）展示资源，不知道资源的"语义归属"。
- 没有"按 Chapter/Scene 分组"的视图。

**设计缺陷**：
> **资源展示是纯文件系统的视角，而不是创作流程的视角。**

---

## 4. 核心问题归纳

| 问题编号 | 问题描述 | 影响的用户场景 | 严重程度 |
|---------|---------|---------------|---------|
| **P1** | 缺少 Blueprint 展示与编辑入口 | 场景 A | 🔴 致命 |
| **P2** | 缺少创作进度与审计状态的可视化 | 场景 B、C、D | 🔴 致命 |
| **P3** | ChatDrawer 不支持新消息类型（blueprint/audit/fix） | 场景 A、B、C | 🔴 致命 |
| **P4** | Story Map / Script Editor / Assets 以 iframe 割裂存在 | 场景 E、F | 🟡 高 |
| **P5** | 导航结构以"功能模块"为中心，而非"创作流程"为中心 | 全部场景 | 🟡 高 |
| **P6** | ProjectWorkspacePage 内容单薄，没有项目总览价值 | 场景 A、B | 🟡 高 |

---

## 5. 重构方向：从"功能模块导航"转向"进度驾驶舱"

### 5.1 新的用户心智模型

在新架构下，用户使用 Dashboard 的核心目的不是"打开某个工具"，而是：
1. **查看** 当前项目的大纲和进度
2. **确认** AI 生成的内容是否符合预期
3. **审查** 审计报告并决定下一步
4. **微调** 具体 Scene 的脚本或资源
5. **试玩** 当前已完成的 Chapter

因此，Dashboard 应该重新设计为一个**"创作进度驾驶舱"**，而不是一个"工具箱"。

### 5.2 新的信息架构

```
项目列表（/projects）
    ↓ 选择一个项目
项目驾驶舱（/projects/:name） ← 新的核心页面
    ├── 顶部：项目标题 + 当前 Chapter 进度条 + 全局操作（Build / Preview）
    ├── 左侧：Chapter 时间线 + Scene 列表
    ├── 中间主区域：根据左侧选中项动态切换
    │       ├── Blueprint 视图（默认）
    │       ├── Scene 详情（脚本 + 资源）
    │       ├── Audit Report 视图
    │       └── Story Map 视图
    └── 右侧边栏（可选）：资源快速预览 / 属性面板
    
Chat Drawer（始终可唤起）
    ├── 支持 BlueprintCard 渲染
    ├── 支持进度消息渲染（"生成 Scene 1.1 中..."）
    ├── 支持 AuditReportCard 渲染
    └── 支持资源候选图确认
```

### 5.3 关键修改点详解

#### 修改 1：ProjectWorkspacePage 升级为"项目驾驶舱"

**当前结构**：简单的标题 + Build/Preview + 三个入口卡片
**目标结构**：

```
┌─────────────────────────────────────────────────────────────────┐
│  campus_romance                          [Build] [Preview]      │
│  进度: Chapter 1 / 3  ━━━━━━━━░░░░░░░░  33%                    │
├──────────┬──────────────────────────────────────┬───────────────┤
│ Chapter  │                                      │               │
│ 时间线   │         主内容区（默认 Blueprint）    │   右侧边栏    │
│          │                                      │   （资源/     │
│ ▼ Ch 1   │  ┌─ Cast ─┐  ┌─ Scenes ─┐           │    属性）     │
│   ✅ 1.1 │  │ 樱      │  │ Scene 1.1 │           │               │
│   🔄 1.2 │  │ 小林    │  │ Scene 1.2 │           │               │
│   ⏳ 1.3 │  └─────────┘  └───────────┘           │               │
│          │                                      │               │
│ Ch 2     │  [修改 Blueprint]                    │               │
│ Ch 3     │                                      │               │
├──────────┴──────────────────────────────────────┴───────────────┤
│  底部状态栏: 最后审计: 通过 ✅ | 视觉健康度: 92% | 3 张图待优化 │
└─────────────────────────────────────────────────────────────────┘
```

**修改理由**：
- 创作者进入项目后的第一需求是"看整体进度"，而不是"打开编辑器"。
- Blueprint 和 Chapter 时间线放在最显眼的位置，符合"大纲优先"的 Spec 模式理念。
- 底部状态栏提供了一目了然的审计和资源健康度摘要。

#### 修改 2：左侧导航改为"Chapter 时间线"，取代固定功能模块导航

**当前结构**：侧边栏固定为"项目、Story Map、脚本编辑、资源管理"
**目标结构**：
- 当用户在项目驾驶舱内时，左侧边栏显示该项目的 **Chapter 树**：
  - 每个 Chapter 可展开/折叠
  - 每个 Scene 显示状态色标（pending / generating / generated / confirmed / audit_fail）
  - 点击 Scene 后，主内容区显示该 Scene 的脚本和资源
- 全局导航（返回项目列表）保留，但收缩为顶部的一个返回按钮。

**修改理由**：
- 创作者在项目内的移动方式不再是"我想打开编辑器"，而是"我想查看/修改第 2 章第 3 个 Scene"。
- Scene 状态色标让创作进度可视化，一眼就能知道哪里还没完成、哪里审计失败了。
- 将导航与内容深度融合，减少页面跳转。

#### 修改 3：主内容区采用"标签页"动态切换，而非 iframe 全页跳转

**当前结构**：Story Map / Script Editor / Assets 各是一个路由页面，用 iframe 加载
**目标结构**：
- 当用户从 Chapter 时间线选中一个 Scene 时，主内容区显示该 Scene 的详情页：
  - **标签 1：脚本** — 内联 Monaco 编辑器（不再用 iframe）
  - **标签 2：资源** — 该 Scene 引用的背景和角色图
  - **标签 3：审计** — 该 Scene 最近一次审计结果
- 当用户不选中具体 Scene（或选中 Chapter 根节点）时，主内容区显示：
  - **标签 1：Blueprint** — 当前 Chapter 或全局的蓝图摘要
  - **标签 2：Story Map** — 只读的 React Flow 图（不再是 iframe）
  - **标签 3：Audit Report** — 当前 Chapter 的审计报告

**修改理由**：
- iframe 导致了无法逾越的跨页面通信壁垒。要实现在 Story Map 点击节点后自动跳转到对应 Scene 的脚本编辑，必须是同一个 React 应用内的路由/状态切换。
- 标签页让用户在同一屏幕内快速切换视角，而不是在不同页面间等待加载。

#### 修改 4：ChatDrawer 升级为"流程控制中心"

**当前结构**：只支持文本消息气泡 + tool 状态 + 简单确认面板
**目标结构**：新增以下消息卡片类型：

1. **BlueprintCard**
   - 展示角色列表（头像+名称+情绪数）
   - 展示 Chapter 时间线（多少个 Scene、有无分支）
   - 底部按钮："确认并生成" / "修改设定"

2. **ProgressCard**
   - 展示当前生成进度："正在生成 Scene 1.2 — 社团教室背景"
   - 进度条 + 预计剩余时间
   - 支持取消当前生成

3. **AuditReportCard**
   - 顶部状态色块（绿/黄/红）
   - 按维度折叠展示 issue
   - 底部按钮："查看详情"（打开 Dashboard Audit Report 页）、"应用修复"、"忽略警告"

4. **ResourceCandidateCard**
   - 2 列网格展示候选图
   - 每张图下方有"确认" / "重生成"按钮

**修改理由**：
- Chat Drawer 是统一对话引擎在所有前端中的核心皮肤。如果它不支持 Spec 和审计的消息类型，那么后端再强大的双 Agent 架构也无法被用户感知。
- 卡片化设计让复杂信息结构化，减少用户阅读长文本的认知负担。

#### 修改 5：新增 Audit Report 页面

**当前结构**：不存在
**目标结构**：
- 作为项目驾驶舱主内容区的一个常驻标签页
- 页面顶部显示最近一次审计的总体状态
- 按五维审计的维度分组展示 issue 卡片
- 每个 issue 卡片支持：
  - 一键跳转 Script Editor 对应行号
  - 一键请求重生成关联资源
  - 手动标记为"已修复"或"忽略"

**修改理由**：
- 审计是双 Agent 架构的核心差异化能力。没有 Audit Report 页面，Auditor Agent 的输出就只能埋没在 Chat Drawer 的消息流中，无法被系统性地审阅和处理。

#### 修改 6：Build/Preview 与 Chapter 进度绑定

**当前结构**：Build 和 Preview 是全局按钮，与具体生成进度无关
**目标结构**：
- **全局 Build 按钮**变为"构建当前已完成进度"，hover 时提示"将构建 Chapter 1-2（Chapter 3 尚未确认）"。
- 每个 Chapter 节点右侧增加"试玩本章"按钮，允许用户只试玩当前已确认的 Chapter。
- Preview 页面（iframe 中的游戏）顶部增加浮动条："当前预览包含 Chapter 1-2（3 个 Scene）"。

**修改理由**：
- 创作者的核心反馈循环是"生成一章 → 试玩一章 → 调整 → 继续下一章"。Build/Preview 必须嵌入这个循环，而不是作为一个孤立的全局操作存在。

---

## 6. 从用户使用角度的收益总结

| 用户痛点（当前 UI） | 重构后体验 |
|-------------------|-----------|
| "大纲在哪里？我在 Chat Drawer 里翻历史消息找 Blueprint。" | Dashboard 主页面默认展示 Blueprint，结构化、可折叠、可编辑。 |
| "AI 生成到哪里了？我是不是卡住了？" | Chapter 时间线实时显示每个 Scene 的状态，generating 状态的 Scene 有旋转动画。 |
| "审计说有 3 个问题，但我只记得其中 1 个。" | Audit Report 页面集中展示所有 issue，支持按维度筛选，支持一键跳转修复。 |
| "我想改 Scene 2 的一句台词，但从 Story Map 切到 Script Editor 找了半天。" | 点击 Chapter 时间线的 Scene 2，主内容区直接显示脚本标签，自动定位到该 label。 |
| "这张背景图是哪一章用的？" | 资源展示按 Scene 分组，每张图都有"被引用处"标签。 |
| "我只想看第一章的效果，但 Preview 必须从开头玩。" | Chapter 节点旁有"试玩本章"按钮，Preview 也可以从指定 Chapter 开始。 |

---

## 7. 实施优先级

### P0（与 Spec 模式基础架构同期实施，Week 1-2）
1. **重构 ProjectWorkspacePage 为项目驾驶舱骨架**
   - 增加 ChapterTimeline 侧边栏占位
   - 增加主内容区标签页占位（Blueprint / Scene / Audit）
2. **ChatDrawer 支持 BlueprintCard 和 ProgressCard**
   - 新增 `blueprint_draft`、`audit_started`、`audit_completed` 的消息类型处理分支

### P1（与双 Agent 硬分离同期实施，Week 2-3）
3. **实现 AuditReportCard 和 Audit Report 页面**
   - 支持 `AuditReport` 的 JSON 渲染
   - 支持 issue 到 Script Editor 的跳转
4. **将 Story Map 从 iframe 改为内联组件**
   - 使用 `@xyflow/react` 实现只读故事图
   - 点击节点可跳转到对应 Scene 详情

### P2（Dashboard 整合阶段，Week 3-4）
5. **Script Editor 内联化**
   - 用 Monaco Editor 替换 iframe
   - 支持外部传入 `file_path` 和 `line_number` 实现自动定位
6. **资源管理内联化**
   - 按 Chapter/Scene 分组展示资源
   - 支持从 Scene 详情页直接重生成某张图

### P3（体验打磨，Week 4+）
7. **Build/Preview 与 Chapter 绑定**
   - 支持"试玩指定 Chapter"
   - Preview 顶部浮动进度提示条
8. **响应式优化**
   - 三栏布局在窄屏幕下自动折叠右侧边栏

---

## 8. 不修改的保留项

以下当前设计在新架构下仍然适用，无需改动：

- **ProjectSelectPage 的项目列表页**：创建项目 → 进入项目驾驶舱的流程不变。
- **AppShell 的整体布局框架**（侧边栏 + 顶部栏 + 主内容区）：只需替换侧边栏内容和主内容区组件。
- **ChatDrawer 的 WebSocket 连接机制**：只需扩展消息解析逻辑。
- **Dark/Light 主题切换和 Tailwind 配置**：保持现有样式系统。

---

## 9. 关键决策记录（ADR）

### ADR-UI-1：为什么 ProjectWorkspacePage 必须从"三个入口卡片"改为"Chapter 时间线 + 标签页"？

- **原因 1**：新架构的核心交互单位是 Chapter/Scene，而不是"编辑器"或"资源库"。
- **原因 2**：创作者需要持续的进度感知，而不是每次手动决定打开哪个工具。
- **原因 3**：审计状态（pass/fail）必须绑定到具体的 Chapter/Scene 上，全局页面无法承载这种粒度。

### ADR-UI-2：为什么必须逐步废弃 LegacyIframePage？

- **原因 1**：iframe 与外层 React 应用处于不同的 JS 运行环境，无法共享路由状态、无法做节点到代码的联动跳转。
- **原因 2**：iframe 加载有额外网络延迟和视觉闪烁，不适合需要高频切换的创作 workflow。
- **原因 3**：内联组件（React Flow + Monaco）可以提供更一致的交互体验和更细粒度的错误边界。

### ADR-UI-3：为什么 Audit Report 需要独立的 Dashboard 页面，而不仅仅是 ChatDrawer 卡片？

- **原因 1**：审计报告通常包含多个 issue、涉及多个文件，ChatDrawer 的窄屏空间无法容纳复杂信息的审阅。
- **原因 2**：Dashboard 页面支持多列布局（issue 列表 + 脚本预览 + 资源缩略图），适合深度编辑。
- **原因 3**：ChatDrawer 适合快速决策（"是否忽略警告？"），Dashboard 适合深度处理（"逐条查看并修复"）。

---

## 10. 下一步行动清单

| 优先级 | 任务 | 涉及文件 | 依赖 |
|--------|------|---------|------|
| P0 | 设计 `ChapterTimeline` 组件 | `dashboard/src/components/ChapterTimeline.tsx` | `ProjectBlueprint` Schema 定稿 |
| P0 | 重构 `ProjectWorkspacePage` 为三栏驾驶舱布局 | `dashboard/src/pages/ProjectWorkspacePage.tsx` | 无 |
| P0 | ChatDrawer 扩展消息类型解析 | `dashboard/src/components/ChatDrawer.tsx` | WebSocket 协议扩展 |
| P1 | 实现 `BlueprintCard` 组件 | `dashboard/src/components/BlueprintCard.tsx` | `ProjectBlueprint` Schema 定稿 |
| P1 | 实现 `AuditReportCard` 组件 | `dashboard/src/components/AuditReportCard.tsx` | `AuditReport` Schema 定稿 |
| P1 | 新增 `AuditReportPage` | `dashboard/src/pages/AuditReportPage.tsx` | `AuditReport` Schema 定稿 |
| P2 | Story Map 内联化（React Flow） | `dashboard/src/components/StoryMapGraph.tsx` | 项目索引数据接口 |
| P2 | Script Editor 内联化（Monaco） | `dashboard/src/components/ScriptEditor.tsx` | 文件读写 API |
| P2 | Asset Gallery 内联化 | `dashboard/src/components/AssetGallery.tsx` | 文件列表 API |

---

*分析报告完*
