# 视觉小说工程中间件目标差距分析

更新日期：2026-04-27

## 目标

如果项目的核心诉求是“为二次精细化开发提供基础”，它不应该定位为一次性的 AI 文本生成器，而应该定位为：

```text
自然语言需求
  -> 结构化游戏中间态
  -> 可校验的剧情/资产/状态工程
  -> 确定性 Ren'Py 文件树
  -> 人类可继续精修和增量维护的游戏项目
```

换句话说，这个项目真正有价值的方向是成为一个“协议转换与工程组装系统”。AI 负责把模糊需求转化为结构化内容，系统负责把结构化内容确定性地编译、校验、组装成可运行、可维护、可二次开发的 Ren'Py 工程。

目标能力应至少包含四层：

1. **确定性的中间态表示（IR）**
   - AI 不直接输出自由格式 `.rpy`。
   - AI 先输出严格 JSON/YAML：角色、章节、场景、台词、选择、变量、条件、资产需求、结局。
   - 系统将 IR 编译为 Ren'Py `label`、`menu`、`jump`、`if/elif/else`、`image`、`define` 等语句。
   - IR 可以被校验、编辑、diff、合并，并作为项目的权威源。

2. **标准化资产管线与本地协议钩子**
   - 所有背景、立绘、表情、CG、BGM、语音、音效都先进入统一资产需求清单。
   - 本地 ComfyUI、Flux、Stable Diffusion、GPT-SoVITS、Piper、BGM 生成器等可以按标准协议接入。
   - 系统自动完成资产命名、目录归位、Ren'Py 声明、Gallery/Ending Gallery 引用。

3. **变量与剧情状态机解耦**
   - 好感度、道具、金币、路线 flag、结局解锁等不应散落在台词脚本里。
   - 系统应生成独立状态声明文件，例如 `init_variables.rpy`。
   - Choice 的条件、效果、跳转目标应结构化表达，并可做可达性和因果校验。

4. **增量生成的幂等性与无损合并**
   - 生成器不能覆盖用户已经精修的代码。
   - AI 生成区、用户编辑区、系统模板区需要明确 ownership。
   - 后续生成支线、章节、CG、语音时，应只追加或更新受控区域。
   - 最终形成“AI 打灰，人类精装修”的协作模式。

## 现状

当前项目已经明显超过“玩具级单次文本生成器”，核心流水线已经具备实用雏形：

```text
创建项目
  -> AI intake
  -> brief 确认
  -> outline 确认
  -> blueprint freeze
  -> scene generation
  -> asset generation / upload / accept / confirm
  -> script preview
  -> commit / rollback
  -> build / preview
```

代码层面已经具备几类关键基础。

### 1. 已有结构化模型基础

项目已经有 `ProjectBlueprint`、`ScenePackagesSnapshot`、`ScenePackageScene`、`DialogueBeat`、`FlowNode`、`FlowEdge` 等模型。这说明当前系统并不是纯 prompt 到 `.rpy` 的直出模式，而是已经存在结构化中间数据。

现有模型可以表达：

- 项目标题、类型、世界观、主题、受众、艺术风格。
- 角色名称、身份、性格、外观。
- 章节、场景、场景顺序。
- 场景标题、摘要、地点、mood、登场角色。
- 台词 beat。
- 入口 label 和下一个 scene id。
- 初步的节点和边模型。

### 2. 已有确定性脚本渲染服务

`ScriptRenderService` 已经承担了从结构化场景数据生成 `.rpy` 的职责。它会：

- 生成角色 `define`。
- 生成背景和立绘 `image` 声明。
- 生成 stage transform。
- 输出 `label`。
- 输出 `scene`、`show`、台词、`jump`、`return`。
- 使用 staging 文件而不是直接覆盖正式脚本。

这已经是“编译器化”的雏形，只是当前仍更接近字符串模板渲染，还不是完整 AST/compiler pipeline。

### 3. 已有分步生成与资产确认状态机

