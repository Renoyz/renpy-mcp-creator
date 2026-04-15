"""Tests for web preview and build tools migrated from renpy_mcp_server."""

import importlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def fresh_mcp(monkeypatch, tmp_path: Path):
    """Provide an MCP server with a temporary workspace."""
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("RENPY_MCP_WORKSPACE", str(workspace))

    from renpy_mcp import config as config_module

    importlib.reload(config_module)

    from renpy_mcp import server as server_module

    importlib.reload(server_module)
    return server_module.mcp, workspace


class TestBuildProject:
    @pytest.mark.asyncio
    async def test_build_project_missing_project(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        result = await mcp.call_tool(
            "build_project",
            {"project_name": "missing", "target": "web"},
        )
        data = json.loads(result[0][0].text)
        assert data["success"] is False
        assert "not found" in data["error"]

    @pytest.mark.asyncio
    async def test_build_project_no_sdk(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        await mcp.call_tool("create_project", {"name": "build_test"})

        with patch("renpy_mcp.tools.preview.BuildManager._resolve_toolchain", return_value=None):
            result = await mcp.call_tool(
                "build_project",
                {"project_name": "build_test", "target": "web"},
            )
        data = json.loads(result[0][0].text)
        assert data["success"] is False
        assert "No usable Ren'Py SDK found" in data["error"]


class TestWebPreview:
    @pytest.mark.asyncio
    async def test_start_web_preview_no_build(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        await mcp.call_tool("create_project", {"name": "preview_test"})

        result = await mcp.call_tool(
            "start_web_preview",
            {"project_name": "preview_test"},
        )
        data = json.loads(result[0][0].text)
        assert data["success"] is False
        assert "No web build found" in data["error"]

    @pytest.mark.asyncio
    async def test_start_and_stop_web_preview(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        await mcp.call_tool("create_project", {"name": "preview_test"})

        # Fake a web build directory
        build_dir = workspace / "preview_test-dists" / "preview_test-web"
        build_dir.mkdir(parents=True)
        (build_dir / "index.html").write_text("<html></html>")

        result = await mcp.call_tool(
            "start_web_preview",
            {"project_name": "preview_test"},
        )
        data = json.loads(result[0][0].text)
        assert data["success"] is True
        assert "127.0.0.1" in data["url"]
        assert data["port"] > 0

        stopped = await mcp.call_tool(
            "stop_web_preview",
            {"project_name": "preview_test"},
        )
        stop_data = json.loads(stopped[0][0].text)
        assert stop_data["stopped"] is True
