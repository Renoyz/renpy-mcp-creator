# Ren'Py MCP Unified Server — 用户实际使用流程分析

**版本:** 1.0  
**日期:** 2026-04-14  
**基于:** `design-specification.md`

---

## 1. 用户角色定义

| 角色 | 技能水平 | 核心诉求 | 主要使用模式 |
|------|---------|---------|-------------|
| **创作者 (Creator)** | 非程序员，有故事创意 | 用自然语言快速生成可玩原型 | AI 对话驱动 + 面板可视化确认 |
| **开发者 (Developer)** | 熟悉 Ren'Py，有项目经验 | 高效调试、重构、管理复杂项目 | 面板为主 + AI 辅助特定任务 |
| **团队 Lead (Team Lead)** | 管理多人协作 | 代码质量、翻译进度、资源管理 | 面板监控 + MCP 工具批量检查 |

---

## 2. 首次使用流程（Onboarding）

### 2.1 安装路径 A：Claude Desktop / Cursor 用户（嵌入式模式）

```
用户操作                              系统响应
─────────────────────────────────────────────────────────────────
1. pip install renpy-mcp-unified      → 安装 Python 包
2. 编辑 mcp.json 添加服务器配置       → 配置完成
3. 重启 Claude Desktop                → 服务器被自动启动（stdio）
4. 在 Claude 中说：                   → Claude 调用 project_create
   "帮我创建一个恋爱视觉小说项目"      → 服务器检查 RENPY_SDK_PATH
                                      → 未设置，触发 SDK Auto-Provisioning
                                      → 下载 Ren'Py SDK 到 ~/.renpy-mcp/sdk/
                                      → 下载 web support module
                                      → 创建项目文件夹并返回成功消息
5. Claude 回复：                      → 附带 dashboard URL
   "项目已创建！你可以在 http://localhost:xxxxx 打开面板查看" 
```

### 2.2 安装路径 B：独立开发者（Standalone Mode）

```
用户操作                              系统响应
─────────────────────────────────────────────────────────────────
1. 命令行运行：                       → 启动 uvicorn 进程
   renpy-mcp-server --transport http  → FastAPI + MCP SSE 启动
   --port 8080                        → 自动检测并下载 SDK（如需要）
2. 浏览器访问 localhost:8080          → 加载 React Dashboard
3. 点击 "New Project"                 → 弹出模板选择（minimal / advanced）
4. 输入项目名和基础设定               → 调用 project_create API
5. 进入 Project Explorer              → 项目已初始化完毕
```

### 2.3 首次配置检查清单

系统会自动完成以下配置，用户基本无感知：
- ✅ Python 环境检查
- ✅ Ren'Py SDK 下载与缓存
- ✅ Web module 安装
- ✅ 工作区目录创建
- ✅ 默认模板复制

用户可能需要手动配置的仅有两项：
- 🔧 `GEMINI_API_KEY`（如需 AI 生图功能）
- 🔧 `RENPY_SDK_PATH`（如希望使用自定义 SDK 路径）

---

## 3. 场景一：AI 驱动快速原型（创作者主线流程）

### 3.1 宏观流程

```
[创意输入] → [AI 生成脚本] → [AI 生成资源] → [自动构建] → [实时预览] → [迭代修改]
     ↑_______________________________________________________________↓
```

### 3.2 详细交互时序

#### Step 1: 概念设计（自然语言 → 结构化剧本）

**用户输入（Claude 对话）:**
> "我想做一个关于咖啡店相遇的视觉小说。主角叫小林，店员叫艾米。有三个场景：初次见面、点单选择、道别。根据选择有好感度变化。"

**Claude 内部决策:**
1. 调用 `project_create(name="coffee_encounter")`
2. 调用 `script_generate` 分三次生成三个 label：`scene1_meet`、`scene2_order`、`scene3_goodbye`
3. 分析脚本中的资源需求：
   - 背景：`bg cafe_interior`（傍晚）
   - 角色：`emi`（艾米，barista，friendly）

**系统执行:**
```python
# 1. 生成主脚本
file_write(project="coffee_encounter", path="script.rpy", content=...)

# 2. 生成三个场景分镜脚本
script_generate(scene_description="小林走进咖啡店...")
script_generate(scene_description="艾米微笑着递上菜单...")
script_generate(scene_description="根据好感度，道别场景不同...")
```

#### Step 2: 资源生成（AI 描述 → 图片资产）

