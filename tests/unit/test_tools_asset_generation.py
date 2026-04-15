"""Tests for asset generation tools migrated from renpy_mcp_server."""

import importlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

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


class TestGenerateBackground:
    @pytest.mark.asyncio
    async def test_generate_background_no_api_key(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        await mcp.call_tool("create_project", {"name": "bg_test"})

        with patch("renpy_mcp.tools.assets.image_service.is_available", return_value=False):
            result = await mcp.call_tool(
                "generate_background",
                {"project_name": "bg_test", "description": "a cafe"},
            )
        data = json.loads(result[0][0].text)
        assert data["success"] is False
        assert "not configured" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_generate_background_success(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        await mcp.call_tool("create_project", {"name": "bg_test"})

        mock_result = AsyncMock()
        mock_result.success = True
        mock_result.prompt = "a cafe"
        mock_result.image_type = "background"
        mock_result.files = [workspace / "bg_test" / "game" / "images" / "background" / "cafe.png"]
        mock_result.primary_file = workspace / "bg_test" / "game" / "images" / "background" / "cafe.png"
        mock_result.error = None
        mock_result.model_dump = lambda mode="json": {
            "success": True,
            "prompt": "a cafe",
            "image_type": "background",
            "files": [str(workspace / "bg_test" / "game" / "images" / "background" / "cafe.png")],
            "primary_file": str(workspace / "bg_test" / "game" / "images" / "background" / "cafe.png"),
            "error": None,
        }

        with patch("renpy_mcp.tools.assets.image_service.is_available", return_value=True), patch(
            "renpy_mcp.tools.assets.image_service.generate_image",
            return_value=mock_result,
        ):
            result = await mcp.call_tool(
                "generate_background",
                {"project_name": "bg_test", "description": "a cozy cafe"},
            )
            data = json.loads(result[0][0].text)
            assert data["success"] is True
            assert data["project"] == "bg_test"
            rel = data["relative_files"][0]
            assert rel.startswith("game/images/background/")
            assert "suggested_image_names" in data


class TestGenerateCharacter:
    @pytest.mark.asyncio
    async def test_generate_character_no_api_key(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        await mcp.call_tool("create_project", {"name": "char_test"})

        with patch("renpy_mcp.tools.assets.image_service.is_available", return_value=False):
            result = await mcp.call_tool(
                "generate_character",
                {
                    "project_name": "char_test",
                    "character_name": "alice",
                    "description": "a friendly girl",
                },
            )
        data = json.loads(result[0][0].text)
        assert data["success"] is False
        assert "not configured" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_generate_character_success(self, fresh_mcp):
        mcp, workspace = fresh_mcp
        await mcp.call_tool("create_project", {"name": "char_test"})

        char_dir = workspace / "char_test" / "game" / "images" / "character"
        char_dir.mkdir(parents=True)
        (char_dir / "alice_neutral.png").write_bytes(b"\x89PNG\r\n\x1a\n")

        mock_result = AsyncMock()
        mock_result.success = True
        mock_result.prompt = "Character name: alice. a friendly girl"
        mock_result.image_type = "character"
        mock_result.files = [char_dir / "alice_neutral.png"]
        mock_result.primary_file = char_dir / "alice_neutral.png"
        mock_result.error = None
        mock_result.model_dump = lambda mode="json": {
            "success": True,
            "prompt": "Character name: alice. a friendly girl",
            "image_type": "character",
            "files": [str(char_dir / "alice_neutral.png")],
            "primary_file": str(char_dir / "alice_neutral.png"),
            "error": None,
        }

        with patch("renpy_mcp.tools.assets.image_service.is_available", return_value=True), patch(
            "renpy_mcp.tools.assets.image_service.generate_image",
            return_value=mock_result,
        ), patch(
            "renpy_mcp.tools.assets.background_remover.remove_background",
            return_value=char_dir / "alice_neutral_transparent.png",
        ):
            result = await mcp.call_tool(
                "generate_character",
                {
                    "project_name": "char_test",
                    "character_name": "alice",
                    "description": "a friendly girl",
                },
            )
            data = json.loads(result[0][0].text)
            assert data["success"] is True
            assert data["project"] == "char_test"
            assert data["character"] == "alice"
            rel = data["relative_files"][0]
            assert rel.startswith("game/images/character/")
            assert "suggested_image_names" in data
