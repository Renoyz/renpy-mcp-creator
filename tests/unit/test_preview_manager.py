"""Tests for PreviewManager."""

from pathlib import Path

import pytest

from renpy_mcp.services.preview_manager import PreviewManager


@pytest.fixture
def preview_manager():
    return PreviewManager()


class TestPreviewManager:
    @pytest.mark.asyncio
    async def test_start_and_stop_preview(self, preview_manager, tmp_path):
        build_dir = tmp_path / "web"
        build_dir.mkdir()
        (build_dir / "index.html").write_text("<html></html>")

        server = await preview_manager.start("test_vn", build_dir)
        assert server.project_name == "test_vn"
        assert server.directory == build_dir
        assert server.port > 0
        assert "127.0.0.1" in server.url

        stopped = await preview_manager.stop("test_vn")
        assert stopped is True

        # Second stop should return False
        stopped_again = await preview_manager.stop("test_vn")
        assert stopped_again is False

    @pytest.mark.asyncio
    async def test_stop_all(self, preview_manager, tmp_path):
        for name in ["a", "b"]:
            d = tmp_path / name
            d.mkdir()
            (d / "index.html").write_text("<html></html>")
            await preview_manager.start(name, d)

        await preview_manager.stop_all()
        assert len(preview_manager._servers) == 0

    def test_allocate_port(self, preview_manager):
        port1 = preview_manager._allocate_port()
        port2 = preview_manager._allocate_port()
        assert port1 > 0
        assert port2 > 0
        assert port1 != port2
