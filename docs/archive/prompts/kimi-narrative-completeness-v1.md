# Kimi 执行任务 — 叙事完整性改进 v1

**任务目标**: 修复生成的 Ren'Py 游戏叙事不完整的问题——每章相同的 emotional_arc、每场景仅 2 段对话、跨章重复"到达场景"。

**设计方**: Claude/DeepSeek (design + review)
**执行方**: Kimi (code execution)

---

## 前置条件

```bash
cd <repository-root>
git status  # 确认没有未提交的修改
python -m pytest tests/integration/test_prototype_generation.py -x -q  # 确认 100% pass
```

---

## Step 1: 位置感知的章节大纲字段推导

**文件**: `src/renpy_mcp/blueprint/outline_derivation.py`

**现状**: `derive_chapter_outline_fields()` 对所有章节返回相同的 `emotional_arc="setup -> escalation"`、`chapter_goal="Advance {name} through..."`、`key_conflict="Pressure escalates around..."`。

**修改**: 根据章节在故事中的位置(early/mid/late)动态变化三个核心字段。

**具体改动** (在 `derive_chapter_outline_fields` 函数中, line 16):

```python
def derive_chapter_outline_fields(
    chapter: ChapterSummary,
    total_chapters: int = 1,
) -> dict:
    scene_names = [scene.name for scene in chapter.scenes if scene.name]
    first_scene_name = scene_names[0] if scene_names else chapter.name
    last_scene_name = scene_names[-1] if scene_names else chapter.name

    # ---- 新增: 位置感知推导 ----
    # 使用 chapter.order 和 total_chapters 计算位置比例
    pos = chapter.order / max(total_chapters, 1)

    # emotional_arc: 早期→setup->escalation, 中期→escalation->confrontation, 后期→climax->resolution
    if pos <= 0.33:
        emotional_arc = "setup -> escalation"
    elif pos <= 0.66:
        emotional_arc = "escalation -> confrontation"
    else:
        emotional_arc = "climax -> resolution"

    # chapter_goal: 早期=介绍世界/角色, 中期=升级风险, 后期=推入高潮/结局
    if pos <= 0.33:
        chapter_goal = f"Introduce the world and characters through {first_scene_name}"
    elif pos <= 0.66:
        chapter_goal = f"Escalate stakes and deepen conflicts through {first_scene_name}"
    else:
        chapter_goal = f"Bring the story to its climax and resolution through {first_scene_name}"

    # key_conflict: 早期=初始摩擦, 中期=升级和联盟变化, 后期=最终对抗
    if pos <= 0.33:
        key_conflict = f"Initial friction emerges around {last_scene_name}"
    elif pos <= 0.66:
        key_conflict = f"Alliances shift and stakes intensify around {last_scene_name}"
    else:
        key_conflict = f"Final confrontation comes to a head around {last_scene_name}"
    # ---- 新增结束 ----

    # ... 以下保持不变 (character_focus, reveals, end_state, mood_or_pacing_bias, relationship_shift, character_presentation_notes)
```

**注意**:
- 删除旧的 `chapter_goal`、`key_conflict`、`emotional_arc` 三行赋值代码
- 保留 `reveals`、`end_state`、`mood_or_pacing_bias`、`character_focus`、`relationship_shift`、`character_presentation_notes` 不变
- `pos` 基于 `chapter.order` (从 1 开始)。如果 `total_chapters=1`，`pos` 会直接落在 `>0.66`，一章故事走到结局。

---

## Step 2: 将章节大纲注入场景生成 prompt

**文件**: `src/renpy_mcp/services/scene_generation_service.py`

**问题**: `generate_scenes()` 的 prompt (line 307-349) 只包含 `{blueprint.title}`、`{blueprint.genre}` 等蓝图信息，但没有 `chapter_goal`、`emotional_arc`、`key_conflict` 等章节级别的叙事方向。

### Step 2a: 修改 `generate_all_chapter_scenes` (line 412)

在循环中累积 `previous_chapter_summaries`，并从 `chapter_outline.json` 读取 outline 数据：