`StepwiseGenerationService` 已经实现了项目级 generation state：

- `scene_outline_draft`
- `scene_outline_confirmed`
- `character_assets_draft`
- `character_assets_confirmed`
- `background_assets_draft`
- `background_assets_confirmed`
- `script_preview`
- `committed`
- `failed`

这套机制已经支持：

- 资产 slot。
- 用户上传。
- AI 生成。
- accept/confirm。
- script preview。
- commit。
- rollback。

这对生产级工具非常关键，因为它避免了“一键生成失败后项目处于半损坏状态”的问题。

### 4. 已有 Game Shell 前置实现迹象

当前工作区已经出现 Game Shell 相关改动，包括：

- `GameShellConfig`
- `GameShellGalleryItem`
- `GameShellEndingItem`
- `GameShellRenderService`
- `/api/projects/{project_name}/game-shell`
- Gallery / Ending Gallery / Credits / Extras 的 additive `.rpy` 输出
- Dashboard 侧 `GameShellWorkspaceView`

这说明项目已经开始从“生成一段剧情”走向“生成一个更完整的 Ren'Py 游戏壳”。

### 5. 已有部分幂等和事务安全基础

当前系统已经在几个关键点上做得比较好：

- 脚本先写入 staging，再 commit。
- commit 失败会恢复脚本、index、manifest、资产。
- 多章节脚本可拆分为多个 prototype 文件。
- Game Shell 倾向输出 additive 文件，而不是直接覆盖 `screens.rpy`。
- 项目路径和资产路径开始强调 project-relative，不暴露绝对路径。

这些是从原型工具走向生产力工具的正确方向。

## 差距

当前项目的主要差距不是“还不会生成更多文本”，而是缺少几层工程边界。没有这些边界，项目容易停留在“可用原型生成器”，而难以成为“可维护游戏工程中间件”。

### 1. IR 还不是权威源

当前已有 `ProjectBlueprint` 和 `ScenePackagesSnapshot`，但它们还不是完整的游戏 IR。

主要问题：

- `ScenePackagesSnapshot` 更像线性场景包，不是完整剧情拓扑图。
- `DialogueBeat` 缺少 expression、voice、condition、effect、branch metadata。
- `FlowNode` / `FlowEdge` 是雏形，但没有成为脚本生成的核心输入。
- 没有统一 `GameIR` 版本号、schema migration、兼容策略。
- 没有 IR 级 validator。
- `.rpy` 仍然容易成为事实源，而不是派生产物。

目标状态应是：

```text
GameIR.json
  -> validate
  -> normalize
  -> compile
  -> generated Ren'Py files
```

而不是：

```text
LLM output / scene package
  -> 拼接字符串
  -> script.rpy / prototype_x.rpy
```

### 2. 脚本生成器还不是完整编译器

当前 `ScriptRenderService` 已经抽离出来，但它仍主要是“一次性文本渲染器”。

缺失能力：

- 没有 Ren'Py AST 层。
- 没有 statement-level ownership。
- 没有 compiler diagnostics。
- 没有 label/jump/menu 可达性校验。
- 没有条件表达式编译。
- 没有变量声明和 effect 编译。
- 没有输出前语法结构校验。

这意味着后续加入分支、变量、结局时，如果继续在字符串拼接上扩展，复杂度会迅速上升。

### 3. 资产协议还没有独立成清单

当前资产 slot 已经可用，但还没有成为可外接的标准协议。

现状偏向：

```text
生成流程内部需要什么资产
  -> 生成/上传/接受
  -> 写入 state
  -> script renderer 引用
```

目标应是：

```text
asset_requirements.json
  -> local provider consumes
  -> candidate assets
  -> validation
  -> accepted assets
  -> runtime registry
```

缺失能力：

- 缺少统一 `AssetRequirement` 模型。
- 缺少 provider hook 协议。
- 缺少对表情变体、CG、voice、BGM、SFX 的统一建模。
- 缺少资产状态从 required/candidate/accepted/rejected/deprecated 的完整生命周期。
- 缺少资产 manifest 与 `.rpy image/audio/voice` 声明之间的双向一致性校验。

