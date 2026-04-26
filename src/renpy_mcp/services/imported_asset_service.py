"""Service for user-imported image assets."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from PIL import Image


class ImportedAssetService:
    """Validate uploaded images and write them into staging.

    Returns slot metadata suitable for both runtime and staged prototype paths.
    """

    _ALLOWED_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
    _MAX_BYTES = 12 * 1024 * 1024

    def __init__(self, pm) -> None:
        if pm is None:
            raise ValueError("ProjectManager is required")
        self.pm = pm

    @staticmethod
    def _normalize_component(value: str, fallback: str) -> str:
        cleaned = "".join(
            char for char in value.strip().replace("\\", "/")
            if char.isascii() and (char.isalnum() or char in "._-")
        )
        cleaned = cleaned.strip("._")
        return cleaned or fallback

    @staticmethod
    def _safe_round_id(round_id: str | None) -> str:
        return ImportedAssetService._normalize_component(round_id or "r0", "r0")

    @staticmethod
    def _safe_filename_component(filename: str) -> str:
        name = Path(filename).name
        stem = Path(name).stem or "upload"
        return ImportedAssetService._normalize_component(stem, "upload")

    @staticmethod
    def _normalize_kind(kind: str) -> str:
        normalized = kind.strip().lower()
        allowed = {"background", "character_sprite"}
        if normalized not in allowed:
            raise ValueError(f"Unsupported asset kind: {kind!r}")
        return normalized

    @staticmethod
    def _asset_dir_for_kind(kind: str) -> str:
        if kind == "background":
            return "images/background"
        return "images/sprites"

    @staticmethod
    def _make_asset_id(kind: str, target: str, variant: str) -> str:
        if kind == "background":
            return f"bg_{target}_{variant}"
        return f"char_{target}_{variant}"

    @staticmethod
    def _decode(file_bytes: bytes) -> tuple[int, int, bool]:
        with Image.open(io.BytesIO(file_bytes)) as image:
            image.load()
            width, height = image.size
            bands = image.getbands()
            has_alpha = "A" in bands
            if not has_alpha and image.mode == "P" and image.info.get("transparency") is not None:
                has_alpha = True
            return width, height, has_alpha

    @staticmethod
    def _build_validation(width: int, height: int, kind: str, has_alpha: bool) -> dict[str, Any]:
        reason = "ok"
        ok = True

        if kind == "character_sprite" and not has_alpha:
            reason = "no_alpha"
            ok = False
        elif kind == "background":
            if height == 0:
                reason = "invalid_dimensions"
                ok = False
            else:
                ratio = width / float(height)
                if abs(ratio - (16 / 9)) > 0.15:
                    reason = "non_16_9"
        return {
            "ok": ok,
            "width": width,
            "height": height,
            "reason": reason,
        }

    @staticmethod
    def _build_preview_url(project_name: str, staging_path: str) -> str:
        return f"/api/projects/{project_name}/asset-file/{staging_path.removeprefix('game/')}"

    @staticmethod
    def _staging_relpath(round_id: str, kind: str, asset_id: str, extension: str) -> str:
        return (
            Path("game")
            / "__staging__"
            / round_id
            / ImportedAssetService._asset_dir_for_kind(kind)
            / f"{asset_id}{extension}"
        ).as_posix()

    @staticmethod
    def _final_relpath(kind: str, asset_id: str, extension: str) -> str:
        return (
            Path("game")
            / ImportedAssetService._asset_dir_for_kind(kind)
            / f"{asset_id}{extension}"
        ).as_posix()

    def import_image(
        self,
        *,
        project_name: str,
        round_id: str,
        kind: str,
        target: str,
        variant: str,
        filename: str,
        file_bytes: bytes,
    ) -> dict[str, Any]:
        if not isinstance(file_bytes, (bytes, bytearray)):
            raise ValueError("Uploaded data must be bytes")
        if len(file_bytes) > self._MAX_BYTES:
            raise ValueError("Uploaded image exceeds maximum size")

        if len(file_bytes) == 0:
            raise ValueError("Uploaded image is empty")

        normalized_kind = self._normalize_kind(kind)
        safe_target = self._normalize_component(target, "asset")
        safe_variant = self._normalize_component(variant, "default")
        normalized_extension = Path(filename).suffix.lower()

        if normalized_extension not in self._ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file extension: {normalized_extension}")

        if not self._safe_filename_component(filename):
            raise ValueError("Invalid filename")

        try:
            width, height, has_alpha = self._decode(file_bytes)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError("Uploaded data is not a valid image") from exc

        validation = self._build_validation(width, height, normalized_kind, has_alpha)
        renderable = (
            normalized_kind == "background"
            or (validation["ok"] and validation["reason"] == "ok")
        )

        asset_id = self._make_asset_id(normalized_kind, safe_target, safe_variant)
        round_token = self._safe_round_id(round_id)

        path = self._final_relpath(normalized_kind, asset_id, normalized_extension)
        staging_path = self._staging_relpath(round_token, normalized_kind, asset_id, normalized_extension)

        project_dir = self.pm._project_dir(project_name)
        destination = project_dir / staging_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(file_bytes)

        return {
            "asset_id": asset_id,
            "kind": normalized_kind,
            "target": safe_target,
            "variant": safe_variant,
            "source": "uploaded",
            "status": "uploaded",
            "path": path,
            "staging_path": staging_path,
            "preview_url": self._build_preview_url(project_name, staging_path),
            "placeholder": False,
            "renderable": renderable,
            "validation": validation,
        }