```python
async def generate_all_chapter_scenes(
    self, project_name: str, blueprint: ProjectBlueprint
) -> dict[str, list]:
    from renpy_mcp.services.prototype_generation_service import PrototypeScene

    if self.provider is None:
        raise RuntimeError("No LLM provider configured for prototype generation.")

    # ---- 新增: 读取 outline + 构建 lookup ----
    outline_lookup: dict[str, dict] = {}
    if self.pm is not None:
        try:
            outline = self.pm.read_chapter_outline(project_name)
            if outline:
                for entry in outline.get("chapters", []):
                    outline_lookup[entry.get("chapter_id")] = entry
        except Exception:
            pass  # outline 读取失败不阻塞生成
    # ---- 新增结束 ----

    packages: dict[str, list] = {}
    chapter_map: dict[str, ChapterSummary] = {}
    previous_chapter_summaries: list[str] = []  # 新增: 跨章连续性

    for chapter in blueprint.chapters:
        contract = self.build_generation_contract(project_name, blueprint, chapter)
        outline_entry = outline_lookup.get(chapter.id)  # 新增

        scenes = await self.generate_scenes(
            chapter, blueprint, contract=contract,
            outline_entry=outline_entry,  # 新增
            previous_chapter_summaries=list(previous_chapter_summaries),  # 新增
            min_beats_per_scene=4,
            max_beats_per_scene=8,
        )
        packages[chapter.id] = scenes
        chapter_map[chapter.id] = chapter

        # 新增: 累积场景摘要
        ch_summary_parts = [f"Chapter {chapter.order}: {chapter.name}"]
        for s in scenes:
            ch_summary_parts.append(f"  - {s.scene_id}: {s.summary}")
        previous_chapter_summaries.append("\n".join(ch_summary_parts))

    # ... persistence logic 不变 ...
```

### Step 2b: 修改 `generate_scenes` (line 241)

新增可选参数 `outline_entry`、`previous_chapter_summaries`、`min_beats_per_scene`、`max_beats_per_scene`:

```python
async def generate_scenes(
    self,
    chapter: ChapterSummary,
    blueprint: ProjectBlueprint,
    contract: GenerationContract | None = None,
    outline_entry: dict | None = None,           # 新增
    previous_chapter_summaries: list[str] | None = None,  # 新增
    min_beats_per_scene: int = 2,                  # 新增 (默认2保持向后兼容)
    max_beats_per_scene: int = 8,                  # 新增
) -> list:
```

### Step 2c: 在 prompt 中注入叙事块 (在 line 317 后, line 318 前)

```python
    Prototype Chapter: {chapter.name} (chapter_id: "{chapter.id}")

    # ---- 新增: narrative_block ----
    {narrative_block}
    # ---- 新增结束 ----

    # ---- 新增: continuity_block ----
    {continuity_block}
    # ---- 新增结束 ----

    {style_block}Generate a JSON array of scenes...
```

**构造 narrative_block** (放在 prompt 构造中, 约 line 306 之后):

```python
    # 构造叙事块
    narrative_lines = []
    if outline_entry:
        narrative_lines.append("Chapter Narrative Direction:")
        if outline_entry.get("chapter_goal"):
            narrative_lines.append(f"- Chapter Goal: {outline_entry['chapter_goal']}")
        if outline_entry.get("emotional_arc"):
            narrative_lines.append(f"- Emotional Arc: {outline_entry['emotional_arc']}")
        if outline_entry.get("key_conflict"):
            narrative_lines.append(f"- Key Conflict: {outline_entry['key_conflict']}")
        if outline_entry.get("character_focus"):
            chars = ", ".join(outline_entry["character_focus"])
            narrative_lines.append(f"- Character Focus: {chars}")
        if outline_entry.get("relationship_shift"):
            narrative_lines.append(f"- Relationship Shift: {outline_entry['relationship_shift']}")
        if outline_entry.get("reveals"):
            narrative_lines.append(f"- Key Reveals: {outline_entry['reveals']}")
        if outline_entry.get("end_state"):
            narrative_lines.append(f"- Desired End State: {outline_entry['end_state']}")
        if outline_entry.get("mood_or_pacing_bias"):
            narrative_lines.append(f"- Mood / Pacing: {outline_entry['mood_or_pacing_bias']}")
        narrative_lines.append("")
    narrative_block = "\n".join(narrative_lines)

    # 构造连续性块
    continuity_lines = []
    if previous_chapter_summaries:
        continuity_lines.append("Previously Established (DO NOT REPEAT):")
        for prev in previous_chapter_summaries:
            continuity_lines.append(prev)
        continuity_lines.append(""
>           Ensure this chapter starts from a different location and situation than
>           previous chapters. Do NOT repeat the same arrival/introduction pattern.")
        continuity_lines.append("")
    continuity_block = "\n".join(continuity_lines)
```

---

## Step 3: 对话节拍数要求和软校验

