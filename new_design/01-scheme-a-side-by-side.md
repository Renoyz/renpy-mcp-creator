# 方案 A：左右分屏式 — Chat 与 Dashboard 并列

## 1. 整体布局理念

**"Chat 和 Dashboard 是双主角，谁也不应该被折叠成抽屉。"**

桌面端采用左右固定分屏：左侧是项目驾驶舱（Dashboard），右侧是 AI 对话面板（ChatPanel）。两者始终可见，实时联动。用户在 Chat 中发送"生成第一章"，左侧 Dashboard 的 Chapter 时间线立即出现生成动画。

这是参考了 Claude Artifacts、ChatGPT Canvas、以及 Cursor Composer 的交互模式。

## 2. 桌面端宽屏布局（≥1280px）

```
┌──────────────────────────────────────────────────┬──────────────────────┐
│ ← 返回项目列表    campus_romance    [Build][Play]│  🤖 与 AI 协作创作     │
├──────────────┬─────────────────────────┬─────────┼──────────────────────┤
│              │                         │  ▶ 试玩 │  对话历史            │
│   CHAPTERS   │      主内容区            │  本章   │                      │
│              │                         │         │  ┌─────────────┐     │
│  ▼ Chapter 1 │  ┌───┬────┬──────┬────┐│ [重生成]│  │ Blueprint   │     │
│   🟢 Scene 1 │  │蓝图│脚本│Story │审计││ [修改]  │  │ Card        │     │
│   🟢 Scene 2 │  └───┴────┴──────┴────┘│         │  └─────────────┘     │
│   🔴 Scene 3 │                         │ 资源    │                      │
│              │  （默认显示 Blueprint）   │ 缩略图   │  ┌─────────────┐     │
│  ▶ Chapter 2 │                         │         │  │ Progress    │     │
│   ⏳ Scene 1 │  Cast 角色卡             │         │  │ Card        │     │
│   ⏳ Scene 2 │  ┌───┬───┐               │         │  └─────────────┘     │
│              │  │ 樱 │小林│               │         │                      │
│  ▶ Chapter 3 │  └───┴───┘               │         │  用户：生成第一章     │
│              │                         │         │  AI：正在生成中...    │
│              │  Scenes 网格             │         │                      │
│              │  ┌───┬───┬───┐          │         │  [输入消息...] [发送] │
│              │  │1.1│1.2│1.3│          │         │                      │
│              │  └───┴───┴───┘          │         │                      │
├──────────────┴─────────────────────────┴─────────┴──────────────────────┤
│  视觉健康度 92%  ·  审计状态: 1 个阻塞问题  ·  3 个资源待优化            │
└───────────────────────────────────────────────────────────────────────────┘

宽度占比：左 65%（Dashboard 内部再分三栏：Chapter 20% + 主内容 55% + 右操作 25%），右 35%（ChatPanel 固定 380-420px）
```

## 3. 区域详解

### 3.1 顶部全局栏（横跨左右）
- **左侧**：返回项目列表按钮 ←
- **中间**：当前项目名称（如 `campus_romance`）
- **右侧**：
  - `[Build]` 按钮：构建当前已完成的进度
  - `[Play / Preview]` 按钮：启动试玩

**注意**：顶部栏**不再放置"AI 助手"按钮**，因为 Chat 已经在右侧常驻。

### 3.2 左侧：Chapter 时间线（Chapter Timeline）
这是一个垂直手风琴树：
- 每个 **Chapter** 是一个可展开/折叠的节点，显示标题（如"图书馆相遇"）
- Chapter 下展开 **Scene** 列表，每个 Scene 显示状态色标：
  - `⏳ pending` 灰色
  - `🔄 generating` 蓝色 + 旋转动画
  - `🟢 generated` 绿色（未审计）
  - `✅ confirmed` 深绿色（已通过审计）
  - `🔴 audit_fail` 红色（审计失败）
- 点击 Scene 后，中栏切换到该 Scene 的详情
- Chapter 节点右侧 hover 时出现 `[▶ 试玩本章]` 小按钮

### 3.3 中栏：主内容区（标签页切换）
根据当前选中对象（全局/Chapter/Scene）动态显示标签：

**默认状态（未选中具体 Scene，或选中 Chapter 根节点）**：
- 标签页：`[Blueprint] [Story Map] [Audit Report]`
- **Blueprint 标签**（默认）：展示角色卡（Cast Cards）+ Scene 网格 + 项目基调

**选中某个 Scene 后**：
- 标签页：`[脚本] [资源] [审计]`
- **脚本标签**：内联 Monaco 编辑器，加载该 Scene 对应的 `.rpy` 文件
- **资源标签**：展示该 Scene 引用的所有图片/音频，带缩略图
- **审计标签**：展示该 Scene 的历史审计记录

### 3.4 Dashboard 右栏：快捷操作面板（可收起）
默认宽度约 160px，显示当前选中对象的快捷操作：
- `[▶ 试玩本章]`
- `[重生成背景]`
- `[重生成角色]`
- 资源缩略图列表

