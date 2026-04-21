"""Background removal utilities for generated character art."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image

try:
    from rembg import remove as rembg_remove

    REMBG_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover - depends on optional deps
    rembg_remove = None
    REMBG_IMPORT_ERROR = exc

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}


class BackgroundRemover:
    """Remove backgrounds from images using rembg."""

    def __init__(self, resize_to: Optional[int] = None) -> None:
        self.resize_to = resize_to
        self._remove = rembg_remove

        if self._remove is None and REMBG_IMPORT_ERROR is not None:
            logger.warning(
                "rembg is unavailable; automatic background removal disabled. (%s)",
                REMBG_IMPORT_ERROR,
            )

    def remove_background(self, input_path: Path) -> Optional[Path]:
        """Remove the background from a single image.

        The output will maintain the same dimensions as the input image.
        """
        if self._remove is None:
            return None

        try:
            input_path = input_path.resolve()

            if input_path.suffix.lower() not in IMAGE_EXTENSIONS:
                logger.debug("Skipping unsupported file %s", input_path)
                return None

            output_path = input_path.with_name(f"{input_path.stem}_transparent.png")
            if output_path.exists():
                logger.debug("Transparent version already exists: %s", output_path)
                return output_path

            with Image.open(input_path) as image:
                # Store original dimensions to maintain size
                original_size = image.size

                # Remove background
                result = self._remove(image)

                # Ensure result maintains input dimensions
                if result.size != original_size:
                    logger.warning(
                        "Background removal changed size %s -> %s, resizing back",
                        original_size,
                        result.size,
                    )
                    result = result.resize(original_size, Image.Resampling.LANCZOS)

                # Apply optional resize (if configured)
                if self.resize_to:
                    result = result.resize(
                        (self.resize_to, self.resize_to), Image.Resampling.LANCZOS
                    )

                result.save(output_path, "PNG", optimize=True)

            logger.info("Removed background: %s -> %s", input_path, output_path)
            return output_path
        except Exception as exc:  # pragma: no cover - best effort logging
            logger.error("Failed to remove background for %s: %s", input_path, exc)
            return None

    def normalize_sprite(
        self,
        input_path: Path,
        output_path: Path | None = None,
        target_height: int = 750,
        canvas_height: int = 900,
    ) -> tuple[Path | None, dict]:
        """Trim transparent edges and normalize sprite to a consistent baseline canvas.

        Steps:
        1. Open the image (RGBA) and find the bounding box of non-transparent pixels.
        2. Crop to the bbox.
        3. Scale so the cropped height matches target_height.
        4. Place the scaled image at the bottom-center of a fixed-size canvas.
        5. Record baseline metadata.

        Returns:
            (normalized_path, metadata) where metadata contains:
            - bbox: {left, top, right, bottom} in original coordinates
            - baseline_offset: pixels from bottom of bbox to bottom of normalized canvas
            - normalized_size: (width, height)
            - visible_ratio: ratio of visible pixels to total pixels
            - renderable: bool — whether the sprite passes quality gate
            - reason: str — human-readable quality assessment
        """
        try:
            with Image.open(input_path) as img:
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                alpha = img.split()[-1]
                bbox = alpha.getbbox()
                if not bbox:
                    return None, {
                        "bbox": None,
                        "baseline_offset": 0,
                        "normalized_size": (0, 0),
                        "visible_ratio": 0.0,
                        "renderable": False,
                        "reason": "no_visible_pixels",
                    }

                left, top, right, bottom = bbox
                visible_pixels = sum(
                    1 for x in range(left, right) for y in range(top, bottom)
                    if alpha.getpixel((x, y)) > 10
                )
                total_pixels = img.width * img.height
                visible_ratio = visible_pixels / total_pixels if total_pixels > 0 else 0.0
                bbox_width = right - left
                bbox_height = bottom - top
                width_ratio = bbox_width / img.width if img.width > 0 else 0.0
                height_ratio = bbox_height / img.height if img.height > 0 else 0.0
                portrait_ratio = bbox_height / max(1, bbox_width)

                # Crop to visible area
                cropped = img.crop(bbox)

                # Scale to target height
                cw, ch = cropped.size
                if ch > 0:
                    scale = target_height / ch
                    new_w = max(1, int(cw * scale))
                    new_h = max(1, int(ch * scale))
                    cropped = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)
                else:
                    return None, {
                        "bbox": None,
                        "baseline_offset": 0,
                        "normalized_size": (0, 0),
                        "visible_ratio": 0.0,
                        "renderable": False,
                        "reason": "zero_height_after_crop",
                    }

                # Create normalized canvas and center the sprite at the bottom
                canvas = Image.new("RGBA", (canvas_height, canvas_height), (0, 0, 0, 0))
                paste_x = (canvas.width - cropped.width) // 2
                paste_y = canvas.height - cropped.height
                canvas.paste(cropped, (paste_x, paste_y), cropped)

                if output_path is None:
                    output_path = input_path.with_name(
                        f"{input_path.stem}_normalized.png"
                    )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                canvas.save(output_path, "PNG")

                # Quality gate: reject if too little visible content or too small
                renderable = True
                reason = "ok"
                if visible_ratio < 0.02:
                    renderable = False
                    reason = "insufficient_visible_pixels"
                elif cropped.width < 100 or cropped.height < 100:
                    renderable = False
                    reason = "sprite_too_small"
                elif width_ratio > 0.55:
                    renderable = False
                    reason = "subject_too_wide"
                elif portrait_ratio < 1.15:
                    renderable = False
                    reason = "not_portrait_sprite"
                elif height_ratio < 0.3:
                    renderable = False
                    reason = "visible_region_too_narrow"

                return output_path, {
                    "bbox": {"left": left, "top": top, "right": right, "bottom": bottom},
                    "baseline_offset": canvas.height - paste_y,
                    "normalized_size": (canvas.width, canvas.height),
                    "visible_ratio": visible_ratio,
                    "renderable": renderable,
                    "reason": reason,
                }
        except Exception as exc:
            logger.error("Sprite normalization failed for %s: %s", input_path, exc)
            return None, {
                "bbox": None,
                "baseline_offset": 0,
                "normalized_size": (0, 0),
                "visible_ratio": 0.0,
                "renderable": False,
                "reason": f"normalization_error: {exc}",
            }

    def process_directory(self, directory: Path) -> Tuple[List[Path], List[Path]]:
        """Process all supported images inside a directory."""
        successes: List[Path] = []
        failures: List[Path] = []

        for image_file in directory.iterdir():
            if not image_file.is_file():
                continue
            if image_file.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if "_transparent" in image_file.stem:
                continue

            output = self.remove_background(image_file)
            if output:
                successes.append(output)
            else:
                failures.append(image_file)

        return successes, failures
