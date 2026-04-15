"""Smoke tests for MCP server bootstrap."""

import pytest


@pytest.mark.asyncio
async def test_mcp_server_imports():
    """Server module should import without side effects."""
    from renpy_mcp.server import mcp, config, runner

    assert mcp.name == "renpy-mcp"
    assert config is not None
    assert runner is not None


@pytest.mark.asyncio
async def test_mcp_tools_registered():
    """All v1.1.2 tools should be registered."""
    from renpy_mcp.server import mcp

    tools = await mcp.list_tools()
    resources = await mcp.list_resources()

    assert len(tools) == 70, f"Expected 70 tools, got {len(tools)}"
    assert len(resources) == 1, f"Expected 1 resource, got {len(resources)}"

    tool_names = {t.name for t in tools}
    expected_tools = {
        "set_project",
        "get_project_info",
        "lint_project",
        "story_flow_graph",
        "list_assets",
        "screenshot_scene",
        "search_script",
        "build_project",
        "create_project",
        "list_projects",
        "list_project_files",
        "read_project_file",
        "edit_project_file",
        "generate_script",
        "generate_background",
        "generate_character",
        "start_web_preview",
        "stop_web_preview",
    }
    missing = expected_tools - tool_names
    assert not missing, f"Missing tools: {missing}"


@pytest.mark.asyncio
async def test_mcp_doc_resource_available():
    """Documentation resource should exist."""
    from renpy_mcp.server import mcp

    resources = await mcp.list_resources()
    uris = {str(r.uri) for r in resources}
    assert "renpy://status" in uris