**窄屏时**：可收起为一条图标边栏，hover 展开。

### 3.5 右侧：ChatPanel（始终可见）
固定宽度 380-420px，独立区域：
- **顶部**：项目名称 + 清空对话 + 设置按钮
- **中部**：消息流（对话历史），支持多种卡片：
  - `BlueprintCard`：折叠面板展示角色+章节，底部有"确认并生成"按钮
  - `ProgressCard`：进度条+当前生成步骤描述
  - `AuditReportCard`：状态色块+issue折叠列表+决策按钮
  - `ResourceCandidateCard`：2列图片网格+确认/重生成按钮
  - 普通文本消息
- **底部**：输入框 + 发送按钮

## 4. 核心交互流程

### 流程 1：首次进入项目 → 查看并确认 Blueprint
1. 用户从项目列表点击进入 `campus_romance`
2. 左侧 Dashboard 默认展示 Blueprint 标签
3. 右侧 ChatPanel 显示 AI 消息："已为你生成项目蓝图，请确认"
4. 用户阅读左侧 Blueprint（角色、章节结构）
5. 用户在右侧 ChatPanel 点击 `BlueprintCard` 上的"确认并生成"
6. Orchestrator 收到确认，开始 Chapter 1 的生成

### 流程 2：生成中 → 进度感知
1. 用户在右侧 Chat 中发送"开始生成第一章"
2. 右侧 Chat 显示 `ProgressCard`："正在生成 Scene 1.1 — 初见"
3. 左侧 Chapter Timeline 中 Scene 1.1 状态变为 `🔄 generating`
4. Scene 1.1 生成完成后，左侧状态变为 `🟢 generated`，Scene 1.2 变为 `🔄 generating`
5. Chapter 1 全部 Scene 完成后，Orchestrator 自动触发审计
6. 左侧 Chapter 1 右侧出现"审计中..."提示

### 流程 3：审计失败 → 修复闭环
1. 审计完成，右侧 Chat 显示 `AuditReportCard`：红色顶部，"发现 2 个阻塞问题"
2. 用户点击 Card 上的"去 Dashboard 查看详情"
3. 左侧 Dashboard 自动切换到 **Audit Report 标签页**
4. 用户看到 issue 列表，点击某条"跳转脚本"
5. 左侧 Dashboard 切到该 Scene 的"脚本"标签，Monaco 编辑器自动滚动到对应行
6. 用户修改保存后，在右侧 Chat 发送"重新审计 Chapter 1"
7. Auditor Agent 复验，通过后 Scene 全部变 `✅ confirmed`

### 流程 4：试玩某一章
1. 用户在左侧 Chapter Timeline  hover Chapter 1
2. 出现 `[▶ 试玩本章]` 按钮
3. 点击后，顶部全局栏的 Preview 区域显示 iframe，顶部有浮动条："当前预览：Chapter 1"

## 5. 状态变化示例

### 选中不同对象时，中栏标签的变化
| 左侧选中 | 中栏标签 | 默认显示 |
|---------|---------|---------|
| 无（项目根） | `[Blueprint] [Story Map] [Audit Report]` | Blueprint |
| Chapter 1 | `[Blueprint] [Story Map] [Audit Report]` | Blueprint（过滤为 Chapter 1 内容） |
| Scene 1.1 | `[脚本] [资源] [审计]` | 脚本 |
| Scene 1.2 | `[脚本] [资源] [审计]` | 脚本 |

## 6. 优缺点

| 优点 | 缺点 |
|------|------|
| Chat 始终可见，零切换成本，创作流最顺畅 | 压缩了 Dashboard 的可用宽度（从 100% 降到约 65%） |
| 左右实时联动，进度感知极强 | 对 13 寸笔记本屏幕可能略挤 |
| 最符合"AI 生成 + 人工确认"的协作心智模型 | 移动端完全不可用，需要单独设计 |
| Chat 中的重要卡片（Blueprint/ Audit）可以长时间保留在视野中供参考 | 如果用户长时间不聊天，右侧 35% 空间利用率低 |

## 7. 适配建议

- **≥1440px**：左侧 Dashboard 采用完整三栏（Chapter 20% + 主内容 55% + 右操作 25%）
- **1280-1439px**：左侧 Dashboard 右栏收起为图标边栏，主内容区扩大
- **<1280px**：降级为方案 B 或 C 的移动端变体

## 8. 设计 Agent 需重点绘制的页面

1. **默认状态**：用户刚进入项目，左侧 Blueprint 标签 + 右侧 Chat 的 `BlueprintCard`
2. **生成中状态**：左侧 Chapter Timeline 有多个 `🔄 generating` Scene + 右侧 `ProgressCard`
3. **审计失败状态**：左侧 Audit Report 标签展开 + 右侧 `AuditReportCard`
4. **编辑 Scene 状态**：左侧选中 Scene 1.2，中栏显示 Monaco 脚本编辑器 + 右侧 Chat 显示修复建议
5. **窄屏收起状态**：左侧 Dashboard 右栏收起，Chat 区域保持

---

*方案 A 完*