### 4. 表情、mood、音乐、语音还没有闭环

项目已有 `mood` 和 `expression` 字段雏形，但闭环不完整：

- `ScenePackageScene.mood` 存在，但没有稳定映射到 BGM/SFX。
- `SpritePlanItem.expression` 存在，但当前脚本渲染基本固定为 `_neutral`。
- 角色表情变体还没有进入 IR、资产需求、脚本显示的一体化链路。
- 语音没有进入 dialogue beat 生命周期。

目标状态应是：

```text
DialogueBeat.expression
  -> AssetRequirement(sprite expression)
  -> image char_happy
  -> show char_happy

SceneNode.mood
  -> MusicRequirement
  -> play music mood_track

DialogueBeat.voice
  -> VoiceRequirement
  -> voice "audio/voice/..."
```

### 5. 游戏内变量与状态机基本缺位

当前系统有“生成流程状态机”，但还没有完整“游戏剧情状态机”。

缺失能力：

- 变量声明模型，例如 `affection`, `trust`, `has_key`, `route_flag`。
- `init_variables.rpy` 确定性生成。
- Choice condition。
- Choice effect。
- Ending unlock condition。
- Route reachability simulation。
- 变量读写冲突校验。

当前更适合线性原型；如果要生成可二次开发的分支 VN，这一层必须补上。

### 6. 分支、结局、CG 还偏展示壳，不是剧情拓扑

Game Shell 中出现 Gallery 和 Ending Gallery 是正确方向，但当前阶段更像 presentation layer。

仍缺少：

- ChoiceNode。
- BranchEdge。
- EndingNode。
- CG event。
- Persistent unlock。
- Replay target。
- Route graph。
- Ending condition。

也就是说，当前可以先让生成物“看起来像完整游戏”，但距离“结构化生成多分支游戏”还有一层剧情拓扑建模。

### 7. 增量生成还不是无损合并

当前已有 staging/commit/rollback，这是很强的基础。但无损增量生成还需要更细粒度的 ownership。

缺失能力：

- AI-generated 文件与 user-authored 文件边界。
- label-level ownership marker。
- scene-level frozen 状态。
- generated block 的稳定 id。
- 用户修改检测。
- IR diff 到 `.rpy` diff。
- append-only 支线生成。
- merge conflict 报告。

目前更接近：

```text
安全替换一批生成物
```

目标应是：

```text
只更新 AI 拥有的区域，保留人类精修区域
```

### 8. Dashboard 还没有成为 IR 编辑器

Dashboard 当前已经可支撑生成流程、资产确认、Game Shell 编辑。但如果目标是二次精修基础，它最终需要从“流程控制台”升级为“结构化工程编辑器”。

缺失能力：

- Chapter/Scene/Dialogue 的结构化编辑。
- Choice/Branch 编辑。
- Variable/State 编辑。
- Asset manifest 编辑。
- Gallery/Ending 与 IR 节点关联。
- 修改后重新编译。
- 编译前错误提示。

当前 UI 已经适合原型生成，但还没有完全服务于“结构化工程维护”。

## 计划

建议不要一次性重写系统，而是沿着当前已有流水线逐层加固。优先级应服务于“二次精细化开发基础”，而不是短期堆更多 AI 生成能力。

### 阶段 1：定义 GameIR v1

目标：建立项目的权威中间态。

建议新增或演进：

- `GameIR`
- `CharacterDef`
- `AssetRequirement`
- `VariableDef`
- `SceneNode`
- `DialogueNode`
- `ChoiceNode`
- `ConditionExpr`
- `EffectExpr`
- `EndingNode`
- `RouteGraph`

关键原则：

- 先覆盖当前线性原型，不强行一次支持复杂分支。
- `ScenePackagesSnapshot` 可以先映射到 `GameIR`，不必立即删除。
- 所有字段必须有 schema version。
- 所有路径必须保持 project-relative。

