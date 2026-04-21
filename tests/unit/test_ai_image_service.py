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

    @patch("renpy_mcp.ai.image_service._resize_character_image")
    def test_only_resizes_explicit_generated_files(
        self, mock_resize: MagicMock, tmp_path: Path
    ) -> None:
        """Directory-wide normalization must not touch previously normalized siblings."""
        from renpy_mcp.ai.image_service import _normalize_character_sizes

        assets_dir = tmp_path / "character"
        assets_dir.mkdir()
        generated = assets_dir / "char_0_neutral.png"
        generated.write_bytes(b"\x89PNG")
        old_normalized = assets_dir / "char_1_normalized.png"
        old_normalized.write_bytes(b"\x89PNG")

        _normalize_character_sizes(assets_dir, target_height=750, image_files=[generated])

        mock_resize.assert_called_once_with(generated, target_height=750)


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

        settings = Settings().model_copy(
            update={"qwen_api_key": "test-key", "dashscope_image_model": "qwen-image"}
        )
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

        settings = Settings().model_copy(
            update={"qwen_api_key": "test-key", "dashscope_image_model": "qwen-image"}
        )

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

        settings = Settings().model_copy(
            update={"qwen_api_key": "test-key", "dashscope_image_model": "qwen-image"}
        )

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

    @patch("renpy_mcp.ai.image_service.httpx.AsyncClient")
    async def test_generate_background_success_with_wanx_async_api(
        self, mock_async_client_cls: MagicMock, tmp_path: Path
    ) -> None:
        """wanx-v1 should use async text2image API and poll task results."""
        from renpy_mcp.ai.image_service import ImageService
        from renpy_mcp.config import Settings

        settings = Settings().model_copy(
            update={
                "qwen_api_key": "test-key",
                "dashscope_image_model": "wanx-v1",
                "dashscope_character_image_model": "wanx-v1",
            }
        )

        mock_client = AsyncMock()
        mock_async_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        create_response = MagicMock()
        create_response.json.return_value = {
            "output": {
                "task_id": "task-123",
                "task_status": "PENDING",
            }
        }

        poll_running = MagicMock()
        poll_running.json.return_value = {
            "output": {
                "task_id": "task-123",
                "task_status": "RUNNING",
            }
        }

        poll_success = MagicMock()
        poll_success.json.return_value = {
            "output": {
                "task_id": "task-123",
                "task_status": "SUCCEEDED",
                "results": [{"url": "https://example.com/wanx.png"}],
            }
        }

        image_response = MagicMock()
        image_response.content = b"fake-image-data"

        mock_client.post.return_value = create_response
        mock_client.get.side_effect = [poll_running, poll_success, image_response]

        service = ImageService(settings)
        result = await service.generate_image(
            project_dir=tmp_path,
            prompt="cozy cafe interior",
            image_type="background",
            base_name="cafe_bg",
        )

        assert result.success is True
        assert len(result.files) == 1

        post_args, post_kwargs = mock_client.post.call_args
        assert post_args[0].endswith("/text2image/image-synthesis")
        assert post_kwargs["headers"]["X-DashScope-Async"] == "enable"
        assert post_kwargs["json"]["input"]["prompt"] == "cozy cafe interior"
        assert post_kwargs["json"]["parameters"]["n"] == 1

        first_poll_args, _ = mock_client.get.call_args_list[0]
        assert first_poll_args[0].endswith("/api/v1/tasks/task-123")

    @patch("renpy_mcp.ai.image_service.httpx.AsyncClient")
    async def test_generate_background_fails_when_wanx_task_fails(
        self, mock_async_client_cls: MagicMock, tmp_path: Path
    ) -> None:
        """wanx-v1 should surface async task failure cleanly."""
        from renpy_mcp.ai.image_service import ImageService
        from renpy_mcp.config import Settings

        settings = Settings().model_copy(
            update={
                "qwen_api_key": "test-key",
                "dashscope_image_model": "wanx-v1",
                "dashscope_character_image_model": "wanx-v1",
            }
        )

        mock_client = AsyncMock()
        mock_async_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        create_response = MagicMock()
        create_response.json.return_value = {
            "output": {
                "task_id": "task-456",
                "task_status": "PENDING",
            }
        }

        poll_failed = MagicMock()
        poll_failed.json.return_value = {
            "output": {
                "task_id": "task-456",
                "task_status": "FAILED",
                "message": "bad prompt",
            }
        }

        mock_client.post.return_value = create_response
        mock_client.get.side_effect = [poll_failed]

        service = ImageService(settings)
        result = await service.generate_image(
            project_dir=tmp_path,
            prompt="cozy cafe interior",
            image_type="background",
            base_name="cafe_bg",
        )

        assert result.success is False
        assert "FAILED" in (result.error or "")

    @patch("renpy_mcp.ai.image_service.httpx.AsyncClient")
    async def test_generate_character_with_wanx_uses_supported_size(
        self, mock_async_client_cls: MagicMock, tmp_path: Path
    ) -> None:
        """wanx-v1 character generation must use a model-supported resolution."""
        from renpy_mcp.ai.image_service import ImageService
        from renpy_mcp.config import Settings

        settings = Settings().model_copy(
            update={
                "qwen_api_key": "test-key",
                "dashscope_image_model": "wanx-v1",
                "dashscope_character_image_model": "wanx-v1",
            }
        )

        mock_client = AsyncMock()
        mock_async_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        create_response = MagicMock()
        create_response.json.return_value = {
            "output": {
                "task_id": "task-789",
                "task_status": "PENDING",
            }
        }

        poll_success = MagicMock()
        poll_success.json.return_value = {
            "output": {
                "task_id": "task-789",
                "task_status": "SUCCEEDED",
                "results": [{"url": "https://example.com/wanx-char.png"}],
            }
        }

        image_response = MagicMock()
        image_response.content = b"fake-image-data"

        mock_client.post.return_value = create_response
        mock_client.get.side_effect = [poll_success, image_response]

        service = ImageService(settings)
        result = await service.generate_image(
            project_dir=tmp_path,
            prompt="a friendly swordsman",
            image_type="character",
            base_name="hero",
        )

        assert result.success is True
        _, post_kwargs = mock_client.post.call_args
        assert post_kwargs["json"]["parameters"]["size"] == "768*1152"

    @patch("renpy_mcp.ai.image_service.httpx.AsyncClient")
    async def test_generate_character_uses_qwen_character_override_when_background_model_is_wanx(
        self, mock_async_client_cls: MagicMock, tmp_path: Path
    ) -> None:
        """Character generation should use the dedicated qwen character model override."""
        from renpy_mcp.ai.image_service import ImageService
        from renpy_mcp.config import Settings

        settings = Settings().model_copy(
            update={
                "qwen_api_key": "test-key",
                "dashscope_image_model": "wanx-v1",
                "dashscope_character_image_model": "qwen-image-2.0",
            }
        )

        mock_client = AsyncMock()
        mock_async_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        dashscope_response = MagicMock()
        dashscope_response.json.return_value = {
            "output": {
                "choices": [
                    {
                        "message": {
                            "content": [{"image": "https://example.com/fake-qwen-char.png"}]
                        }
                    }
                ]
            }
        }
        image_response = MagicMock()
        image_response.content = b"fake-image-data"

        mock_client.post.return_value = dashscope_response
        mock_client.get.return_value = image_response

        service = ImageService(settings)
        result = await service.generate_image(
            project_dir=tmp_path,
            prompt="single character sprite",
            image_type="character",
            base_name="hero",
        )

        assert result.success is True
        post_args, post_kwargs = mock_client.post.call_args
        assert post_args[0].endswith("/multimodal-generation/generation")
        assert post_kwargs["json"]["model"] == "qwen-image-2.0"
        assert post_kwargs["json"]["parameters"]["size"] == "832*1248"