### Step 3a: 在 prompt 中加入对话节拍要求

在 prompt 的 `Requirements:` 部分末尾 (line 346 附近) 添加:

```python
    Requirements:
    - 2 to 4 scenes total
    - Linear flow: each scene (except last) points to the next
    - Last scene has next_scene_id = null
    - Each scene MUST have between {min_beats_per_scene} and {max_beats_per_scene} dialogue_beats
    - Each dialogue beat should feel like a complete emotional exchange, not a single-line reply
    - Build mini-arcs within the scene's beats: setup → tension → release/follow-through
    - Output ONLY the JSON array, nothing else.
```

注意 prompt 是 f-string，`{min_beats_per_scene}` 和 `{max_beats_per_scene}` 会自动展开。

### Step 3b: 在 `_validate_scene_consistency` 中加入软校验

**文件**: `src/renpy_mcp/services/scene_generation_service.py` line 212

在函数末尾添加警告 (不阻塞生成):

```python
def _validate_scene_consistency(self, scenes: list) -> None:
    # ... 现有校验逻辑不变 ...

    # 新增: 对话节拍数量警告
    for scene in scenes:
        beats = getattr(scene, "dialogue_beats", []) or []
        if len(beats) < 4:
            logger.warning(
                "Scene %s has only %d dialogue_beats (recommended >= 4). This may result in sparse narrative.",
                getattr(scene, "scene_id", "?"), len(beats)
            )
```

需要在文件顶部 `import logging` 并在模块级 `logger = logging.getLogger(__name__)` (如果还没有的话——检查 line 1-20)。

### Step 3c: `__init__` 添加默认参数 (可选)

在 `SceneGenerationService.__init__` 中不需要添加——参数通过 `generate_scenes` 方法签名默认值控制。类似地在 `PrototypeGenerationService` facade 层也不需要改动。

---

## Step 4: 向后兼容性保证

- 所有新参数都有默认值 (`outline_entry=None`, `previous_chapter_summaries=None`, `min_beats_per_scene=2`)。
- `outline_entry=None` → `narrative_block` 为空 → prompt 不变。
- `previous_chapter_summaries=None` → `continuity_block` 为空 → prompt 不变。
- 节拍数校验是 `logger.warning` 不阻塞。
- 现有 mock-based 测试不应受影响。

---

## 验证

按顺序执行：

```bash
# 1. 现有单元/集成测试必须全部通过
python -m pytest tests/integration/test_prototype_generation.py -x -q
python -m pytest tests/integration/test_requirements_refinement_phase7_round1.py -x -q

# 2. 手动验证: 触发一次完整生成，检查 chapter_outline.json
# 预期: 第一章 emotional_arc: "setup -> escalation"
#       最后一章 emotional_arc: "climax -> resolution"

# 3. 检查场景生成 prompt 日志
# 预期: prompt 中包含 "Chapter Narrative Direction:" 和对应的 chapter_goal/emotional_arc/key_conflict

# 4. 检查生成的场景对话节拍数
# 预期: 每场景 4-8 个 dialogue_beats

# 5. E2E 全链路测试
python -m pytest tests/e2e/test_full_game_creation_real_llm_playwright.py::test_full_game_creation_with_real_llm -v --tb=short -s
```

---

## 常见问题处理

**Q: `self.pm.read_chapter_outline()` 不存在？**
A: 检查 `ProjectManager` 类中的方法名。如果方法不存在，用 `self.pm.read_json(project_name, "chapter_outline.json")` 或 fallback 到手动读取路径。

**Q: `logger` 未定义？**
A: 在 `scene_generation_service.py` 顶部确保有:
```python
import logging
logger = logging.getLogger(__name__)
```

**Q: prompt f-string 中的 `{min_beats_per_scene}` 不展开？**
A: 确保变量在 f-string 作用域内。需要在构造 prompt 前将值赋给局部变量，或使用 `prompt.format(min_beats_per_scene=min_beats_per_scene)` 风格。

**Q: 测试失败？**
A: snapshot 测试可能包含旧的 prompt 文本。用 `--snapshot-update` 更新。如果某个测试专门检查旧 prompt，报告给我(stop)，由我来判断如何处理。

---

## 完成后输出

完成后告诉我：
1. 修改了哪些文件和行号
2. 测试结果 (几个 pass / fail)
3. 如果不小心改了额外的代码，列出
4. 任何未预料到的问题

我会 review 代码变更，然后和你讨论后续优化。