**Claude 自动调用:**
```
asset_generate_background(
    project_name="coffee_encounter",
    description="Cozy coffee shop interior, evening golden hour, warm lighting, wooden counters, soft bokeh"
)

asset_generate_character(
    project_name="coffee_encounter",
    character_name="emi",
    description="Friendly female barista, short brown hair, green apron, warm smile, anime style",
    generate_emotions=True
)
```

**系统内部处理:**
1. Gemini 生成 1 张 16:9 背景图 → `game/images/bg_cafe_interior.jpg`
2. Gemini 批量生成 5 张 2:3 角色图 → 临时目录
3. `rembg` 处理每张角色图 → `game/images/emi_neutral_transparent.png` 等
4. Pillow resize 到 750px 高度
5. Indexer 检测到新文件，更新 `ProjectIndex.asset_files`

#### Step 3: 脚本验证与修正

**Claude 调用:**
```
script_validate(project_name="coffee_encounter")
```

**系统返回:**
```json
{
  "errors": [
    {"type": "missing_definition", "line": 12, "message": "Character 'XiaoLin' used but not defined with 'define'"}
  ],
  "warnings": [
    {"type": "missing_at_clause", "line": 15, "message": "show emi happy lacks 'at' position clause"}
  ]
}
```

**Claude 自动修正:**
- 插入 `define xiaolin = Character("小林", color="#66ccff")`
- 将 `show emi happy` 改为 `show emi happy at center`

#### Step 4: 构建与预览

**用户说:** "现在能试玩吗？"

**Claude 调用:**
```
build_project(project_name="coffee_encounter", package="web")
preview_start(project_name="coffee_encounter")
```

**系统响应:**
1. 调用 `renpy.sh launcher distribute --package web`
2. 后处理：提取 zip、复制 runtime、生成 game.zip
3. FastAPI 挂载 `/preview/coffee_encounter`
4. 返回 URL：`http://localhost:8080/preview/coffee_encounter`

**用户看到:**
- Claude 回复可玩链接
- Dashboard 的 Live Preview 页面自动加载同一 URL
- 用户可以在浏览器中直接游玩

#### Step 5: 迭代循环

**用户反馈:** "艾米生气的表情不太对，而且我想把道别场景改得更感人。"

**新一轮 AI 交互:**
1. `asset_generate_character` 重新生成 `emi_angry`（指定"slight frown, disappointed rather than furious"）
2. `script_generate` 重写 `scene3_goodbye`
3. `build_project` 重新构建
4. 用户在面板中点击 "Reload Preview" 查看最新效果

---

## 4. 场景二：专业开发调试（开发者主线流程）

### 4.1 日常工作流

```
[打开面板] → [查看 Story Map] → [定位到问题标签] → [Bridge Warp] → [实时调试] → [修复/重构] → [Lint + Test]
```

### 4.2 详细流程：调试一个分支逻辑 Bug

#### Step 1: 项目加载与分析

**用户操作:**
```bash
renpy-mcp-server --transport http --port 8080
# 在 Dashboard 中选择已有项目 "my_complex_vn"
```

**系统自动执行:**
1. `watchdog` 扫描所有 `.rpy` 文件
2. `parser.py` 逐文件解析，构建 `ProjectIndex`
3. `graph_builder.py` 生成 Story Map
4. WebSocket 推送 `{"event": "index_updated", "version": 1}`

#### Step 2: 发现问题

**用户在 Dashboard 中查看 Visual Story Map:**
- 发现 `chapter3_secret` 标签被标记为 **orphan**（灰色）
- 鼠标悬停显示："No incoming edges from start"
- 用户点击查看，发现某处 `jump` 写成了 `chapter3_secre`（拼写错误）

**用户操作选择:**
- 方案 A：直接面板中双击节点，用 Script Editor 修改
- 方案 B：让 AI 修复（Claude 中发送消息）
- 方案 C：使用 `refactor_rename_label`（但这里更适合直接改 `jump` 目标）

#### Step 3: Live Bridge 实时调试

**用户想要验证 chapter3_secret 的内容:**
1. 在 Dashboard 中点击 chapter3_secret 节点右上角的 "Warp Here"
2. 前端发送 WS 消息：`{"action": "bridge_warp", "target": "chapter3_secret"}`
3. 后端 `BridgeService` 写入 `cmd.json`：
   ```json
   {"seq": 15, "command": "jump_to_label", "args": {"label": "chapter3_secret", "variables": {}}}
   ```
