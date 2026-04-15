"""Generate visual assets using DashScope qwen-image-2.0-pro."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from PIL import Image

from ..models import ImageGenerationResult

logger = logging.getLogger(__name__)

_DASHSCOPE_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
_DEFAULT_MODEL = "qwen-image-2.0-pro"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "image"


def _resize_character_image(image_path: Path, target_height: int = 750) -> None:
    """Resize character sprite to a consistent size."""
    try:
        img = Image.open(image_path)
        width, height = img.size
        aspect_ratio = width / height
        new_height = target_height
        new_width = int(target_height * aspect_ratio)
        resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        resized.save(image_path, optimize=True, quality=95)
        logger.info("Resized character: %sx%s -> %sx%s", width, height, new_width, new_height)
    except Exception as e:
        logger.warning("Failed to resize image %s: %s", image_path, e)


def _normalize_character_sizes(assets_dir: Path, target_height: int = 750) -> None:
    """Post-process all character images to ensure consistent sizing."""
    try:
        for image_file in assets_dir.glob("*.png"):
            _resize_character_image(image_file, target_height=target_height)
        logger.info("Normalized all character images to %spx height", target_height)
    except Exception as e:
        logger.warning("Failed to normalize character sizes: %s", e)


def _size_for_image_type(image_type: str) -> str:
    """Return recommended DashScope size string for the asset type."""
    if image_type == "background":
        return "1280*720"
    return "1024*1024"


class ImageService:
    """High-level image generation helpers backed by DashScope."""

    def __init__(self, settings) -> None:
        self.settings = settings
        self.api_key = settings.qwen_api_key
        self.model = getattr(settings, "dashscope_image_model", None) or _DEFAULT_MODEL

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def generate_image(
        self,
        project_dir: Path,
        prompt: str,
        image_type: str,
        base_name: Optional[str] = None,
        generate_emotions: bool = False,
    ) -> ImageGenerationResult:
        """Generate an image asset and persist it to the project directory."""
        if not self.api_key:
            return ImageGenerationResult(
                success=False,
                prompt=prompt,
                image_type=image_type,
                error="Image generation service is not configured. Set RENPY_MCP_QWEN_API_KEY.",
            )

        output_dir = project_dir / "game" / "images" / image_type
        output_dir.mkdir(parents=True, exist_ok=True)

        raw_name = (
            base_name or f"{_slugify(prompt)[:48]}-{datetime.utcnow():%Y%m%d%H%M%S}"
        )
        filename_root = _slugify(raw_name)
        saved_files: list[Path] = []

        emotion_suffixes = ["neutral", "happy", "sad", "surprised", "angry"]

        prompts_to_generate: list[tuple[str, str]] = []
        if generate_emotions and image_type == "character":
            for emotion in emotion_suffixes:
                emotion_prompt = (
                    f"{prompt}\n\n"
                    f"Emotion: {emotion}. "
                    "Generate a single character sprite with this exact emotion. "
                    "Only one character in the image, transparent background, full body, consistent scale."
                )
                prompts_to_generate.append((emotion_prompt, f"{filename_root}_{emotion}"))
        else:
            prompts_to_generate.append((prompt, filename_root))

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        size = _size_for_image_type(image_type)

        async with httpx.AsyncClient(timeout=120.0) as client:
            for single_prompt, file_name in prompts_to_generate:
                payload = {
                    "model": self.model,
                    "input": {
                        "messages": [
                            {
                                "role": "user",
                                "content": [{"text": single_prompt}],
                            }
                        ]
                    },
                    "parameters": {
                        "size": size,
                        "watermark": False,
                        "prompt_extend": True,
                    },
                }

                try:
                    response = await client.post(_DASHSCOPE_ENDPOINT, headers=headers, json=payload)
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    logger.error("DashScope HTTP error %s: %s", exc.response.status_code, exc.response.text)
                    return ImageGenerationResult(
                        success=False,
                        prompt=prompt,
                        image_type=image_type,
                        error=f"DashScope API error {exc.response.status_code}: {exc.response.text}",
                    )
                except Exception as exc:  # pragma: no cover
                    logger.exception("DashScope request failed: %s", exc)
                    return ImageGenerationResult(
                        success=False,
                        prompt=prompt,
                        image_type=image_type,
                        error=str(exc),
                    )

                data = response.json()
                image_url = _extract_image_url(data)
                if not image_url:
                    logger.error("No image URL in DashScope response: %s", data)
                    return ImageGenerationResult(
                        success=False,
                        prompt=prompt,
                        image_type=image_type,
                        error="No image URL returned from DashScope.",
                    )

                try:
                    image_resp = await client.get(image_url)
                    image_resp.raise_for_status()
                except Exception as exc:  # pragma: no cover
                    logger.exception("Failed to download image from %s: %s", image_url, exc)
                    return ImageGenerationResult(
                        success=False,
                        prompt=prompt,
                        image_type=image_type,
                        error=f"Failed to download generated image: {exc}",
                    )

                file_path = output_dir / f"{file_name}.png"
                file_path.write_bytes(image_resp.content)
                saved_files.append(file_path)
                logger.info("Saved image: %s", file_path.name)

        if not saved_files:
            return ImageGenerationResult(
                success=False,
                prompt=prompt,
                image_type=image_type,
                error="No image data returned from DashScope.",
            )

        if image_type == "character":
            _normalize_character_sizes(output_dir, target_height=750)
            logger.info(
                "Applied post-generation size normalization to all character images"
            )

        return ImageGenerationResult(
            success=True,
            prompt=prompt,
            image_type=image_type,
            files=saved_files,
            primary_file=saved_files[0],
        )


def _extract_image_url(data: dict) -> Optional[str]:
    """Extract image URL from DashScope multimodal-generation response."""
    try:
        output = data.get("output", {})
        choices = output.get("choices", [])
        if not choices:
            return None
        message = choices[0].get("message", {})
        content_list = message.get("content", [])
        for item in content_list:
            url = item.get("image")
            if url:
                return url
    except Exception:
        return None
    return None
