"""TDD: verify silent-exception paths now emit warnings and keep fallback behavior."""

import json
import logging
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP

from renpy_mcp.config import RenPyConfig


class _FakeRunner:
    async def run_command(self, *args, **kwargs):
        class _Result:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Result()


@pytest.mark.asyncio
async def test_docs_read_failure_logs_warning(caplog):
    """docs._extract_doc_text logs warning on read failure."""
    from renpy_mcp.resources.docs import _extract_doc_text

    with caplog.at_level(logging.WARNING):
        await _extract_doc_text(Path("/nonexistent/file.html"))

    assert any("Failed to read doc text from" in rec.message for rec in caplog.records), (
        "Must log a warning when doc read fails"
    )


def test_activation_service_leftover_cleanup_logs_warning(monkeypatch, tmp_path, caplog):
    """prototype_activation_service logs warning and continues when old prototype cleanup fails."""
    from renpy_mcp.config import get_settings
    from renpy_mcp.services.project_manager import ProjectManager
    from renpy_mcp.services.prototype_activation_service import PrototypeActivationService

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)
    project_name = "test_project"

    project_dir = tmp_path / project_name
    game_dir = project_dir / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text(
        'label start:\n    "Hello from the Ren\'Py MCP server!"\n    return\n',
        encoding="utf-8",
    )
    old_proto = game_dir / "prototype_ch0_Old.rpy"
    old_proto.write_text("# old", encoding="utf-8")
    staging = game_dir / "prototype_ch1_New.__staging__.rpy"
    staging.write_text("# staged", encoding="utf-8")

    service = PrototypeActivationService(ProjectManager(settings))

    original_unlink = Path.unlink

    def failing_unlink(self, *args, **kwargs):
        if self == old_proto:
            raise OSError("permission denied")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr("pathlib.Path.unlink", failing_unlink)
    with caplog.at_level(logging.WARNING):
        service.commit_prototype_replacement(
            project_name=project_name,
            new_scene_ids=["s1"],
            staging_script_path="game/prototype_ch1_New.__staging__.rpy",
        )

    assert not staging.exists()
    # Commit should continue despite failure to remove stale file.
    assert old_proto.exists()
    assert old_proto.read_text(encoding="utf-8") == "# old"
    assert any("Failed to remove old prototype file" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_fastapi_build_status_read_logs_warning(caplog, monkeypatch, tmp_path):
    """fastapi_app._read_build_status logs warning on JSON decode failure."""
    from renpy_mcp.web.fastapi_app import _read_build_status

    corrupt_file = tmp_path / "build-status.json"
    corrupt_file.write_text("not json{{{", encoding="utf-8")
    monkeypatch.setattr(
        "renpy_mcp.web.fastapi_app._build_status_path",
        lambda _pn: corrupt_file,
    )

    with caplog.at_level(logging.WARNING):
        result = _read_build_status("dummy")

    assert result is None
    assert any("Failed to read build status" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_analysis_tool_continue_on_script_read_failure_logs_warning(tmp_path, caplog):
    """analysis.story_flow_graph logs warning and still returns parsed graph on unreadable file."""
    from renpy_mcp.tools.analysis import register_analysis_tools

    project_dir = tmp_path / "analysis_project"
    game_dir = project_dir / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text(
        'label start:\n    "Hello"\n    return\n',
        encoding="utf-8",
    )
    broken_script = game_dir / "broken.rpy"
    broken_script.write_text("broken", encoding="utf-8")

    config = RenPyConfig(project_path=project_dir)
    mcp = FastMCP("analysis-p1")
    register_analysis_tools(mcp, config)

    original_read_text = Path.read_text

    def failing_read_text(self, *args, **kwargs):
        if self == broken_script:
            raise OSError("disk error")
        return original_read_text(self, *args, **kwargs)

    with caplog.at_level(logging.WARNING), pytest.MonkeyPatch().context() as mp:
        mp.setattr("pathlib.Path.read_text", failing_read_text)
        response = await mcp.call_tool("story_flow_graph", {})

    data = json.loads(response[0][0].text)
    assert "start" in data["labels"]
    assert any("Failed to read script during analysis parse" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_assets_tool_continue_on_script_read_failure_logs_warning(tmp_path, caplog):
    """assets.find_unused_assets logs warning and still returns fallback list on unreadable script."""
    from renpy_mcp.tools.assets import register_asset_tools

    project_dir = tmp_path / "assets_project"
    game_dir = project_dir / "game"
    images_dir = game_dir / "images"
    images_dir.mkdir(parents=True)
    (images_dir / "bg_room.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (game_dir / "script.rpy").write_text('label start:\n    return\n', encoding="utf-8")
    broken_script = game_dir / "broken.rpy"
    broken_script.write_text("broken", encoding="utf-8")

    config = RenPyConfig(project_path=project_dir)
    mcp = FastMCP("assets-p1")
    register_asset_tools(mcp, config)

    original_read_text = Path.read_text

    def failing_read_text(self, *args, **kwargs):
        if self == broken_script:
            raise OSError("disk error")
        return original_read_text(self, *args, **kwargs)

    with caplog.at_level(logging.WARNING), pytest.MonkeyPatch().context() as mp:
        mp.setattr("pathlib.Path.read_text", failing_read_text)
        response = await mcp.call_tool("find_unused_assets", {})

    data = json.loads(response[0][0].text)
    assert data["unused_count"] >= 1
    assert any("Failed to read script for asset extraction" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_testing_tool_continue_on_test_read_failure_logs_warning(tmp_path, caplog):
    """testing.list_tests logs warning and still returns collected tests on unreadable script."""
    from renpy_mcp.tools.testing import register_testing_tools

    project_dir = tmp_path / "testing_project"
    game_dir = project_dir / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "good_tests.rpy").write_text("testcase sample:\n    pass\n", encoding="utf-8")
    broken_script = game_dir / "broken.rpy"
    broken_script.write_text("broken", encoding="utf-8")

    config = RenPyConfig(project_path=project_dir)
    mcp = FastMCP("testing-p1")
    register_testing_tools(mcp, config, _FakeRunner())

    original_read_text = Path.read_text

    def failing_read_text(self, *args, **kwargs):
        if self == broken_script:
            raise OSError("disk error")
        return original_read_text(self, *args, **kwargs)

    with caplog.at_level(logging.WARNING), pytest.MonkeyPatch().context() as mp:
        mp.setattr("pathlib.Path.read_text", failing_read_text)
        response = await mcp.call_tool("list_tests", {})

    text = response[0][0].text
    assert "sample" in text
    assert any("Failed to read test file" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_translation_tool_continue_on_translation_read_failure_logs_warning(tmp_path, caplog):
    """translation.list_translations logs warning and still returns fallback counts."""
    from renpy_mcp.tools.translation import register_translation_tools

    project_dir = tmp_path / "translation_project"
    tl_dir = project_dir / "game" / "tl" / "en"
    tl_dir.mkdir(parents=True)
    (tl_dir / "ok.rpy").write_text(
        "translate en strings:\nold \"Hello\"\nnew \"Hello\"\n",
        encoding="utf-8",
    )
    broken_tl = tl_dir / "broken.rpy"
    broken_tl.write_text("translate en strings:\nold \"Bad\"\nnew \"Bad\"\n", encoding="utf-8")

    config = RenPyConfig(project_path=project_dir)
    mcp = FastMCP("translation-p1")
    register_translation_tools(mcp, config, _FakeRunner())

    original_read_text = Path.read_text

    def failing_read_text(self, *args, **kwargs):
        if self == broken_tl:
            raise OSError("disk error")
        return original_read_text(self, *args, **kwargs)

    with caplog.at_level(logging.WARNING), pytest.MonkeyPatch().context() as mp:
        mp.setattr("pathlib.Path.read_text", failing_read_text)
        response = await mcp.call_tool("list_translations", {})

    data = json.loads(response[0][0].text)
    assert "en" in data
    assert data["en"]["total_strings"] >= 1
    assert any("Failed to read translation file" in rec.message for rec in caplog.records)