4. 运行中的 Ren'Py 游戏（已通过 `bridge_inject` 注入 bridge）读取命令
5. 游戏通过 `FullRestartException` 跳转到该标签
6. Dashboard 的 Live Preview iframe 在 2-3 秒内显示该场景
7. `status.json` 心跳更新：`{"current_label": "chapter3_secret"}`

**用户继续调试:**
- 打开 Dashboard 的 Variable Inspector
- 看到当前 `affinity_score = 45`
- 怀疑应该是 >= 50 才能进入该分支
- 手动在 Variable Inspector 中将 `affinity_score` 改为 55
- 后端调用 `bridge_set_variable`
- 用户点击 "Restart from Label" 验证分支逻辑

#### Step 4: 批量重构

**用户发现角色名需要统一修改:**
> 项目中同时存在 `emi`、`emi_barista`、`emily` 三个标签，其实都指向同一个人。

**用户在 Claude 中说:**
> "把项目中所有 `emi_barista` 和 `emily` 的对话标签合并成 `emi`，并更新所有引用。"

**Claude 调用流程:**
1. `story_get_character_map` 确认引用分布
2. `refactor_rename_character(old="emi_barista", new="emi")`
3. `refactor_rename_character(old="emily", new="emi")`
4. `script_lint` 验证没有语法错误
5. `story_check_consistency` 确认无冲突

**系统执行细节:**
- 解析器索引所有 `define` 和对话引用
- 使用安全的文本替换（保持缩进和注释）
- 更新 `ProjectIndex` 并广播变更

#### Step 5: 自动化测试

**用户运行测试场景:**
1. `test_create_scenario(name="secret_route_high_affinity")`
2. 用户在 Bridge 运行模式下，Dashboard 记录用户点击路径
3. `test_run_scenario` 自动重放路径
4. 系统在关键节点自动调用 `bridge_screenshot`
5. `test_get_report` 返回对比报告

---

## 5. 场景三：团队协作与翻译管理（Team Lead 流程）

### 5.1 工作流程

```
[代码审查] → [翻译进度检查] → [缺失字符串补齐] → [未使用资源清理] → [构建发布包]
```

### 5.2 详细步骤

#### Step 1: 项目健康检查

**Team Lead 在 Claude 中输入:**
> "检查这个项目的整体健康状况。"

**Claude 调用:**
```
project_analyze(project_name="team_vn_project")
```

**系统返回综合报告:**
```json
{
  "lint": {"status": "passed", "warnings": 3},
  "unused_assets": [
    {"path": "game/images/old_bg_school.jpg", "size_kb": 1200},
    {"path": "game/audio/bgm_unused.ogg", "size_kb": 3400}
  ],
  "story_issues": {
    "dead_ends": 1,
    "orphans": 2,
    "unreachable_menus": 0
  },
  "index_version": 42
}
```

#### Step 2: 翻译进度监控

**调用:**
```
translate_get_stats(project_name="team_vn_project")
```

**返回:**
| 语言 | 完成度 | 状态 |
|------|--------|------|
| English | 94% | 🟢 接近完成 |
| 日本語 | 67% | 🟡 进行中 |
| 한국어 | 23% | 🔴 严重滞后 |

**调用:**
```
translate_find_missing(project_name="team_vn_project", language="korean")
```

**系统返回 150 条未翻译字符串，Team Lead 决定:**
1. 将前 50 条分配给 AI 自动翻译：`translate_auto_block`
2. 将剩余 100 条分配给人工译者

#### Step 3: 资源清理与构建

**调用:**
```
asset_find_unused(project_name="team_vn_project")
# 确认无风险后，用户手动在面板中勾选删除
file_delete(path="game/images/old_bg_school.jpg")
file_delete(path="game/audio/bgm_unused.ogg")
```

**最终构建:**
```
build_project(project_name="team_vn_project", package="web")
```

---

## 6. 面板（Dashboard）核心页面使用流程

### 6.1 Project Explorer → Script Editor 联动

```
用户在左侧文件树点击 script.rpy
    ↓
Script Editor 加载文件内容（Monaco）
    ↓
用户编辑第 42 行，保存（Ctrl+S）
    ↓
watchdog 检测到变更
    ↓
parser 重新解析 script.rpy
    ↓
indexer 更新 labels / edges
    ↓
WebSocket 广播 index_updated
    ↓
Visual Story Map 自动重绘（平滑动画过渡）
    ↓
如有错误（如新增 orphan 节点），地图高亮闪烁提示
```

