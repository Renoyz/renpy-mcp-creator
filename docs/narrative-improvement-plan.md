# 剧本叙事完整性改进方案

## 问题诊断

通过分析项目 44444 的完整流水线产出，发现以下根因导致剧本叙事不完整：

### 根因 1：章节大纲字段由机械推导而非 LLM 生成

当前 `_build_chapter_intake_entry`（chat_ws.py:777、fastapi_app.py:656）用硬编码公式填充 `emotional_arc`、`chapter_goal`、`key_conflict` 等字段：

```python
emotional_arc = "setup -> escalation"  # 所有 >1 场景的章节全部相同
chapter_goal = f"Advance {chapter.name} through {first_scene_name}"  # 模板填空
key_conflict = f"Pressure escalates around {last_scene_name}"  # 模板填空
character_focus = []  # 永远为空
relationship_shift = ""  # 永远为空
```

不管第几章，都得到相同的叙事弧线。三章全是"铺垫→升级"，故事没有高潮和结局。

### 根因 2：场景生成 prompt 未接收大纲数据

`generate_scenes`（prototype_generation_service.py:916）只接收章节名称和世界观描述，**完全不接收** 章节大纲中的 `chapter_goal`、`emotional_arc`、`key_conflict`、`character_focus`、`relationship_shift` 等字段。LLM 在没有任何叙事指导的条件下生成场景，只能输出骨架模板。

### 根因 3：未指定对白节拍数

场景生成 prompt 没有要求每场景最少对白数。LLM 默认每人一句话（2 句），导致场景空洞。

### 根因 4：章节间完全隔离

每个章节独立调用 `generate_scenes`，对前一章的剧情一无所知。导致 ch2、ch3 重复"登岛"开场。

---

## 改进方案（三层）

### 第一层：章节大纲随位置变化

**修改文件：** `src/renpy_mcp/web/chat_ws.py:777-824`、`src/renpy_mcp/web/fastapi_app.py:656-709`

根据章节在故事中的位置（第几章/共几章），赋予不同的叙事职能：

| 位置 | emotional_arc | chapter_goal | key_conflict |
|------|--------------|-------------|-------------|
| 前 1/3（早期） | `setup → escalation` | 引入世界观、角色、激励事件 | 初始摩擦出现 |
| 中间（中期） | `escalation → confrontation` | 加深冲突、提升赌注 | 压力升级、联盟转变 |
| 后 1/3（末期） | `climax → resolution` | 冲突爆发、达成解决 | 最终对决与收束 |

实现方式：在调用处传入 `total_chapters`，函数内计算 `position_ratio = chapter_index / max(total_chapters - 1, 1)`，按比例分配叙事阶段。

### 第二层：将章节大纲注入场景生成 prompt

**修改文件：** `src/renpy_mcp/services/prototype_generation_service.py`

**2a. 读取大纲并传入生成方法**

`generate_all_chapter_scenes`（line 288）增加：
- 读取 `meta/chapter_outline.json`
- 构建 `chapter_id → ChapterOutlineEntry` 映射
- 累积前几章的摘要作为跨章节上下文
- 将 `outline_entry` 和 `previous_chapter_summaries` 传入 `generate_scenes`

**2b. 构建叙事指导块**

在 prompt 中注入两个新块：

```
# 叙事指导块（来自章节大纲）
Chapter Narrative Direction:
- Chapter Goal: 引入世界观、角色、激励事件...
- Emotional Arc: setup → escalation
- Key Conflict: 初始摩擦出现...
- Character Focus: 沈墨, 江雪遥
- Relationship Shift: ...

# 跨章节连续性块
Previously Established (earlier chapters):
  - Chapter '迷雾海图': Scene ch1-s1: ...; Scene ch1-s2: ...
```

叙事指导块告诉 LLM 这一章要达成什么；连续性块告诉 LLM 前面发生了什么，避免重复"登岛"场景。

**2c. 参数签名**

`generate_scenes` 新增 4 个可选参数（全部带默认值，向后兼容）：

```python
async def generate_scenes(
    self,
    chapter: ChapterSummary,
    blueprint: ProjectBlueprint,
    contract: GenerationContract | None = None,
    outline_entry: ChapterOutlineEntry | None = None,        # 新增
    previous_chapter_summaries: list[str] | None = None,     # 新增
    min_beats_per_scene: int = 4,                            # 新增
    max_beats_per_scene: int = 8,                            # 新增
) -> list[PrototypeScene]:
```

### 第三层：对白节拍数要求

**修改文件：** `src/renpy_mcp/services/prototype_generation_service.py`

**3a. Prompt 中增加要求**

在场景生成 prompt 的 Requirements 部分加入：

```
- Each scene MUST have between 4 and 8 dialogue_beats. Every character present
  should speak at least once unless deliberately silent for dramatic effect.
- The dialogue_beats should form a complete emotional exchange, not just an
  opening line. Include reactions, turn-taking, and emotional shifts.
```

**3b. 构造函数增加配置参数**

```python
def __init__(self, pm, provider,
             min_beats_per_scene: int = 4,
             max_beats_per_scene: int = 8):
```

**3c. 软性验证（仅警告，不阻塞）**

在 `_validate_scene_consistency` 中增加对白数检查，不满足时输出 warning 日志，不阻止生成。

---

## 向后兼容性

- 所有新参数都有默认值
- `outline_entry=None` 时不注入叙事块，prompt 与原版一致
- 对白数验证是 warning 而非 error，现有测试不受影响
- 构造函数新参数有默认值，现有调用方无需修改

## 涉及文件

| 文件 | 改动 |
|------|------|
| `src/renpy_mcp/services/prototype_generation_service.py` | 导入 ChapterOutlineEntry、构造函数增加参数、generate_all_chapter_scenes 读大纲、generate_scenes 增加参数+prompt 注入、_validate_scene_consistency 增加对白数检查 |
| `src/renpy_mcp/web/chat_ws.py` | _build_chapter_intake_entry 根据章节位置变化推导字段 |
| `src/renpy_mcp/web/fastapi_app.py` | _build_chapter_intake_entries_from_blueprint 同上 |

## 验证方式

1. 运行现有测试确保不回归：`pytest tests/integration/test_prototype_generation.py -x -q`
2. 用新项目跑完整流水线，检查：
   - `chapter_outline.json` 中不同章节的 `emotional_arc` 各有不同
   - 每场景对白 ≥4 句
   - 章节间无重复"登岛"开场
   - 最后一章有 `emotional_arc: "climax -> resolution"`
