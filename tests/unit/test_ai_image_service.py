"""Tests for image service."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSlugify:
    """Tests for _slugify helper."""

    def test_slugify_basic(self) -> None:
        from renpy_mcp.ai.image_service import _slugify

        assert _slugify("Hello World") == "hello-world"

    def test_slugify_special_chars(self) -> None:
        from renpy_mcp.ai.image_service import _slugify

        # Non-ASCII chars are stripped by the simple regex
        assert _slugify("Café & Restaurant!!!") == "caf-restaurant"

    def test_slugify_empty_fallback(self) -> None:
        from renpy_mcp.ai.image_service import _slugify

        assert _slugify("!!!") == "image"


class TestNormalizeCharacterSizes:
    """Tests for _normalize_character_sizes."""

    @patch("renpy_mcp.ai.image_service.Image")
    def test_resizes_to_target_height(self, mock_image_cls: MagicMock, tmp_path: Path) -> None:
        """Should resize character images to target height while preserving aspect ratio."""
        from renpy_mcp.ai.image_service import _normalize_character_sizes

        assets_dir = tmp_path / "character"
        assets_dir.mkdir()
        png_file = assets_dir / "hero.png"
        png_file.write_bytes(b"\x89PNG")

        mock_img = MagicMock()
        mock_img.size = (500, 1000)
        # _resize_character_image does NOT use a context manager
        mock_image_cls.open.return_value = mock_img

        _normalize_character_sizes(assets_dir, target_height=750)

        # aspect ratio = 0.5, new_height=750 -> new_width=375
        mock_img.resize.assert_called_once()
        args, _ = mock_img.resize.call_args
        assert args[0] == (375, 750)


class TestImageService:
    """Tests for ImageService."""

    def test_not_available_without_api_key(self) -> None:
        """Should report unavailable when no API key is set."""
        from renpy_mcp.ai.image_service import ImageService
        from renpy_mcp.config import Settings

        settings = Settings()
        settings = settings.model_copy(update={"qwen_api_key": None})
        service = ImageService(settings)
        assert service.is_available() is False

    def test_available_with_api_key(self) -> None:
        """Should report available when API key is present."""
        from renpy_mcp.ai.image_service import ImageService
        from renpy_mcp.config import Settings

        settings = Settings().model_copy(update={"qwen_api_key": "test-key"})
        service = ImageService(settings)
        assert service.is_available() is True

    async def test_generate_image_fails_when_unavailable(self, tmp_path: Path) -> None:
        """Should return success=False when API key is not configured."""
        from renpy_mcp.ai.image_service import ImageService
        from renpy_mcp.config import Settings

        settings = Settings().model_copy(update={"qwen_api_key": None})
        service = ImageService(settings)

        result = await service.generate_image(
            project_dir=tmp_path,
            prompt="a test",
            image_type="background",
        )

        assert result.success is False
        assert "not configured" in (result.error or "").lower()

    @patch("renpy_mcp.ai.image_service.httpx.AsyncClient")
    async def test_generate_background_success(self, mock_async_client_cls: MagicMock, tmp_path: Path) -> None:
        """Should save background image when DashScope returns a URL."""
        from renpy_mcp.ai.image_service import ImageService
        from renpy_mcp.config import Settings

        settings = Settings().model_copy(update={"qwen_api_key": "test-key"})

        # Mock the async client and its response chain
        mock_client = AsyncMock()
        mock_async_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        dashscope_response = MagicMock()
        dashscope_response.status_code = 200
        dashscope_response.json.return_value = {
            "output": {
                "choices": [
                    {
                        "message": {
                            "content": [{"image": "https://example.com/fake.png"}]
                        }
                    }
                ]
            }
        }

        image_response = MagicMock()
        image_response.status_code = 200
        image_response.content = b"fake-image-data"

        mock_client.post.return_value = dashscope_response
        mock_client.get.return_value = image_response

        service = ImageService(settings)
        result = await service.generate_image(
            project_dir=tmp_path,
            prompt="cozy cafe interior",
            image_type="background",
            base_name="cafe_bg",
        )

        assert result.success is True
        assert result.image_type == "background"
        assert len(result.files) == 1
        # _slugify turns underscores into hyphens
        assert result.files[0].name.startswith("cafe-bg")
        assert result.files[0].suffix == ".png"

    @patch("renpy_mcp.ai.image_service.httpx.AsyncClient")
    async def test_generate_character_with_emotions(self, mock_async_client_cls: MagicMock, tmp_path: Path) -> None:
        """Should generate multiple emotion variants for characters."""
        from renpy_mcp.ai.image_service import ImageService
        from renpy_mcp.config import Settings

        settings = Settings().model_copy(update={"qwen_api_key": "test-key"})

        mock_client = AsyncMock()
        mock_async_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        dashscope_response = MagicMock()
        dashscope_response.status_code = 200
        dashscope_response.json.return_value = {
            "output": {
                "choices": [
                    {
                        "message": {
                            "content": [{"image": "https://example.com/fake.png"}]
                        }
                    }
                ]
            }
        }
        image_response = MagicMock()
        image_response.status_code = 200
        image_response.content = b"fake-image-data"

        mock_client.post.return_value = dashscope_response
        mock_client.get.return_value = image_response

        service = ImageService(settings)
        result = await service.generate_image(
            project_dir=tmp_path,
            prompt="a friendly girl",
            image_type="character",
            base_name="alice",
            generate_emotions=True,
        )

        assert result.success is True
        assert len(result.files) == 5
        assert mock_client.post.call_count == 5
