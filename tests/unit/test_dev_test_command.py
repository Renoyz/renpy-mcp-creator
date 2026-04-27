"""Tests for the development-only /test chat command."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


@pytest.fixture()
def pm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from renpy_mcp.config import get_settings
    from renpy_mcp.services.project_manager import ProjectManager

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)
    return ProjectManager(settings)


def _create_project(pm, project_name: str) -> None:
    from renpy_mcp.blueprint.models import ProjectMeta, ProjectStatus

    project_dir = pm._project_dir(project_name)
    (project_dir / "game").mkdir(parents=True)
    (project_dir / "game" / "script.rpy").write_text(
        'label start:\n    "Hello."\n    return\n',
        encoding="utf-8",
    )
    pm.write_project_meta(
        project_name,
        ProjectMeta(
            name=project_name,
            path=project_dir,
            status=ProjectStatus.DRAFT,
        ),
    )


def test_test_command_is_rejected_when_dev_flag_is_disabled(pm, monkeypatch: pytest.MonkeyPatch):
    from renpy_mcp.web.chat_ws import BlueprintOrchestrator

    monkeypatch.delenv("RENPY_MCP_DEV_TEST_COMMANDS", raising=False)
    project_name = "dev_disabled"
    _create_project(pm, project_name)

    orchestrator = BlueprintOrchestrator(project_name, pm)
    events = asyncio.get_event_loop().run_until_complete(
        orchestrator.handle_user_message("/test")
    )

    assert events == [
        {
            "type": "message",
            "role": "assistant",
            "message_kind": "system",
            "content": "测试指令未启用。设置 RENPY_MCP_DEV_TEST_COMMANDS=1 后可使用 /test。",
            "pipeline_stage": "idle",
        }
    ]
    assert pm.read_project_brief(project_name) is None
    assert pm.read_chapter_outline(project_name) is None
    assert pm.read_blueprint(project_name) is None


def test_test_command_materializes_confirmed_test_brief_outline_and_blueprint(
    pm,
    monkeypatch: pytest.MonkeyPatch,
):
    from renpy_mcp.blueprint.models import BlueprintFreezeStatus, RefinementState
    from renpy_mcp.web.chat_ws import BlueprintOrchestrator

    monkeypatch.setenv("RENPY_MCP_DEV_TEST_COMMANDS", "1")
    project_name = "dev_enabled"
    _create_project(pm, project_name)

    orchestrator = BlueprintOrchestrator(project_name, pm)
    events = asyncio.get_event_loop().run_until_complete(
        orchestrator.handle_user_message("/test")
    )

    assert events[0]["type"] == "message"
    assert events[0]["role"] == "assistant"
    assert events[0]["message_kind"] == "dev_test_command"
    assert "测试数据已生成" in events[0]["content"]
    assert events[0]["pipeline_stage"] == "editing"

    brief = pm.read_project_brief(project_name)
    assert brief is not None
    assert all(card.confirmed for card in brief.cards.values())
    assert brief.cards["constraints"].content == "短篇测试项目；PC；个人开发；source: dev_test_command"

    outline = pm.read_chapter_outline(project_name)
    assert outline is not None
    assert len(outline.chapters) == 4
    assert all(ch.confirmed for ch in outline.chapters)

    blueprint = pm.read_blueprint(project_name)
    assert blueprint is not None
    assert blueprint.title == project_name
    assert len(blueprint.characters) == 3
    assert len(blueprint.chapters) == 4

    meta = pm.read_project_meta(project_name)
    assert meta.refinement_state == RefinementState.BLUEPRINT_READY
    assert meta.blueprint_freeze_status == BlueprintFreezeStatus.NOT_FROZEN
    assert meta.pipeline_stage == "editing"

    marker = pm._project_dir(project_name) / "meta" / "dev_test_command.json"
    assert json.loads(marker.read_text(encoding="utf-8"))["source"] == "dev_test_command"