### 6.2 Visual Story Map → Live Preview → Bridge 三角循环

```
用户在 Story Map 中点击 "menu_order" 节点
    ↓
弹出浮层：显示节点详情 + "Read Script" / "Warp to Here" 按钮
    ↓
用户点击 "Warp to Here"
    ↓
Dashboard 发送 bridge_jump_to_label 命令
    ↓
Live Preview iframe 中游戏跳转至该场景（2-3 秒）
    ↓
Bridge 心跳更新 current_label
    ↓
Variable Inspector 显示当前所有 store 变量
    ↓
用户在 Variable Inspector 修改 affinity=80
    ↓
用户点击 "Take Screenshot"
    ↓
Dashboard 下载当前游戏画面，用于团队分享或 bug 报告
```

### 6.3 Asset Gallery 工作流

```
用户进入 Asset Gallery
    ↓
系统显示 game/images/ 和 game/audio/ 的内容
    ↓
未使用资源显示 "UNUSED" 红色角标
    ↓
用户拖拽本地 PNG 文件到上传区
    ↓
asset_normalize 自动调整尺寸和格式
    ↓
文件写入 game/images/
    ↓
Indexer 更新，引用检查触发
    ↓
如 5 秒内无脚本引用该图片，Dashboard 提示 "This image is not referenced in any script"
```

---

## 7. 异常处理与用户恢复流程

### 7.1 构建失败

**场景:** `build_project` 返回失败

**系统行为:**
1. `build_get_status` 保留完整日志
2. Dashboard Build & Deploy 页面标红显示错误行
3. 如果错误是 Ren'Py lint 错误，提供一键跳转 Script Editor 的链接

**用户恢复路径:**
- 路径 A：让 AI 分析构建日志并自动修复
- 路径 B：手动跳转 Script Editor 修复
- 路径 C：回滚到上次成功的 git commit（需用户自行操作）

### 7.2 Bridge 连接断开

**场景:** 游戏崩溃或被用户手动关闭

**系统行为:**
1. `Poller` 检测到 `status.json` 超过 5 秒未更新
2. Dashboard Live Preview 显示 "Game Disconnected" 遮罩层
3. 提供 "Reinject Bridge & Restart" 按钮

### 7.3 AI 生成资源不符合预期

**场景:** 生成的角色表情偏离描述

**用户恢复路径:**
1. 在 Asset Gallery 中点击 "Regenerate"
2. 弹出微调输入框，用户补充描述细节
3. 调用 `asset_generate_character` 重新生成（仅替换该情绪）
4. 旧文件自动备份到 `.mcp_backup/` 目录

### 7.4 解析器对新语法产生误报

**场景:** Ren'Py 新版本引入了 `camera` 语句，解析器将其标记为 `RawLineNode`

**系统行为:**
1. 不影响文件 I/O 和构建
2. Story Map 中该部分显示为 "Unparsed Block"
3. Dashboard 提示："Detected unsupported syntax. Analysis may be incomplete."
4. 用户可以选择忽略，或提交 issue 等待 parser 插件更新

---

## 8. 典型会话完整示例

### 8.1 创作者与 Claude 的完整对话日志（模拟）

> **用户:** 帮我创建一个视觉小说，主题是校园恋爱，主角是高二学生。
> 
> **Claude:** 好的！我先为你创建一个名为 `school_romance` 的项目。请稍等...
> *[调用 project_create]*
> 项目已创建。接下来我为你生成开场脚本和主要角色，然后你可以通过面板查看和试玩。
> *[调用 script_generate 生成 label start + scene1]*
> *[调用 asset_generate_character 生成女主 sakura：5 种情绪]*
> *[调用 asset_generate_background 生成教室背景]*
> 脚本和素材已生成。我正在构建可玩的 web 版本...
> *[调用 build_project]*
> *[调用 preview_start]*
> 完成了！你可以：
> 1. 直接在这里继续和我对话修改剧情
> 2. 打开面板查看故事流程图：http://localhost:8080/dashboard/school_romance
> 3. 试玩链接：http://localhost:8080/preview/school_romance
> 
> **用户:** 女主开心的表情有点怪，重新生成一下，要更阳光的感觉。
> 
> **Claude:** 明白，我重新生成 sakura 的 happy 表情，强调阳光开朗的感觉。
> *[调用 asset_generate_character，仅指定 emotion="happy"]*
> 已更新。需要我重新构建预览吗？
> *[调用 build_project（增量构建，只替换变更图片）]*
> 预览已刷新，你可以直接刷新试玩页面查看新表情。
> 
> **用户:** 在第二章加一个选择支：接受告白还是拒绝。
> 
> **Claude:** 好的，我为第二章添加告白场景和选择支。如果接受告白，进入 happy ending；如果拒绝，进入普通结局。
> *[调用 script_generate 生成 chapter2_confession]*
> *[调用 script_validate 检查语法]*
> *[自动修正缺失的 menu 缩进]*
> 已添加。故事图现在会显示新的分支结构。