验收标准：

- 当前线性 prototype 可以完整表达为 GameIR。
- GameIR 可以序列化到 `meta/game_ir.json`。
- 不依赖 `.rpy` 反推核心剧情结构。

### 阶段 2：把 ScriptRenderService 升级为编译器

目标：从“字符串渲染服务”升级为“确定性 Ren'Py compiler”。

建议拆分：

- `game_ir_validator.py`
- `renpy_ast.py`
- `renpy_compiler.py`
- `renpy_writer.py`

第一版 compiler 只需要覆盖：

- `define`
- `image`
- `label`
- `scene`
- `show`
- dialogue
- `jump`
- `return`

第二版再加入：

- `menu`
- `$ variable += 1`
- `if/elif/else`
- `play music`
- `voice`
- persistent unlock

验收标准：

- 现有 prototype 输出行为保持兼容。
- 编译前能报告缺失 label、重复 id、非法路径。
- 编译输出不直接覆盖用户文件，只写 generated 区域。

### 阶段 3：建立 Asset Manifest Protocol

目标：把资产从“流程内部状态”提升为“外部工具可消费协议”。

建议新增：

```text
meta/asset_requirements.json
meta/asset_manifest.json
```

资产类型至少覆盖：

- background
- sprite
- sprite_expression
- cg
- bgm
- sfx
- voice
- font

状态至少覆盖：

- required
- generating
- candidate
- accepted
- rejected
- deprecated

同时定义本地 provider hook：

```text
GET asset requirements
POST generated candidate
POST accept/reject
POST regenerate
```

验收标准：

- ComfyUI/Flux 可以只看 asset requirements 就知道要生成什么。
- 用户上传和 AI 生成走同一资产生命周期。
- accepted asset 自动进入 `.rpy` 声明、Gallery、预览。

### 阶段 4：补齐变量与分支 DSL

目标：让项目能生成可维护的多分支 VN，而不是只能线性播放。

建议新增：

- `VariableDef`
- `ChoiceNode`
- `ConditionExpr`
- `EffectExpr`
- `EndingCondition`

输出文件建议：

```text
game/generated/init_variables.rpy
game/generated/story_routes.rpy
```

第一版只支持简单表达式：

- bool flag
- int counter
- string route
- `==`, `!=`, `>=`, `<=`
- `set`
- `increment`
- `decrement`

验收标准：

- 一个 choice 可以改变变量并跳转不同 label。
- 一个 ending 可以按变量条件解锁。
- 系统能检测不可达 ending。

### 阶段 5：建立增量生成 ownership 模型

目标：防止 AI 后续生成覆盖人工精修成果。

建议文件边界：

```text
game/generated/
  ai 可重写

game/custom/
  用户维护，AI 不覆盖

game/templates/
  系统模板，升级时受控更新
```

建议 block marker：

```renpy
# @mcp-generated id=scene_ch1_001 source=game_ir version=1
label ch1_scene_001:
    ...
# @mcp-end
```

规则：

- AI 只能更新带 matching id 的 generated block。
- 用户修改 generated block 后，系统标记 dirty，不自动覆盖。
- 新支线优先 append 新 label。
- 删除内容必须进入 preview diff，由用户确认。

验收标准：

- 用户手动修改某个 label 后，再生成新支线不会覆盖该 label。
- 系统能报告哪些文件会新增、修改、跳过、冲突。
- commit 失败仍可完整 rollback。

### 阶段 6：让 Dashboard 从流程控制台升级为结构化编辑器

目标：让用户不必直接编辑 JSON 或 `.rpy`，也能维护 IR。

优先做轻量编辑，不急着做复杂图编辑：

1. Chapter / Scene 列表编辑。
2. Dialogue beat 编辑。
3. Choice 编辑。
4. Variable 面板。
5. Asset Requirements 面板。
6. Game Shell / Gallery / Ending Gallery 与 IR 节点关联。
7. Compile Preview。
8. Build Preview。

