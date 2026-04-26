# 分步生成 — 具体设计

**日期**: 2026-04-26
**状态**: 待实施
**依赖**: 后端生成流水线已完成（P2-1 拆分），前端需新增交互

---

## 一、现状 vs 目标

```
现状: Freeze → [场景+角色+背景+脚本]一次生成 → Build → Preview
              ↑ 用户无法干预，不满意只能全部重来

目标: Freeze → ①审阅场景 → ②逐个验收角色 → ③逐个验收背景 → ④脚本组装 → Build → Preview
              ↑ 每步可独立审核/重来       ↑ 已确认资产不受后续重试影响
```

---

## 二、UI 布局

新增 `GenerationWorkspace` 页面，顶部步骤指示器 + 主内容区按步骤切换：

```
┌──────────────────────────────────────────────────────┐
│  ← 返回     ① 场景 → ② 角色 → ③ 背景 → ④ 脚本      │
│              ● 当前    ○ 未开始    ✓ 已完成           │
├──────────────────────────────────────────────────────┤
│  步骤 1: 场景大纲审阅                                 │
│  ┌─ 章节场景列表 ──────┐  ┌─ 场景详情 ────────────┐  │
│  │ Ch1 (3 scenes)       │  │ Location / Mood       │  │
│  │  ├ 残夜余烬 ← 选中   │  │ Characters            │  │
│  │  ├ 龙影之下          │  │ Dialogue beats (6)    │  │
│  │  └ 铁与雪            │  │  1. Aldric: "..."     │  │
│  │ Ch2 (3 scenes)       │  └──────────────────────┘  │
│  └──────────────────────┘                             │
│  [确认场景大纲，开始生成角色 →]                         │
├──────────────────────────────────────────────────────┤
│  步骤 2: 角色资产生成    进度: 2/3                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐             │
│  │ Aldric ✓ │ │Seraphina✓│ │ Eldrin   │             │
│  │ [normal] │ │ [normal] │ │ ⏳ 生成中│             │
│  │ [happy]  │ │ [happy]  │ │          │             │
│  │ [sad]    │ │ [sad]    │ │          │             │
│  │ [重试]   │ │ [重试]   │ │          │             │
│  └──────────┘ └──────────┘ └──────────┘             │
│  [确认角色，开始生成背景 →]                             │
├──────────────────────────────────────────────────────┤
│  步骤 3: 背景资产生成    （同步骤2网格布局）             │
├──────────────────────────────────────────────────────┤
│  步骤 4: 脚本预览                                     │
│  ┌─ script ────────────┐ ┌─ 资源清单 ─────────────┐  │
│  │ label prototype_ch1: │ │ Aldric: normal ✓       │  │
│  │   scene bg_ruins     │ │ bg_ruins ✓             │  │
│  │   ...                │ └────────────────────────┘  │
│  └──────────────────────┘                             │
│  [确认脚本并写入 →]                                     │
└──────────────────────────────────────────────────────┘
```

---

## 三、React 组件树

```
GenerationWorkspace (新页面, route: /dashboard/projects/:name/generate)
├── StepIndicator              ← 顶部步骤条
│   └── StepDot (×4)           ← 每个步骤的状态圆点
├── Step1SceneOutline          ← 只读场景列表 + 章节分组
│   ├── ChapterSceneList
│   │   └── SceneCard (×N)
│   └── SceneDetailPanel
│       └── DialogueBeatList
├── Step2CharacterAssets
│   ├── ProgressBar
│   └── CharacterGrid
│       └── CharacterAssetCard (×N)
│           ├── SpritePreview (×3)   ← normal/happy/sad 缩略图
│           ├── RetryButton          ← 调用 character_asset_retry WS
│           └── AcceptBadge          ← 验收状态标记
├── Step3BackgroundAssets
│   └── BackgroundGrid
│       └── BackgroundAssetCard (×N)  ← 同角色卡片结构
└── Step4ScriptAssembly
    ├── ScriptFileTabs
    ├── ScriptPreview           ← <pre> 代码展示
    └── AssetChecklist
```

---

## 四、GenerationState

```typescript
interface GenerationState {
  currentStep: 1 | 2 | 3 | 4;

  sceneOutline: ScenePackagesSnapshot | null;
  sceneConfirmed: boolean;

  characterAssets: Record<string, {
    charId: string;
    status: 'generating' | 'done' | 'failed';
    sprites: { normal: string; happy: string; sad: string };
    accepted: boolean;
  }>;

  backgroundAssets: Record<string, {
    location: string;
    status: 'generating' | 'done' | 'failed';
    image: string;
    accepted: boolean;
  }>;

  scriptFiles: Array<{ name: string; content: string }>;
  scriptConfirmed: boolean;
}
```

---

## 五、WebSocket 消息协议（新增）

```typescript
// 步骤控制
{ type: "generation_step", step: 1|2|3|4, status: "active"|"complete" }

// 角色逐个进度
{ type: "character_asset_progress", character_id, status: "generating"|"done"|"failed" }
{ type: "character_asset_result",  character_id, sprites: {normal, happy, sad} }
{ type: "character_asset_retry",   character_id, hint?: string }

// 背景逐个进度
{ type: "background_asset_progress", location, status: "generating"|"done"|"failed" }
{ type: "background_asset_result",  location, image }
{ type: "background_asset_retry",   location, hint?: string }

// 脚本预览
{ type: "script_preview", files: Array<{name, content}> }
{ type: "script_confirm" }
```

---

## 六、后端改动

| 文件 | 改动 |
|------|------|
| `services/prototype_orchestration.py` | 新增 `GenerationStepController` 类：`start_step(n)`, `retry_character(id)`, `retry_background(loc)` |
| `web/chat_ws.py` | `handle_user_message` 响应步骤控制消息 |
| `services/prototype_generation_service.py` | `generate_character_assets` 每完成一个角色发送 WS 消息 |
| `services/prototype_activation_service.py` | `prototype_manifest.json` 扩展 `generation_step` 字段 |

---

## 七、MVP 裁切

完整实现 5-8 天。MVP（2-3 天）范围：

| 保留 | 裁切 |
|------|------|
| 步骤 1 只读审阅 | 场景增删改 |
| 步骤 2 验收 + 基础重试 | 重试时自定义提示词 |
| 步骤 3 验收 + 基础重试 | — |
| 步骤 4 `<pre>` 代码预览 | Monaco Editor |
| 步骤指示器 | 刷新后恢复 |
| WS 进度消息 | staging/ 持久化 |