### 8.2 开发者的面板操作日志（模拟）

> **动作 1:** 打开 Dashboard → 选择 `my_complex_vn`
> **系统:** 加载项目索引，Story Map 渲染完成（127 个节点，14 个 choice 节点）
> 
> **动作 2:** 发现 `ending_secret` 为 dead_end（红色），点击查看代码
> **系统:** Script Editor 定位到 `ending_secret.rpy:89`
> 
> **动作 3:** 在 Script Editor 中在第 89 行后添加 `return`
> **系统:** 保存后 500ms，Story Map 中 `ending_secret` 变为 normal（蓝色）
> 
> **动作 4:** 点击 `chapter5_boss` 节点的 "Warp Here"
> **系统:** Live Preview 中游戏跳转，Variable Inspector 显示 `boss_hp=100`
> 
> **动作 5:** 在 Variable Inspector 将 `boss_hp` 改为 10，点击 "Take Screenshot"
> **系统:** 下载 screenshot.png，显示残血 BOSS 的对话画面
> 
> **动作 6:** 切换到 Translation Manager，发现 Korean 完成度 23%
> **系统:** 显示 150 条未翻译，用户选中前 50 条点击 "Auto-Translate"
> 
> **动作 7:** 返回 Project Explorer，删除 3 个标记为 UNUSED 的音频文件
> **系统:** 确认删除，索引更新，Asset Gallery 刷新
> 
> **动作 8:** 点击 "Build & Deploy" → "Build Web Package"
> **系统:** 构建进度通过 WebSocket 流式显示，2 分钟后成功，提供 zip 下载

---

## 9. 高频操作速查表

| 用户意图 | 推荐操作方式 | 涉及工具/页面 |
|---------|-------------|--------------|
| 从零创建新项目 | AI 对话 | `project_create` + `script_generate` + `asset_generate_*` |
| 快速试玩当前项目 | AI 对话或面板 | `build_project` + `preview_start` |
| 修改已有脚本 | Script Editor 或直接 AI | `file_edit` / `script_generate` |
| 检查故事结构完整性 | Dashboard Story Map | `story_get_flow_graph` + `story_find_dead_ends` |
| 调试特定场景 | Dashboard + Bridge | `bridge_jump_to_label` + `bridge_set_variable` |
| 重命名角色/标签 | AI 对话 | `refactor_rename_character` / `refactor_rename_label` |
| 生成新背景/角色 | AI 对话 | `asset_generate_background` / `asset_generate_character` |
| 清理未使用资源 | Dashboard Asset Gallery | `asset_find_unused` + `file_delete` |
| 检查翻译进度 | Dashboard Translation Manager | `translate_get_stats` + `translate_find_missing` |
| 导出发布包 | Dashboard Build & Deploy | `build_project` |

---

## 10. 关键设计决策对用户体验的影响

| 设计决策 | 用户收益 | 潜在成本 |
|---------|---------|---------|
| **文件 IPC Bridge** | 无需配置端口/防火墙即可调试 | 命令响应延迟 ~0.5-2s |
| **独立 AST Parser** | 故事图实时更新，无需启动 Ren'Py | 对新语法支持可能有滞后 |
| **一体化 Python 进程** | 安装简单，stdio + HTTP 同时可用 | 单进程故障影响全部功能 |
| **AI 生成与工程工具共存** | 创作者和开发者可用同一套工具 | 工具数量多，初学者可能感到复杂 |
| **增量索引 + WebSocket** | 面板秒级响应文件变更 | 大项目首次索引可能需要数秒 |

---

*用户流程分析完*
