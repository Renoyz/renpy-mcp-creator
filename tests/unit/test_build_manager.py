"""Tests for BuildManager."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from renpy_mcp.models import BuildRequest, BuildResult
from renpy_mcp.services.build_manager import BuildManager


@pytest.fixture
def settings(tmp_path: Path):
    from renpy_mcp.config import Settings

    return Settings().model_copy(
        update={"workspace": tmp_path / "workspace", "renpy_sdk_path": None}
    )


@pytest.fixture
def build_manager(settings):
    return BuildManager(settings)


class TestBuildManager:
    @pytest.mark.asyncio
    async def test_build_missing_project(self, build_manager):
        req = BuildRequest(project_name="missing")
        result = await build_manager.build(req)
        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_build_no_toolchain(self, settings, tmp_path):
        settings = settings.model_copy(update={"renpy_sdk_path": None})
        bm = BuildManager(settings)

        project_dir = settings.workspace / "test_vn"
        project_dir.mkdir(parents=True)
        (project_dir / "game").mkdir()

        req = BuildRequest(project_name="test_vn")
        result = await bm.build(req)
        assert result.success is False
        assert "No usable Ren'Py SDK found" in result.error

    def test_auto_copy_assets(self, build_manager, tmp_path, settings):
        project_dir = settings.workspace / "test_vn"
        (project_dir / "assets" / "background").mkdir(parents=True)
        (project_dir / "assets" / "character").mkdir(parents=True)
        (project_dir / "game").mkdir()

        (project_dir / "assets" / "background" / "bg.png").write_text("png")
        (project_dir / "assets" / "character" / "char.png").write_text("png")

        build_manager._auto_copy_assets(project_dir)

        assert (project_dir / "game" / "images" / "bg.png").exists()
        assert (project_dir / "game" / "images" / "char.png").exists()
