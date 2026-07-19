"""Generate visual assets using DashScope image models (default: qwen-image-2.1)."""

from __future__ import annotations

import asyncio
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
_DASHSCOPE_WANX_ENDPOINT = (
    "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
)
_DASHSCOPE_TASKS_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/tasks"
_DEFAULT_MODEL = "qwen-image"
_WANX_ASYNC_POLL_INTERVAL_SECONDS = 1.0
_WANX_ASYNC_MAX_POLLS = 90


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


def _normalize_character_sizes(
    assets_dir: Path,
    target_height: int = 750,
    image_files: list[Path] | None = None,
) -> None:
    """Post-process generated character images to ensure consistent sizing.

    By default this keeps the old directory-based behavior, but callers may pass
    an explicit list of files to avoid reprocessing previously normalized or
    staged siblings.
    """
    try:
        files = image_files if image_files is not None else list(assets_dir.glob("*.png"))
        for image_file in files:
            _resize_character_image(image_file, target_height=target_height)
        logger.info("Normalized all character images to %spx height", target_height)
    except Exception as e:
        logger.warning("Failed to normalize character sizes: %s", e)


def _size_for_image_type(image_type: str) -> str:
    """Return recommended DashScope size string for the asset type."""
    if image_type == "background":
        return "1280*720"
    return "832*1248"


def _uses_wanx_text2image(model: str) -> bool:
    """Return True when the configured model uses the async wanx text2image API."""
    return model == "wanx-v1"


def _wanx_size_for_image_type(image_type: str) -> str:
    """Return wanx-v1-compatible size string for the asset type."""
    if image_type == "background":
        return "1280*720"
    return "768*1152"


class ImageService:
    """High-level image generation helpers backed by DashScope."""

    def __init__(self, settings) -> None:
        self.settings = settings
        self.api_key = settings.qwen_api_key
        self.model = getattr(settings, "dashscope_image_model", None) or _DEFAULT_MODEL
        self.character_model = (
            getattr(settings, "dashscope_character_image_model", None)
            or self.model
        )

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _model_for_image_type(self, image_type: str) -> str:
        if image_type == "character":
            return self.character_model
        return self.model

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
        model = self._model_for_image_type(image_type)
        if _uses_wanx_text2image(model):
            size = _wanx_size_for_image_type(image_type)
        else:
            size = _size_for_image_type(image_type)

        async with httpx.AsyncClient(timeout=120.0) as client:
            for single_prompt, file_name in prompts_to_generate:
                try:
                    if _uses_wanx_text2image(model):
                        image_url = await self._generate_wanx_image_url(
                            client=client,
                            headers=headers,
                            model=model,
                            prompt=single_prompt,
                            size=size,
                        )
                    else:
                        image_url = await self._generate_qwen_image_url(
                            client=client,
                            headers=headers,
                            model=model,
                            prompt=single_prompt,
                            size=size,
                        )
                except RuntimeError as exc:
                    return ImageGenerationResult(
                        success=False,
                        prompt=prompt,
                        image_type=image_type,
                        error=str(exc),
                    )
                if not image_url:
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
            _normalize_character_sizes(output_dir, target_height=750, image_files=saved_files)
            logger.info(
                "Applied post-generation size normalization to generated character images"
            )

        return ImageGenerationResult(
            success=True,
            prompt=prompt,
            image_type=image_type,
            files=saved_files,
            primary_file=saved_files[0],
        )

    async def _generate_qwen_image_url(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        model: str,
        prompt: str,
        size: str,
    ) -> Optional[str]:
        payload = {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt}],
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
            raise RuntimeError(f"DashScope API error {exc.response.status_code}: {exc.response.text}") from exc
        except Exception as exc:  # pragma: no cover
            logger.exception("DashScope request failed: %s", exc)
            raise RuntimeError(str(exc)) from exc

        data = response.json()
        image_url = _extract_image_url(data)
        if image_url:
            return image_url
        logger.error("No image URL in DashScope response: %s", data)
        return None

    async def _generate_wanx_image_url(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        model: str,
        prompt: str,
        size: str,
    ) -> Optional[str]:
        wanx_headers = dict(headers)
        wanx_headers["X-DashScope-Async"] = "enable"
        payload = {
            "model": model,
            "input": {
                "prompt": prompt,
            },
            "parameters": {
                "style": "<auto>",
                "size": size,
                "n": 1,
            },
        }

        try:
            response = await client.post(
                _DASHSCOPE_WANX_ENDPOINT,
                headers=wanx_headers,
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("DashScope HTTP error %s: %s", exc.response.status_code, exc.response.text)
            raise RuntimeError(f"DashScope API error {exc.response.status_code}: {exc.response.text}") from exc
        except Exception as exc:  # pragma: no cover
            logger.exception("DashScope request failed: %s", exc)
            raise RuntimeError(str(exc)) from exc

        data = response.json()
        output = data.get("output", {})
        image_url = _extract_task_image_url(data)
        if image_url:
            return image_url

        task_id = output.get("task_id")
        if not task_id:
            logger.error("No task_id in wanx response: %s", data)
            return None

        for _ in range(_WANX_ASYNC_MAX_POLLS):
            try:
                poll_response = await client.get(
                    f"{_DASHSCOPE_TASKS_ENDPOINT}/{task_id}",
                    headers={"Authorization": headers["Authorization"]},
                )
                poll_response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "DashScope task polling HTTP error %s: %s",
                    exc.response.status_code,
                    exc.response.text,
                )
                raise RuntimeError(
                    f"DashScope task polling error {exc.response.status_code}: {exc.response.text}"
                ) from exc

            task_data = poll_response.json()
            task_output = task_data.get("output", {})
            task_status = (task_output.get("task_status") or "").upper()
            if task_status == "SUCCEEDED":
                image_url = _extract_task_image_url(task_data)
                if image_url:
                    return image_url
                logger.error("No image URL in successful wanx task response: %s", task_data)
                return None
            if task_status in {"FAILED", "CANCELED", "CANCELLED", "UNKNOWN"}:
                message = task_output.get("message") or task_data.get("message") or "unknown task failure"
                raise RuntimeError(f"Wanx task {task_status}: {message}")

            await asyncio.sleep(_WANX_ASYNC_POLL_INTERVAL_SECONDS)

        raise RuntimeError(f"Wanx task polling timed out after {_WANX_ASYNC_MAX_POLLS} attempts")


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
        logger.warning(
            "Failed to extract image URL from LLM response",
            exc_info=True,
        )
        return None
    return None


def _extract_task_image_url(data: dict) -> Optional[str]:
    """Extract image URL from DashScope async task responses."""
    try:
        output = data.get("output", {})
        results = output.get("results", [])
        if isinstance(results, list):
            for item in results:
                url = item.get("url") or item.get("image")
                if url:
                    return url
        output_image_url = output.get("output_image_url")
        if output_image_url:
            return output_image_url
    except Exception:
        logger.warning(
            "Failed to extract task image URL from DashScope response",
            exc_info=True,
        )
        return None
    return None