React Flow 分支图可以后置，不应阻塞 GameIR 和 compiler 落地。

## LLM Agent 与形式化工具层

引入 GameIR、ScriptBlockModel、Compiler 和 ScriptIndex 的核心价值，不是让系统看起来更复杂，而是提升 LLM 在工程操作中的可靠性。

LLM 适合承担：

- 理解用户意图。
- 补全剧情创意。
- 生成台词草稿。
- 规划分支走向。
- 解释诊断结果。
- 提出修改方案。

LLM 不适合直接承担：

- 精确修改第几行。
- 保持 Ren'Py 缩进。
- 同步修改 `label`、`jump`、`call`。
- 判断变量是否已声明。
- 判断资产是否存在或是否可渲染。
- 判断结局、分支、菜单是否可达。
- 避免覆盖用户已经精修的代码。
- 保证 staging、commit、rollback 的事务安全。

因此，形式化工具层应该把 LLM 的工作方式从“直接写 Ren'Py 源码”改成“提交结构化变更意图”：

```text
坏模式：
LLM 直接生成或改写 .rpy 文件

好模式：
LLM 生成结构化意图
  -> 工具校验
  -> 工具生成 AST / ScriptBlockModel
  -> 工具生成 diff
  -> 工具写入 staging
  -> 工具诊断
  -> 用户确认或系统 commit
```

例如用户提出：

```text
给第二章结尾加一个选择，如果好感度大于 3，就进入隐藏结局。
```

LLM 不应直接写：

```renpy
if affection > 3:
    jump hidden_ending
```

而应调用受控工具，提交类似结构化操作：

```json
{
  "operation": "insert_choice",
  "target_label": "ch2_final",
  "choices": [
    {
      "text": "追上她",
      "condition": "affection > 3",
      "effects": [
        {"variable": "affection", "op": "+=", "value": 1}
      ],
      "target": "hidden_ending"
    }
  ]
}
```

然后由工具负责：

- 检查 `ch2_final` 是否存在。
- 检查 `affection` 是否声明。
- 检查 `hidden_ending` 是否存在，或按策略创建 ending label。
- 生成正确的 `menu`、`if`、变量操作和 `jump`。
- 保持缩进和 Ren'Py 语法。
- 生成 preview diff。
- 运行 diagnostics。
- 只修改允许修改的 generated block。
- 必要时阻止写入并返回明确错误。

### 与当前 MCP Tools 的关系

当前项目已经有 MCP tools 作为 LLM agent 的行动接口。常规 ChatEngine 路径会把 FastMCP 注册的工具转换成 LLM function/tool schema，再由 LLM 决定是否调用工具。

当前关系可以概括为：

```text
Dashboard Chat
  -> WebSocket /ws/chat
     -> BlueprintOrchestrator 路径
        直接调用 ProjectManager / service / LLM provider
        不走 MCP tools

     -> ChatEngine ReAct 路径
        ToolAdapter 暴露 MCP tools
        LLM 选择 tool call
        ChatEngine 调用 mcp.call_tool(...)
        MCP tool 修改或分析项目
```

这说明项目中已经存在“LLM 通过工具操作工程”的基础。但当前 tools 仍存在几个问题：

- 部分工具直接读写 `.rpy` 文件。
- `analysis.py`、`refactor.py`、`assets.py` 各自用正则扫描脚本，底层模型不统一。
- 旧式 `generate_script()`、`edit_project_file()`、`insert_dialogue()` 可能绕过 stepwise staging/rollback。
- LLM 默认能看到较大的工具面，可能选择风险更高的低层文件操作。
- 工具层和当前产品化 service/FastAPI 生成流水线尚未完全统一。

因此，下一步不应简单增加更多 LLM 工具，而是把工具层收敛到形式化服务上：

