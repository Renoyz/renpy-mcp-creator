"""Unit tests for core MCP tools with filesystem mocking."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from renpy_mcp.config import RenPyConfig


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a minimal Ren'Py project structure."""
    project_dir = tmp_path / "test_vn"
    game_dir = project_dir / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text(
        'label start:\n    scene bg room\n    "Hello world."\n    return\n',
        encoding="utf-8",
    )
    (game_dir / "options.rpy").write_text(
        "define config.name = _('Test VN')\n",
        encoding="utf-8",
    )
    return project_dir


class TestProjectTools:
    """Tests for project management tools."""

    @pytest.mark.asyncio
    async def test_set_project_success(self, temp_project: Path) -> None:
        """set_project should accept a valid Ren'Py project path."""
        from renpy_mcp.tools.project import register_project_tools
        from renpy_mcp.server import mcp, config

        # Tool is already registered on module import; just call it
        result = await mcp.call_tool("set_project", {"path": str(temp_project)})
        text = result[0][0].text
        assert "Project set to" in text
        assert config.project_path == temp_project

    @pytest.mark.asyncio
    async def test_set_project_invalid(self) -> None:
        """set_project should reject a path without game/ directory."""
        from renpy_mcp.server import mcp

        result = await mcp.call_tool("set_project", {"path": "/nonexistent/path"})
        text = result[0][0].text
        assert "Error" in text

    @pytest.mark.asyncio
    async def test_get_project_info(self, temp_project: Path) -> None:
        """get_project_info should list rpy files and directories."""
        from renpy_mcp.server import mcp

        await mcp.call_tool("set_project", {"path": str(temp_project)})
        result = await mcp.call_tool("get_project_info", {})
        data = json.loads(result[0][0].text)

        assert data["project_path"] == str(temp_project)
        assert any("script.rpy" in p for p in data["rpy_files"])


class TestAnalysisTools:
    """Tests for story analysis tools."""

    @pytest.mark.asyncio
    async def test_story_flow_graph(self, temp_project: Path) -> None:
        """story_flow_graph should extract labels and jumps."""
        from renpy_mcp.server import mcp

        await mcp.call_tool("set_project", {"path": str(temp_project)})
        result = await mcp.call_tool("story_flow_graph", {})
        data = json.loads(result[0][0].text)

        assert "labels" in data
        assert "mermaid" in data
        assert "start" in data["labels"]
        assert data["labels"]["start"]["has_return"] is True

    @pytest.mark.asyncio
    async def test_find_dead_ends(self, temp_project: Path) -> None:
        """find_dead_ends should report no issues for a minimal valid script."""
        from renpy_mcp.server import mcp

        await mcp.call_tool("set_project", {"path": str(temp_project)})
        result = await mcp.call_tool("find_dead_ends", {})
        text = result[0][0].text
        assert "No dead ends found" in text


class TestAssetTools:
    """Tests for asset management tools."""

    @pytest.mark.asyncio
    async def test_list_assets(self, temp_project: Path) -> None:
        """list_assets should categorize image/audio/video files."""
        from renpy_mcp.server import mcp

        # Create dummy assets
        images_dir = temp_project / "game" / "images"
        images_dir.mkdir(exist_ok=True)
        (images_dir / "bg_room.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        await mcp.call_tool("set_project", {"path": str(temp_project)})
        result = await mcp.call_tool("list_assets", {})
        data = json.loads(result[0][0].text)

        assert data["summary"]["images_count"] >= 1
        assert any(a["name"] == "bg_room" for a in data["images"])

    @pytest.mark.asyncio
    async def test_find_unused_assets(self, temp_project: Path) -> None:
        """find_unused_assets should flag unreferenced files."""
        from renpy_mcp.server import mcp

        images_dir = temp_project / "game" / "images"
        images_dir.mkdir(exist_ok=True)
        (images_dir / "unused_sprite.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        await mcp.call_tool("set_project", {"path": str(temp_project)})
        result = await mcp.call_tool("find_unused_assets", {})
        text = result[0][0].text
        data = json.loads(text)

        assert data["unused_count"] >= 1
        assert any(u["path"].endswith("unused_sprite.png") for u in data["unused"])
