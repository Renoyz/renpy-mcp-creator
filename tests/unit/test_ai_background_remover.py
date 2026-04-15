"""Tests for background remover."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestBackgroundRemoverUnavailable:
    """Tests when rembg is not installed."""

    def test_remove_background_returns_none_when_unavailable(self, tmp_path: Path) -> None:
        """Should gracefully return None if rembg is unavailable."""
        from renpy_mcp.ai.background_remover import BackgroundRemover

        remover = BackgroundRemover()
        remover._remove = None  # Simulate missing rembg

        input_path = tmp_path / "sprite.png"
        input_path.write_bytes(b"\x89PNG\r\n\x1a\n")

        result = remover.remove_background(input_path)
        assert result is None


class TestBackgroundRemoverWithMock:
    """Tests with mocked rembg."""

    @patch("renpy_mcp.ai.background_remover.rembg_remove")
    def test_removes_background_and_preserves_size(self, mock_rembg: MagicMock, tmp_path: Path) -> None:
        """Should create _transparent.png and preserve original dimensions."""
        from renpy_mcp.ai.background_remover import BackgroundRemover
        from PIL import Image

        # Create a real 100x100 PNG
        input_path = tmp_path / "sprite.png"
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        img.save(input_path, "PNG")

        # Mock rembg to return same-size image
        mock_result = Image.new("RGBA", (100, 100), (0, 255, 0, 128))
        mock_rembg.return_value = mock_result

        remover = BackgroundRemover()
        result = remover.remove_background(input_path)

        assert result is not None
        assert result.name == "sprite_transparent.png"
        assert result.exists()

        # Verify dimensions preserved
        with Image.open(result) as out_img:
            assert out_img.size == (100, 100)

    @patch("renpy_mcp.ai.background_remover.rembg_remove")
    def test_resizes_back_if_rembg_changes_size(self, mock_rembg: MagicMock, tmp_path: Path) -> None:
        """Should resize back to original dimensions if rembg alters size."""
        from renpy_mcp.ai.background_remover import BackgroundRemover
        from PIL import Image

        input_path = tmp_path / "sprite.png"
        img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
        img.save(input_path, "PNG")

        # Mock rembg to return different-size image
        mock_result = Image.new("RGBA", (80, 80), (0, 255, 0, 128))
        mock_rembg.return_value = mock_result

        remover = BackgroundRemover()
        result = remover.remove_background(input_path)

        assert result is not None
        with Image.open(result) as out_img:
            assert out_img.size == (100, 100)

    @patch("renpy_mcp.ai.background_remover.rembg_remove")
    def test_skips_unsupported_extensions(self, mock_rembg: MagicMock, tmp_path: Path) -> None:
        """Should return None for unsupported file types."""
        from renpy_mcp.ai.background_remover import BackgroundRemover

        input_path = tmp_path / "sprite.bmp"
        input_path.write_bytes(b"BM")

        remover = BackgroundRemover()
        result = remover.remove_background(input_path)

        assert result is None
        mock_rembg.assert_not_called()

    @patch("renpy_mcp.ai.background_remover.rembg_remove")
    def test_process_directory(self, mock_rembg: MagicMock, tmp_path: Path) -> None:
        """Should process all images in a directory."""
        from renpy_mcp.ai.background_remover import BackgroundRemover
        from PIL import Image

        # Create two PNGs
        for name in ["a.png", "b.png"]:
            img = Image.new("RGBA", (10, 10), (255, 0, 0, 255))
            img.save(tmp_path / name, "PNG")

        mock_rembg.return_value = Image.new("RGBA", (10, 10), (0, 255, 0, 128))

        remover = BackgroundRemover()
        successes, failures = remover.process_directory(tmp_path)

        assert len(successes) == 2
        assert len(failures) == 0
        assert all("_transparent" in p.name for p in successes)
