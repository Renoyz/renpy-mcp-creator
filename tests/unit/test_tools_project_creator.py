"""Tests for project creator tools migrated from renpy_mcp_server."""

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def fresh_mcp(monkeypatch, tmp_path: Path):
    """Provide an MCP server with a temporary workspace."""
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("RENPY_MCP_WORKSPACE", str(workspace))

    # Reload config to pick up the new env var (resets _settings singleton)
    from renpy_mcp import config as config_module

    importlib.reload(config_module)

    # Reload server so tools register with the fresh config
    from renpy_mcp import server as server_module

    importlib.reload(server_module)
    return server_module.mcp, workspace


class TestCreateProject:
    @pytest.mark.asyncio
    async def test_create_project_basic(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        result = await mcp.call_tool("create_project", {"name": "my_vn"})
        data = json.loads(result[0][0].text)
        assert data["name"] == "my_vn"
        assert "path" in data
        assert Path(data["path"]).exists()

    @pytest.mark.asyncio
    async def test_create_project_with_template(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        result = await mcp.call_tool(
            "create_project", {"name": "templated_vn", "template": "basic"}
        )
        data = json.loads(result[0][0].text)
        assert data["template"] == "basic"
        project_path = Path(data["path"])
        assert (project_path / "game" / "script.rpy").exists()
        assert (project_path / "game" / "options.rpy").exists()


class TestListProjects:
    @pytest.mark.asyncio
    async def test_list_projects(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        await mcp.call_tool("create_project", {"name": "project_a"})
        await mcp.call_tool("create_project", {"name": "project_b"})

        result = await mcp.call_tool("list_projects", {})
        data = json.loads(result[0][0].text)
        names = {p["name"] for p in data["projects"]}
        assert "project_a" in names
        assert "project_b" in names


class TestProjectFiles:
    @pytest.mark.asyncio
    async def test_list_project_files(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        await mcp.call_tool("create_project", {"name": "file_test"})
        result = await mcp.call_tool("list_project_files", {"project_name": "file_test"})
        data = json.loads(result[0][0].text)
        assert data["project"] == "file_test"
        paths = {f["path"] for f in data["files"]}
        assert "script.rpy" in paths
        assert "options.rpy" in paths

    @pytest.mark.asyncio
    async def test_read_project_file(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        await mcp.call_tool("create_project", {"name": "read_test"})
        result = await mcp.call_tool(
            "read_project_file",
            {"project_name": "read_test", "file_path": "script.rpy"},
        )
        data = json.loads(result[0][0].text)
        assert "label start:" in data["content"]
        assert data["file_path"] == "script.rpy"

    @pytest.mark.asyncio
    async def test_edit_project_file(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        await mcp.call_tool("create_project", {"name": "edit_test"})
        result = await mcp.call_tool(
            "edit_project_file",
            {
                "project_name": "edit_test",
                "file_path": "new_scene.rpy",
                "content": 'label new_scene:\n    "Hello"\n    return\n',
            },
        )
        data = json.loads(result[0][0].text)
        assert data["success"] is True

        # Verify file was written
        project_path = workspace / "edit_test"
        assert (project_path / "game" / "new_scene.rpy").exists()


class TestGenerateScript:
    @pytest.mark.asyncio
    async def test_generate_script_writes_file(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        await mcp.call_tool("create_project", {"name": "script_test"})
        result = await mcp.call_tool(
            "generate_script",
            {
                "project_name": "script_test",
                "script_name": "intro",
                "script_content": 'label intro:\n    "Welcome"\n    return\n',
            },
        )
        data = json.loads(result[0][0].text)
        assert data["success"] is True
        assert data["script_name"] == "intro"

        project_path = workspace / "script_test"
        script_file = project_path / "game" / "intro.rpy"
        assert script_file.exists()
        assert "label intro:" in script_file.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_generate_script_updates_main_script(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        await mcp.call_tool("create_project", {"name": "main_update_test"})
        result = await mcp.call_tool(
            "generate_script",
            {
                "project_name": "main_update_test",
                "script_name": "chapter1",
                "script_content": 'label chapter1:\n    "Chapter 1"\n    return\n',
            },
        )
        data = json.loads(result[0][0].text)
        assert "main script.rpy updated" in data["message"]

        project_path = workspace / "main_update_test"
        main_script = project_path / "game" / "script.rpy"
        content = main_script.read_text(encoding="utf-8")
        assert "call chapter1" in content
