# 分步生成交互设计

## 现状

蓝图确认后，用户点击"生成原型"，场景、角色图、背景图、脚本一次性全部生成。用户只能接受整体结果，出现任何问题必须全部重来。不具备中间干预能力。

## 目标流程

```
确认蓝图
  ↓
─────────────────────────────────────────────────
步骤 1/4 — 场景大纲生成 + 审阅
─────────────────────────────────────────────────
  LLM 生成所有章节的场景大纲（场景结构、对白节拍、情绪弧线）
  → 用户审阅：增删场景、调整对白数量、修改情绪走向
  → 用户确认后进入步骤 2

─────────────────────────────────────────────────
步骤 2/4 — 角色资产生成（逐个）
─────────────────────────────────────────────────
  根据场景大纲中出现的角色列表，逐个生成立绘
  → 每个角色显示 sprites/normalized，用户可单独"重试"或"接受"
  → 所有角色确认后进入步骤 3

─────────────────────────────────────────────────
步骤 3/4 — 背景资产生成（逐个场景）
─────────────────────────────────────────────────
  根据场景大纲中的场景列表，逐个生成背景图
  → 每个场景显示背景图，用户可单独"重试"或"接受"
  → 所有背景确认后进入步骤 4

─────────────────────────────────────────────────
步骤 4/4 — 脚本组装 + 预览
─────────────────────────────────────────────────
  将确认的场景、角色图、背景图组合成 .rpy 脚本
  → 用户预览脚本内容
  → 确认后写入 project/game/，可启动游戏测试
```

## 各步骤详情

### 步骤 1：场景大纲生成

| 维度 | 内容 |
|------|------|
| **输入** | 已确认的 ProjectBrief + ChapterOutline |
| **LLM 调用** | `generate_all_chapter_scenes`（现已有） |
| **输出** | 每章的场景列表：scene_id, title, summary, location, characters_present, dialogue_beats, mood, emotional_arc |
| **用户可操作** | ① 删除/新增场景 ② 调整 dialogue_beats 数量 ③ 修改某个场景的 location/mood ④ 调整场景顺序 |
| **状态** | `pipeline_stage: generating` → 子状态 `scene_outline_draft` |

**前端展示**：
- 左侧：按章节分组的场景卡片列表
- 右侧：选中场景的详情（对白节拍预览、角色列表、情绪标注）
- 底部：确认按钮 → "场景大纲确认，开始生成角色"

### 步骤 2：角色资产生成

| 维度 | 内容 |
|------|------|
| **输入** | 步骤 1 中所有 `characters_present` 的去重列表 + CharacterBible |
| **每个角色生成** | `generate_character_assets`（逐个调用） |
| **输出** | 每个角色 normal、happy、sad 三张 sprite，质量门检查结果 |
| **用户可操作** | ① 对单个角色"重试"（重新生成该角色的所有 sprite）② "接受"单个角色 ③ 调整角色 visual_identity_anchors 后重试 |
| **状态** | 子状态 `character_assets_draft` |

**前端展示**：
- 网格布局，每个角色一个卡片
- 卡片内显示 3 张 sprite（normal/happy/sad）的缩略图
- 每个卡片有"重试"按钮（带 loading 状态）
- 顶部显示进度：已完成 3/5 角色
- 底部：所有角色接受后出现"确认角色，开始生成背景"

**重试机制**：
- 重试只影响该角色，不影响已接受的其他角色
- 重试时可修改生成提示词（如"让发型更夸张一些"）
- 重试后原地替换该角色的 sprite，无需重新下载其他角色

### 步骤 3：背景资产生成

| 维度 | 内容 |
|------|------|
| **输入** | 步骤 1 中所有 `location` 的去重列表 + location_visual_brief |
| **每个场景生成** | `generate_background_assets`（逐个调用） |
| **输出** | 每个 location 一张背景图 |
| **用户可操作** | ① 对单个背景"重试" ② "接受"单个背景 ③ 调整 location_visual_brief 后重试 |
| **状态** | 子状态 `background_assets_draft` |