```text
ScriptModelService
  parser
  indexer
  diagnostics
  editor
  writer
  compiler

MCP Script Tools
  script_index
  validate_scripts
  preview_script_edit
  apply_script_edit
  insert_dialogue
  insert_menu_choice
  rename_label
  compile_game_ir
  diagnose_build_error

Dashboard / FastAPI
  复用同一套 ScriptModelService
```

最终目标是让 LLM agent 不再直接使用 raw file edit，而是通过受控工具执行结构化修改：

```text
LLM 意图
  -> MCP AST / ScriptModel tools
  -> ScriptModelService
  -> validated diff
  -> staging write
  -> commit / rollback
```

这会带来几类可靠性提升：

1. **语法可靠性**
   - Ren'Py 语句由 Writer 生成，而不是 LLM 手写。
   - 缩进、引号、`label`、`menu`、`jump` 格式由确定性代码控制。

2. **引用一致性**
   - 改名时同步更新 `jump`、`call`、dialogue、show、asset reference。
   - 避免 label 改了但跳转没改的错误。

3. **控制流可靠性**
   - 检查 orphan label、dead end、missing jump target。
   - 检查 ending 是否可达。
   - 检查 choice 是否有出口。

4. **变量可靠性**
   - 检查变量是否声明。
   - 检查变量是否读写一致。
   - 检查条件表达式是否引用未知变量。

5. **资产可靠性**
   - 检查 image、audio、voice、Gallery 引用是否存在。
   - 防止 placeholder 或不可渲染资产进入运行时场景。

6. **增量安全**
   - generated 区域可重写。
   - custom 区域只读或需显式确认。
   - dirty generated block 不自动覆盖。
   - 所有修改先生成 diff，再进入 commit。

7. **诊断闭环**
   - build/lint 错误可以映射回 AST 节点或 GameIR 节点。
   - Agent 可以基于诊断调用修复工具，而不是凭上下文猜测。

因此，形式化工具层的定位应是：

```text
LLM 负责创造性与意图理解。
GameIR / AST / Compiler / Diagnostics 负责工程正确性。
MCP tools 是 LLM 调用这些确定性能力的安全入口。
```

## 推荐近期路线

如果只选最关键的三步，建议按以下顺序执行：

### 第一优先级：GameIR v1

原因：没有稳定 IR，后面所有功能都会变成局部补丁。

产出：

- `meta/game_ir.json`
- Pydantic models
- 从现有 blueprint/scene package 迁移或派生 GameIR
- IR validator

### 第二优先级：Asset Manifest Protocol

原因：视觉小说的工程价值很大一部分来自资产组织，而不是文字生成本身。

产出：

- `asset_requirements.json`
- `asset_manifest.json`
- 统一上传/AI 生成/本地 provider 生命周期
- 表情变体和 CG 进入同一协议

### 第三优先级：Generated/User Ownership

原因：这是“玩具”和“生产力工具”的分界线。

产出：

- generated/custom 文件边界
- block marker
- dirty detection
- preview diff
- no-overwrite policy

## 最终判断

当前项目距离目标并不遥远，但需要明确战略重心。

它已经具备：

- 可运行流水线。
- 结构化模型雏形。
- 确定性脚本渲染服务。
- 分步资产确认。
- 事务性 commit/rollback。
- Game Shell 前置方向。

它仍缺少：

- 权威 GameIR。
- 真正 compiler pass。
- 独立资产协议。
- 游戏变量/状态 DSL。
- 分支/结局/CG 拓扑。
- 无损增量合并模型。
- 面向 IR 的编辑 UI。

因此，下一阶段最重要的不是继续增强“AI 一次生成更多内容”，而是把系统升级为：

```text
AI 生成结构
系统校验结构
编译器输出工程
资产协议填充资源
用户在稳定边界内精修
后续 AI 增量追加而不破坏人工成果
```

这条路线一旦走通，项目的价值会从“能帮我生成一个可玩的 Demo”，提升为“能帮我搭建一个可继续开发的 Ren'Py 工程底座”。
