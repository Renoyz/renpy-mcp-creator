"""Tests for AI project creation tools."""

from pathlib import Path

import pytest

from renpy_mcp.config import Settings


@pytest.fixture
def ai_settings(tmp_path: Path) -> Settings:
    """Settings with a temporary workspace for AI project tools."""
    return Settings().model_copy(update={"workspace": tmp_path / "ai_workspace"})


class TestCreateProjectTool:
    """Tests for create_project MCP tool."""

    @pytest.mark.asyncio
    async def test_create_project_with_basic_template(self, ai_settings: Settings) -> None:
        """create_project should create a project from the basic template."""
        from renpy_mcp.tools.ai_project import register_ai_project_tools
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test-mcp")
        register_ai_project_tools(mcp, ai_settings)

        result = await mcp.call_tool("create_project", {"name": "demo_vn", "template": "basic"})
        text = result[0][0].text

        assert '"name": "demo_vn"' in text
        assert '"template": "basic"' in text

        # Verify project directory was created
        project_dir = ai_settings.workspace / "demo_vn"
        assert project_dir.exists()
        assert (project_dir / "game" / "script.rpy").exists()

    @pytest.mark.asyncio
    async def test_create_project_default_template(self, ai_settings: Settings) -> None:
        """create_project should use the default template when none specified."""
        from renpy_mcp.tools.ai_project import register_ai_project_tools
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("test-mcp")
        register_ai_project_tools(mcp, ai_settings)

        result = await mcp.call_tool("create_project", {"name": "default_vn"})
        text = result[0][0].text

        assert '"name": "default_vn"' in text
        assert '"template": "basic"' in text