**前端展示**：
- 类似角色卡片网格，按场景分组
- 每个背景卡片显示缩略图 + 所属场景名称
- 每个卡片有"重试"按钮

### 步骤 4：脚本组装 + 预览

| 维度 | 内容 |
|------|------|
| **输入** | 步骤 1 确认的场景大纲 + 步骤 2 确认的角色 sprite 映射 + 步骤 3 确认的背景图映射 |
| **生成** | `write_script` → 完整的 .rpy 文件 |
| **输出** | 预览用的 .rpy 内容 + 资源文件清单 |
| **用户可操作** | ① 预览脚本内容 ② 手动编辑脚本 ③ 确认生成 |
| **状态** | 子状态 `script_assembled` |

**前端展示**：
- 左侧：脚本文件列表（prototype_ch1.rpy 等）
- 中间：选中文件的代码预览（带语法高亮）
- 右侧：资源清单（已关联的角色图、背景图）
- 底部：确认按钮 → 写入文件系统 → 提示"可启动游戏"

## 中间状态持久化

每个步骤的结果必须持久化，以便用户关闭页面后能继续：

```
project/game/__staging__/
  step1_scene_outline.json    # 步骤 1 结果
  step2_characters/
    char_1/  normal.png / happy.png / sad.png  # 未归一化
    char_2/  ...
  step2_character_status.json  # {char_id: {accepted: bool, sprites: [...]}}
  step3_backgrounds/
    bg_forest.png
    bg_castle.png
  step3_background_status.json # {location: {accepted: bool, file: str}}
```

`prototype_manifest.json` 扩展字段追踪当前步骤：
```json
{
  "generation_step": "character_assets",
  "step1_confirmed": true,
  "step2_confirmed_characters": ["char_1", "char_2"],
  "step3_confirmed_backgrounds": []
}
```

## 恢复逻辑

用户重新打开项目时，根据 `generation_step` 恢复到对应步骤：
- `scene_outline` → 显示步骤 1 界面，已生成的内容可编辑
- `character_assets` → 显示步骤 2 界面，已完成角色灰显 + 勾选
- `background_assets` → 显示步骤 3 界面
- `script_assembled` → 显示步骤 4 预览

## API 变更

新增/修改的 WebSocket 消息类型：

```
# 步骤控制
{type: "generation_start_step", step: "scene_outline|characters|backgrounds|script"}
{type: "generation_step_complete", step: "...", data: {...}}

# 角色资产（逐个）
{type: "character_asset_progress", character_id: "...", status: "generating|done|failed"}
{type: "character_asset_result", character_id: "...", sprites: {...}}
{type: "character_asset_retry", character_id: "...", hint: "..."}

# 背景资产（逐个）
{type: "background_asset_progress", location: "...", status: "generating|done|failed"}
{type: "background_asset_result", location: "...", image: "..."}
{type: "background_asset_retry", location: "...", hint: "..."}

# 脚本预览
{type: "script_preview", files: [{name: "...", content: "..."}]}
{type: "script_confirm"}
```

## 前端路由

在 Dashboard 中新增生成工作区路由：

```
/dashboard/projects/:name/generate/outline      → 步骤 1
/dashboard/projects/:name/generate/characters   → 步骤 2
/dashboard/projects/:name/generate/backgrounds  → 步骤 3
/dashboard/projects/:name/generate/script       → 步骤 4
```

或者用单个页面 + 步骤指示器（推荐）：

```
/dashboard/projects/:name/generate
  → 根据 generation_step 显示对应的步骤面板
  → 顶部步骤条：① 场景 → ② 角色 → ③ 背景 → ④ 脚本
  → 已完成步骤可点击查看，未完成步骤灰显
```

## 实现优先级

1. **Phase 1**：后端拆分 `PrototypeGenerationService` 的子服务，保持现有 API 兼容
2. **Phase 2**：新增分步 WebSocket 消息类型，每个步骤可独立触发
3. **Phase 3**：前端步骤式 UI，逐个角色/背景的重试交互
4. **Phase 4**：中间状态持久化 + 恢复逻辑

Phase 1 与 P2-1（架构拆分）重叠，可以合并执行。
