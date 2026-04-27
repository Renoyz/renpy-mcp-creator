"""Development-only chat commands for quickly seeding test content."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from renpy_mcp.blueprint.models import (
    BlueprintFreezeStatus,
    BriefCard,
    ChapterOutline,
    ChapterOutlineEntry,
    PipelineStage,
    ProjectBrief,
    ProjectMeta,
    RefinementState,
)
from renpy_mcp.services.project_manager import ProjectManager
from renpy_mcp.services.refinement_logic import assemble_frozen_blueprint


DEV_TEST_COMMAND = "/test"
DEV_TEST_COMMAND_ENV = "RENPY_MCP_DEV_TEST_COMMANDS"


def is_dev_test_command(content: str) -> bool:
    return content.strip() == DEV_TEST_COMMAND


def dev_test_commands_enabled() -> bool:
    return os.getenv(DEV_TEST_COMMAND_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def disabled_dev_test_command_event() -> dict[str, Any]:
    return {
        "type": "message",
        "role": "assistant",
        "message_kind": "system",
        "content": "测试指令未启用。设置 RENPY_MCP_DEV_TEST_COMMANDS=1 后可使用 /test。",
        "pipeline_stage": PipelineStage.IDLE.value,
    }


def _confirmed_card(content: str | dict[str, Any]) -> BriefCard:
    return BriefCard(content=content, confirmed=True)


def build_dev_test_brief() -> ProjectBrief:
    characters = [
        {
            "character_id": "lin_yan",
            "name": "林砚",
            "story_role": "失忆侦探主角",
            "core_motivation": "找回被抹除的案件记忆，同时证明自己没有杀人。",
            "personality_anchors": ["冷静", "自我怀疑", "对细节异常敏感"],
            "visual_identity_anchors": ["深色长风衣", "旧怀表", "右手有烧伤疤痕"],
            "forbidden_drift": ["不能写成轻浮喜剧角色", "不能变成全知侦探"],
        },
        {
            "character_id": "su_qing",
            "name": "苏青",
            "story_role": "记者与情报提供者",
            "core_motivation": "追查父亲失踪真相，利用主角接近警署旧档案。",
            "personality_anchors": ["锋利", "共情强", "不完全可信"],
            "visual_identity_anchors": ["短发", "白衬衫", "随身相机"],
            "forbidden_drift": ["不能只是解释剧情的工具人"],
        },
        {
            "character_id": "shen_mo",
            "name": "沈默",
            "story_role": "旧案幸存者与潜在反派",
            "core_motivation": "阻止真相公开，因为真相会毁掉所有幸存者。",
            "personality_anchors": ["克制", "温和", "压迫感"],
            "visual_identity_anchors": ["黑伞", "灰色西装", "左眼有雾状白斑"],
            "forbidden_drift": ["不能过早暴露真实立场"],
        },
    ]
    relationships = [
        {
            "pair": ["林砚", "苏青"],
            "baseline": "互相利用但逐渐建立信任。",
            "must_preserve": ["苏青必须保留隐瞒关键情报的动机"],
        },
        {
            "pair": ["林砚", "沈默"],
            "baseline": "主角怀疑沈默，却本能地信任他的证词。",
            "must_preserve": ["沈默不能直接承认自己是反派"],
        },
    ]
    cards = {
        "core_premise": _confirmed_card("雨夜旧案重启，失忆侦探发现自己可能是凶手。source: dev_test_command"),
        "audience_genre": _confirmed_card("悬疑视觉小说；面向喜欢推理、人物关系和多结局的玩家"),
        "tone_themes": _confirmed_card("都市悬疑, 记忆不可靠, 信任与背叛, 冷色调浪漫"),
        "visual_style": _confirmed_card("冷雨、霓虹、旧胶片颗粒、低饱和蓝灰色，角色立绘偏写实动画风"),
        "world_rules": _confirmed_card("近未来海港城市；记忆备份技术存在但非法；警方档案可被篡改"),
        "core_cast": _confirmed_card("三人核心：林砚、苏青、沈默；少量警署与报社配角"),
        "character_identity": _confirmed_card({"characters": characters, "source": "dev_test_command"}),
        "relationship_baselines": _confirmed_card({"relationships": relationships, "source": "dev_test_command"}),
        "constraints": _confirmed_card("短篇测试项目；PC；个人开发；source: dev_test_command"),
    }
    return ProjectBrief(cards=cards, updated_at=datetime.utcnow().isoformat())


def build_dev_test_outline() -> ChapterOutline:
    chapters = [
        ChapterOutlineEntry(
            chapter_id="ch1",
            order=1,
            chapter_name="雨夜重启",
            chapter_goal="让玩家理解主角失忆、旧案重启和核心疑点。",
            key_conflict="林砚收到匿名照片，照片显示他站在旧案尸体旁。",
            emotional_arc="困惑 -> 警觉 -> 被迫行动",
            reveals="旧案档案被人重新打开，苏青知道更多内情。",
            end_state="林砚决定与苏青合作调查。",
            mood_or_pacing_bias="慢热悬疑，结尾用强钩子推进。",
            character_focus=["林砚", "苏青"],
            relationship_shift="互相试探，形成临时同盟。",
            character_presentation_notes="林砚保持克制，苏青主动压迫式提问。",
            confirmed=True,
        ),
        ChapterOutlineEntry(
            chapter_id="ch2",
            order=2,
            chapter_name="档案裂缝",
            chapter_goal="调查警署旧档案，展示记忆篡改规则。",
            key_conflict="档案证据与主角残留记忆互相矛盾。",
            emotional_arc="希望 -> 怀疑 -> 自我动摇",
            reveals="沈默是旧案唯一公开幸存者。",
            end_state="主角找到沈默的住址。",
            mood_or_pacing_bias="信息密集但每场只保留一个核心发现。",
            character_focus=["林砚", "苏青", "沈默"],
            relationship_shift="苏青隐瞒信息被主角察觉。",
            character_presentation_notes="沈默先以间接影子出现，不正面解释。",
            confirmed=True,
        ),
        ChapterOutlineEntry(
            chapter_id="ch3",
            order=3,
            chapter_name="黑伞证词",
            chapter_goal="让沈默进入核心三角关系，制造真假证词冲突。",
            key_conflict="沈默提供的证词能洗清主角，却会指向苏青父亲。",
            emotional_arc="接近真相 -> 情感拉扯 -> 信任破裂",
            reveals="苏青父亲参与过非法记忆备份。",
            end_state="三人都意识到旧案不是单人犯罪。",
            mood_or_pacing_bias="压迫、暧昧、长对话中埋伏笔。",
            character_focus=["林砚", "苏青", "沈默"],
            relationship_shift="主角开始怀疑苏青，同时对沈默产生依赖。",
            character_presentation_notes="沈默温和但控制谈话节奏。",
            confirmed=True,
        ),
        ChapterOutlineEntry(
            chapter_id="ch4",
            order=4,
            chapter_name="潮声回放",
            chapter_goal="回到旧案现场，给出可分支的结局前置结构。",
            key_conflict="主角必须选择公开真相、保护幸存者，或删除自己的记忆备份。",
            emotional_arc="崩解 -> 选择 -> 余波",
            reveals="主角不是凶手，但曾主动参与掩盖真相。",
            end_state="进入 Normal/Bad/True Ending 的分支入口。",
            mood_or_pacing_bias="高压收束，保留结局选择空间。",
            character_focus=["林砚", "苏青", "沈默"],
            relationship_shift="三人关系根据玩家选择走向合作或决裂。",
            character_presentation_notes="所有角色都必须暴露一个真实弱点。",
            confirmed=True,
        ),
    ]
    return ChapterOutline(chapters=chapters, updated_at=datetime.utcnow().isoformat())


def materialize_dev_test_project(project_name: str, pm: ProjectManager) -> dict[str, Any]:
    brief = build_dev_test_brief()
    outline = build_dev_test_outline()
    blueprint = assemble_frozen_blueprint(project_name, brief, outline)

    pm.write_project_brief(project_name, brief)
    pm.write_chapter_outline(project_name, outline)
    pm.write_blueprint(project_name, blueprint)

    meta = pm.read_project_meta(project_name)
    project_dir = pm._project_dir(project_name)
    if meta is None:
        meta = ProjectMeta(name=project_name, path=project_dir)
    meta.pipeline_stage = PipelineStage.EDITING
    meta.refinement_state = RefinementState.BLUEPRINT_READY
    meta.blueprint_freeze_status = BlueprintFreezeStatus.NOT_FROZEN
    meta.chapter_count = len(outline.chapters)
    meta.scene_count = 0
    meta.confirmed_scenes = 0
    meta.genre = blueprint.genre
    pm.write_project_meta(project_name, meta)

    marker = project_dir / "meta" / "dev_test_command.json"
    marker.write_text(
        json.dumps(
            {
                "source": "dev_test_command",
                "command": DEV_TEST_COMMAND,
                "created_at": datetime.utcnow().isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "brief": brief,
        "outline": outline,
        "blueprint": blueprint,
    }


def dev_test_command_event(project_name: str, pm: ProjectManager) -> dict[str, Any]:
    materialize_dev_test_project(project_name, pm)
    return {
        "type": "message",
        "role": "assistant",
        "message_kind": "dev_test_command",
        "content": (
            "测试数据已生成：Project Brief 与 Chapter Outline 已自动补齐并确认，"
            "Blueprint 已生成但尚未冻结。现在可以在 Brief/Outline/Blueprint 页面检查，"
            "然后点击 Freeze 进入分步生成测试。"
        ),
        "pipeline_stage": PipelineStage.EDITING.value,
    }
