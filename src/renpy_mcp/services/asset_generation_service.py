"""Asset generation service: background + character image generation.

Extracted from PrototypeGenerationService (P2-1) to isolate image asset
generation (backgrounds, character sprites, CJK fonts, quality gates)
into a focused, testable unit.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from renpy_mcp.blueprint.models import (
    GenerationContract,
    ProjectBlueprint,
)
from renpy_mcp.services.project_manager import ProjectManager

logger = logging.getLogger(__name__)

_CJK_FONT_DEST_NAME = "simhei.ttf"


class AssetGenerationService:
    """Background and character asset generation with fallback placeholders.

    Responsibilities:
    - Generate background images (via ImageService or PIL placeholder)
    - Generate character sprites (via ImageService + bg removal + normalize)
    - Background composition quality gate
    - CJK font configuration
    - Staging path rewriting for atomic promotion
    """

    def __init__(
        self,
        pm: ProjectManager | None,
        script_renderer: Any | None = None,
    ) -> None:
        self.pm = pm
        self._script_renderer = script_renderer

    # ------------------------------------------------------------------
    # Path utilities
    # ------------------------------------------------------------------

    def _runtime_asset_relpath(
        self, project_dir: Path, asset_path: Path, round_id: str | None = None
    ) -> str:
        """Return the final project-relative path for a generated asset.

        When an asset lives under game/__staging__/{round_id}/..., the runtime path
        must point at the eventual promoted game/... location, not the staging file.
        """
        rel = asset_path.relative_to(project_dir)
        if round_id:
            staging_root = Path("game") / "__staging__" / round_id
            if rel.parts[: len(staging_root.parts)] == staging_root.parts:
                rel = Path("game") / Path(*rel.parts[len(staging_root.parts) :])
        return rel.as_posix()

    # ------------------------------------------------------------------
    # Background composition quality gate
    # ------------------------------------------------------------------

    def _assess_background_composition(self, image_path: Path) -> tuple[bool, str]:
        """Reject obviously subject-heavy background plates.

        The goal is not semantic accuracy; it is a conservative guardrail against
        generated backgrounds that behave like key art with a dominant foreground
        subject, leaving no usable space for sprite compositing.
        """
        try:
            from collections import deque

            from PIL import Image, ImageFilter

            with Image.open(image_path) as img:
                gray = img.convert("L").resize((128, 72), Image.Resampling.LANCZOS)
                edges = gray.filter(ImageFilter.FIND_EDGES).filter(
                    ImageFilter.MaxFilter(5)
                )
                px = edges.load()
                width, height = edges.size
                threshold = 52
                binary = [
                    [1 if px[x, y] >= threshold else 0 for x in range(width)]
                    for y in range(height)
                ]

                def _density(x0: int, x1: int, y0: int, y1: int) -> float:
                    total = max(1, (x1 - x0) * (y1 - y0))
                    count = 0
                    for yy in range(y0, y1):
                        row = binary[yy]
                        count += sum(row[x0:x1])
                    return count / total

                visited = [[False] * width for _ in range(height)]
                largest_component = 0
                largest_bbox = (0, 0, 0, 0)
                min_x = int(width * 0.15)
                max_x = int(width * 0.85)
                min_y = int(height * 0.10)
                max_y = int(height * 0.97)

                for y in range(min_y, max_y):
                    for x in range(min_x, max_x):
                        if not binary[y][x] or visited[y][x]:
                            continue
                        q = deque([(x, y)])
                        visited[y][x] = True
                        area = 0
                        left = right = x
                        top = bottom = y
                        while q:
                            cx, cy = q.popleft()
                            area += 1
                            left = min(left, cx)
                            right = max(right, cx)
                            top = min(top, cy)
                            bottom = max(bottom, cy)
                            for nx, ny in (
                                (cx - 1, cy),
                                (cx + 1, cy),
                                (cx, cy - 1),
                                (cx, cy + 1),
                            ):
                                if (
                                    min_x <= nx < max_x
                                    and min_y <= ny < max_y
                                    and binary[ny][nx]
                                    and not visited[ny][nx]
                                ):
                                    visited[ny][nx] = True
                                    q.append((nx, ny))
                        if area > largest_component:
                            largest_component = area
                            largest_bbox = (left, top, right, bottom)

                focus_density = _density(
                    int(width * 0.18),
                    int(width * 0.82),
                    int(height * 0.15),
                    int(height * 0.95),
                )
                lower_focus_density = _density(
                    int(width * 0.18),
                    int(width * 0.82),
                    int(height * 0.45),
                    int(height * 0.98),
                )
                peripheral_density = (
                    _density(0, int(width * 0.15), 0, height)
                    + _density(int(width * 0.85), width, 0, height)
                    + _density(0, width, 0, int(height * 0.18))
                ) / 3.0

                comp_ratio = largest_component / max(1, width * height)
                bbox_w = max(0, largest_bbox[2] - largest_bbox[0] + 1)
                bbox_h = max(0, largest_bbox[3] - largest_bbox[1] + 1)
                if (
                    comp_ratio > 0.11
                    and bbox_w / width > 0.24
                    and bbox_h / height > 0.34
                    and lower_focus_density > 0.14
                ):
                    return False, "dominant_foreground_subject"
                if (
                    focus_density > 0.19
                    and focus_density > peripheral_density * 1.55
                    and lower_focus_density > 0.13
                ):
                    return False, "foreground_too_busy"
        except Exception as exc:
            logger.warning(
                "Background composition assessment failed for %s: %s",
                image_path,
                exc,
            )
        return True, "ok"

    # ------------------------------------------------------------------
    # Placeholder generators
    # ------------------------------------------------------------------

    def _generate_placeholder_background(self, file_path: Path, scene: Any) -> None:
        """Generate a simple colored placeholder background using PIL."""
        from PIL import Image, ImageDraw

        mood_colors: dict[str, tuple[int, int, int]] = {
            "\u60b2\u6006": (30, 30, 50),
            "\u7d27\u5f20": (50, 20, 20),
            "\u538b\u8feb": (20, 20, 20),
            "\u77ed\u6682\u6e29\u6696": (60, 40, 30),
            "\u6000\u7591": (30, 40, 30),
        }
        base_color = mood_colors.get(scene.mood, (25, 25, 35))

        img = Image.new("RGB", (1280, 720), color=base_color)
        draw = ImageDraw.Draw(img)

        for y in range(0, 720, 4):
            shade = int((y / 720) * 30)
            draw.line(
                [(0, y), (1280, y)],
                fill=(
                    min(255, base_color[0] + shade),
                    min(255, base_color[1] + shade),
                    min(255, base_color[2] + shade),
                ),
            )

        draw.text((20, 20), f"{scene.location}", fill=(200, 200, 200))
        draw.text((20, 50), f"{scene.mood}", fill=(180, 180, 180))

        file_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(file_path, "PNG")

    def _generate_placeholder_character(self, file_path: Path, char_name: str) -> None:
        """Generate a transparent placeholder character sprite using PIL."""
        from PIL import Image, ImageDraw

        img = Image.new("RGBA", (400, 750), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), f"{char_name}", fill=(200, 200, 200, 255))
        draw.text((20, 50), "SPRITE PLACEHOLDER", fill=(180, 180, 180, 255))

        file_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(file_path, "PNG")

    # ------------------------------------------------------------------
    # Background asset generation
    # ------------------------------------------------------------------

    async def generate_background_assets(
        self,
        project_name: str,
        scenes: list,
        round_id: str | None = None,
        contract: GenerationContract | None = None,
    ) -> dict[str, dict]:
        """Generate background images for each scene.

        Tries ImageService first; falls back to PIL placeholder on failure.
        """
        if self.pm is None:
            raise RuntimeError("ProjectManager is required for asset generation")

        project_dir = self.pm._project_dir(project_name)
        bg_dir = project_dir / "game" / "images" / "background"
        bg_dir.mkdir(parents=True, exist_ok=True)

        staging_bg_dir: Path | None = None
        if round_id:
            staging_bg_dir = (
                project_dir
                / "game"
                / "__staging__"
                / round_id
                / "images"
                / "background"
            )
            staging_bg_dir.mkdir(parents=True, exist_ok=True)

        result: dict[str, dict] = {}
        for scene in scenes:
            file_name = f"bg_{scene.scene_id}.png"
            final_path = bg_dir / file_name
            staging_path = staging_bg_dir / file_name if staging_bg_dir else final_path

            rel_final = str(final_path.relative_to(project_dir).as_posix())
            rel_staging = (
                str(staging_path.relative_to(project_dir).as_posix())
                if staging_bg_dir
                else None
            )

            old_backup: Path | None = None
            if round_id and final_path.exists():
                old_backup = (
                    project_dir
                    / "game"
                    / "__staging__"
                    / round_id
                    / "__backup__"
                    / file_name
                )
                old_backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(final_path, old_backup)

            image_generated = False
            gate_rejected = False
            try:
                from renpy_mcp.ai.image_service import ImageService
                from renpy_mcp.config import get_settings

                settings = get_settings()
                image_service = ImageService(settings)
                if image_service.is_available():
                    prompt_parts: list[str] = []
                    if contract is not None:
                        vc = contract.visual_contract
                        if vc.art_direction:
                            prompt_parts.append(f"Art direction: {vc.art_direction}.")
                        if vc.camera_language:
                            prompt_parts.append(
                                f"Camera language: {vc.camera_language}."
                            )
                        if vc.palette_baseline:
                            prompt_parts.append(
                                f"Palette baseline: {vc.palette_baseline}."
                            )
                        if vc.mood_target:
                            prompt_parts.append(f"Mood: {vc.mood_target}.")
                        if vc.lighting_bias:
                            prompt_parts.append(f"Lighting: {vc.lighting_bias}.")
                        if vc.temperature_bias:
                            prompt_parts.append(f"Temperature: {vc.temperature_bias}.")
                    prompt_parts.append(f"Background: {scene.location}.")
                    prompt_parts.append(f"Visual: {scene.location_visual_brief}.")
                    if not contract or not contract.visual_contract.mood_target:
                        prompt_parts.append(f"Mood: {scene.mood}.")
                    prompt_parts.append(
                        "Visual novel background plate, 16:9, no characters, no text, no giant statues, "
                        "no giant masks, no close foreground props, no dominant central subject, "
                        "keep the lower foreground visually open for foreground sprites."
                    )
                    bg_prompt = " ".join(prompt_parts)
                    gen_result = await image_service.generate_image(
                        project_dir=project_dir,
                        prompt=bg_prompt,
                        image_type="background",
                        base_name=f"bg_{scene.scene_id}",
                    )
                    if gen_result.success and gen_result.primary_file:
                        generated = gen_result.primary_file
                        gate_check_path = generated
                        if round_id and staging_bg_dir:
                            shutil.move(str(generated), str(staging_path))
                            if old_backup and old_backup.exists():
                                shutil.copy2(old_backup, final_path)
                            gate_check_path = staging_path
                        passes_gate, gate_reason = (
                            self._assess_background_composition(gate_check_path)
                        )
                        if not passes_gate:
                            gate_rejected = True
                            logger.warning(
                                "Generated background for %s warned by composition gate but kept for runtime: %s",
                                scene.scene_id,
                                gate_reason,
                            )
                        if round_id and staging_bg_dir:
                            result[scene.scene_id] = {
                                "path": rel_final,
                                "staging_path": rel_staging,
                                "placeholder": False,
                                "source": "image_service",
                                "is_new_file": True,
                            }
                        else:
                            result[scene.scene_id] = {
                                "path": generated,
                                "placeholder": False,
                                "source": "image_service",
                                "is_new_file": True,
                            }
                        image_generated = True
            except Exception as exc:
                logger.warning(
                    "ImageService background generation failed for %s: %s",
                    scene.scene_id,
                    exc,
                )

            if not image_generated:
                try:
                    self._generate_placeholder_background(staging_path, scene)
                    if round_id and staging_bg_dir:
                        result[scene.scene_id] = {
                            "path": rel_final,
                            "staging_path": rel_staging,
                            "placeholder": True,
                            "source": "composition_warned_fallback"
                            if gate_rejected
                            else "pil_fallback",
                            "is_new_file": True,
                        }
                    else:
                        result[scene.scene_id] = {
                            "path": staging_path,
                            "placeholder": True,
                            "source": "composition_warned_fallback"
                            if gate_rejected
                            else "pil_fallback",
                            "is_new_file": True,
                        }
                except Exception as exc:
                    logger.warning(
                        "PIL placeholder generation failed for %s: %s",
                        scene.scene_id,
                        exc,
                    )
                    result[scene.scene_id] = {
                        "path": None,
                        "staging_path": None,
                        "placeholder": True,
                        "source": "none",
                        "is_new_file": False,
                    }

        return result

    # ------------------------------------------------------------------
    # Character sprite asset generation
    # ------------------------------------------------------------------

    async def generate_character_assets(
        self,
        project_name: str,
        blueprint: ProjectBlueprint,
        scenes: list,
        round_id: str | None = None,
        contract: GenerationContract | None = None,
    ) -> dict[str, dict]:
        """Generate character sprite images for all characters in prototype scenes.

        Tries ImageService first; falls back to PIL placeholder on failure.
        Attempts background removal via BackgroundRemover when available.
        Post-processes sprites with normalize_sprite for consistent baseline.
        """
        from renpy_mcp.services.prototype_generation_service import _safe_character_id

        if self.pm is None:
            raise RuntimeError("ProjectManager is required for asset generation")

        project_dir = self.pm._project_dir(project_name)
        char_dir = project_dir / "game" / "images" / "character"
        char_dir.mkdir(parents=True, exist_ok=True)

        staging_char_dir: Path | None = None
        if round_id:
            staging_char_dir = (
                project_dir
                / "game"
                / "__staging__"
                / round_id
                / "images"
                / "character"
            )
            staging_char_dir.mkdir(parents=True, exist_ok=True)

        unique_chars: set[str] = set()
        for scene in scenes:
            for name in scene.characters_present:
                unique_chars.add(name)

        char_info: dict[str, dict] = {}
        for c in blueprint.characters:
            char_info[c.name] = {
                "appearance": c.appearance,
                "personality": c.personality,
            }

        char_scene_context: dict[str, dict] = {}
        for char_name in unique_chars:
            for scene in scenes:
                if char_name in scene.characters_present:
                    char_scene_context[char_name] = {
                        "location": scene.location,
                        "location_visual_brief": scene.location_visual_brief,
                        "mood": scene.mood,
                        "character_count": len(scene.characters_present),
                    }
                    break

        result: dict[str, dict] = {}

        # Use script_renderer for character registry if available
        if self._script_renderer is not None:
            char_registry = self._script_renderer.build_character_registry(scenes)
        else:
            char_registry = {}

        for char_name in unique_chars:
            safe_id = (
                char_registry.get(char_name)
                or _safe_character_id(char_name)
                or "char_unknown"
            )
            file_name = f"{safe_id}_neutral.png"
            final_path = char_dir / file_name
            staging_path = (
                staging_char_dir / file_name if staging_char_dir else final_path
            )

            rel_final = str(final_path.relative_to(project_dir).as_posix())
            rel_staging = (
                str(staging_path.relative_to(project_dir).as_posix())
                if staging_char_dir
                else None
            )

            info = char_info.get(char_name, {})
            appearance = info.get("appearance", "anime character")
            personality = info.get("personality", "")
            ctx = char_scene_context.get(char_name, {})

            # Resolve layout mode via script_renderer or fallback
            if self._script_renderer is not None:
                layout_mode = self._script_renderer._resolve_layout_mode(
                    ctx.get("character_count", 1)
                )
                subject_height_guidance = (
                    self._script_renderer._character_subject_height_guidance(
                        layout_mode
                    )
                )
            else:
                layout_mode = "solo"
                subject_height_guidance = "character should occupy about 70-80% of image height"

            framing = (
                "medium shot"
                if layout_mode == "solo"
                else (
                    "medium shot"
                    if layout_mode == "duo"
                    else "medium-long shot"
                )
            )

            prompt_parts: list[str] = []
            prompt_parts.append(f"Portrait of {char_name}.")

            identity_anchors: list[str] = []
            default_costume: str = ""
            if contract is not None:
                for char_entry in contract.character_contract.characters:
                    if char_entry.name == char_name:
                        identity_anchors = char_entry.identity_anchors
                        default_costume = char_entry.default_costume
                        break

            if identity_anchors:
                prompt_parts.append(
                    f"Identity anchors: {', '.join(identity_anchors)}."
                )
            if default_costume:
                prompt_parts.append(f"Costume: {default_costume}.")
            if not identity_anchors:
                prompt_parts.append(f"Appearance: {appearance}.")
            if personality:
                prompt_parts.append(f"Personality: {personality}.")

            prompt_parts.append(f"Scene setting: {ctx.get('location', 'unknown')}.")
            prompt_parts.append(
                f"Visual direction: {ctx.get('location_visual_brief', '')}."
            )

            mood_text = ctx.get("mood", "neutral")
            lighting_text = ""
            art_direction_text = ""
            if contract is not None:
                vc = contract.visual_contract
                if vc.mood_target:
                    mood_text = vc.mood_target
                if vc.lighting_bias:
                    lighting_text = vc.lighting_bias
                if vc.temperature_bias:
                    lighting_text = (
                        f"{lighting_text}, {vc.temperature_bias}"
                        if lighting_text
                        else vc.temperature_bias
                    )
                if vc.art_direction:
                    art_direction_text = vc.art_direction

            prompt_parts.append(f"Mood: {mood_text}.")
            if lighting_text:
                prompt_parts.append(f"Lighting: {lighting_text}.")
            if art_direction_text:
                prompt_parts.append(f"Art direction: {art_direction_text}.")

            prompt_parts.append(f"Camera framing: {framing}, centered on character.")
            prompt_parts.append(
                "Visual novel character sprite style, one person only, single character, "
                "standing pose, facing viewer, centered composition, white/plain background, minimal background, "
                f"full body visible, clean line art, anime style, {subject_height_guidance}, "
                "comfortable margin around the character, leave breathing room above the head and around the body. "
                "No environment scene, no street, no room, no architecture, no skyline, no vehicles, no landscape. "
                "Do not generate a poster, wide shot, cinematic environment plate, or character with scenery. "
                "Not a close-up. No oversized character dominating the frame. "
                "Same art direction, lighting, and color palette as the scene background. "
                "Matching atmosphere for seamless visual novel composition."
            )
            char_prompt = " ".join(prompt_parts)

            intermediate_paths: list[str] = []
            image_generated = False
            generated_path: Path | None = None
            bg_removed = False

            old_backup: Path | None = None
            if round_id and final_path.exists():
                old_backup = (
                    project_dir
                    / "game"
                    / "__staging__"
                    / round_id
                    / "__backup__"
                    / file_name
                )
                old_backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(final_path, old_backup)

            try:
                from renpy_mcp.ai.image_service import ImageService
                from renpy_mcp.config import get_settings

                settings = get_settings()
                image_service = ImageService(settings)
                if image_service.is_available():
                    gen_result = await image_service.generate_image(
                        project_dir=project_dir,
                        prompt=char_prompt,
                        image_type="character",
                        base_name=f"{safe_id}_neutral",
                    )
                    if gen_result.success and gen_result.primary_file:
                        raw_generated = gen_result.primary_file
                        if round_id and staging_char_dir:
                            shutil.move(str(raw_generated), str(staging_path))
                            if old_backup and old_backup.exists():
                                shutil.copy2(old_backup, final_path)
                            generated_path = staging_path
                            intermediate_paths.append(rel_staging)
                        else:
                            generated_path = raw_generated

                        transparent_path: Path | None = None
                        try:
                            from renpy_mcp.ai.background_remover import (
                                BackgroundRemover,
                            )

                            remover = BackgroundRemover()
                            transparent_path = remover.remove_background(
                                generated_path
                            )
                        except Exception as exc:
                            logger.warning(
                                "Background removal failed for %s: %s",
                                char_name,
                                exc,
                            )

                        if transparent_path and transparent_path.exists():
                            if (
                                round_id
                                and staging_char_dir
                                and not str(transparent_path).startswith(
                                    str(staging_char_dir)
                                )
                            ):
                                dest = staging_char_dir / transparent_path.name
                                shutil.move(str(transparent_path), str(dest))
                                transparent_path = dest
                                intermediate_paths.append(
                                    str(
                                        dest.relative_to(project_dir).as_posix()
                                    )
                                )
                            elif round_id and staging_char_dir:
                                rel_tp = str(
                                    transparent_path.relative_to(
                                        project_dir
                                    ).as_posix()
                                )
                                if rel_tp not in intermediate_paths:
                                    intermediate_paths.append(rel_tp)
                            generated_path = transparent_path
                            bg_removed = True
                        image_generated = True
            except Exception as exc:
                logger.warning(
                    "Character image generation failed for %s: %s", char_name, exc
                )

            # Post-process: normalize sprite for consistent baseline
            normalized_path: Path | None = None
            norm_meta: dict = {}
            if image_generated and generated_path and generated_path.exists():
                try:
                    from renpy_mcp.ai.background_remover import BackgroundRemover

                    remover = BackgroundRemover()
                    norm_output = (
                        staging_char_dir / f"{safe_id}_normalized.png"
                        if round_id and staging_char_dir
                        else char_dir / f"{safe_id}_normalized.png"
                    )
                    normalized_path, norm_meta = remover.normalize_sprite(
                        generated_path,
                        output_path=norm_output,
                    )
                    if (
                        normalized_path
                        and normalized_path.exists()
                        and round_id
                        and staging_char_dir
                    ):
                        rel_np = str(
                            normalized_path.relative_to(project_dir).as_posix()
                        )
                        if rel_np not in intermediate_paths:
                            intermediate_paths.append(rel_np)
                except Exception as exc:
                    logger.warning(
                        "Sprite normalization failed for %s: %s", char_name, exc
                    )

            final_sprite_path = (
                normalized_path
                if normalized_path and normalized_path.exists()
                else generated_path
            )
            if final_sprite_path is None or not final_sprite_path.exists():
                final_sprite_path = None

            if not image_generated or final_sprite_path is None:
                try:
                    self._generate_placeholder_character(staging_path, char_name)
                    if round_id and staging_char_dir:
                        result[char_name] = {
                            "path": rel_final,
                            "staging_path": rel_staging,
                            "placeholder": True,
                            "renderable": False,
                            "renderable_reason": "placeholder_fallback",
                            "bbox": None,
                            "baseline_offset": 0,
                            "is_new_file": True,
                            "intermediate_paths": intermediate_paths,
                        }
                    else:
                        result[char_name] = {
                            "path": rel_final,
                            "placeholder": True,
                            "renderable": False,
                            "renderable_reason": "placeholder_fallback",
                            "bbox": None,
                            "baseline_offset": 0,
                            "is_new_file": True,
                            "intermediate_paths": intermediate_paths,
                        }
                except Exception as exc:
                    logger.warning(
                        "Character placeholder generation failed for %s: %s",
                        char_name,
                        exc,
                    )
                    result[char_name] = {
                        "path": None,
                        "staging_path": None,
                        "placeholder": True,
                        "renderable": False,
                        "renderable_reason": "generation_failed",
                        "bbox": None,
                        "baseline_offset": 0,
                        "is_new_file": False,
                        "intermediate_paths": intermediate_paths,
                    }
            else:
                renderable = norm_meta.get("renderable", True)
                reason = norm_meta.get("reason", "ok")
                if not bg_removed:
                    renderable = False
                    reason = "background_removal_failed"
                if not renderable:
                    logger.info(
                        "Sprite for %s marked unrenderable: %s", char_name, reason
                    )

                runtime_rel = self._runtime_asset_relpath(
                    project_dir, final_sprite_path, round_id
                )
                staging_rel = str(
                    final_sprite_path.relative_to(project_dir).as_posix()
                )
                if round_id and staging_char_dir:
                    result[char_name] = {
                        "path": runtime_rel,
                        "staging_path": staging_rel,
                        "placeholder": False,
                        "renderable": renderable,
                        "renderable_reason": reason,
                        "bbox": norm_meta.get("bbox"),
                        "baseline_offset": norm_meta.get("baseline_offset", 0),
                        "is_new_file": True,
                        "intermediate_paths": intermediate_paths,
                    }
                else:
                    result[char_name] = {
                        "path": runtime_rel,
                        "placeholder": False,
                        "renderable": renderable,
                        "renderable_reason": reason,
                        "bbox": norm_meta.get("bbox"),
                        "baseline_offset": norm_meta.get("baseline_offset", 0),
                        "is_new_file": True,
                        "intermediate_paths": intermediate_paths,
                    }

        return result

    # ------------------------------------------------------------------
    # CJK font configuration
    # ------------------------------------------------------------------

    def ensure_cjk_font_config(
        self, project_name: str, round_id: str | None = None
    ) -> dict:
        """Ensure the project has CJK-safe font configuration.

        Copies a system CJK font into the project and writes a Ren'Py config
        file that references it.  The config is only enabled when the font
        file actually exists so the runtime never references a missing file.

        Returns:
            dict with keys: configured (bool), font_path (str | None), config_path (str)
        """
        from renpy_mcp.services.prototype_generation_service import resolve_cjk_font_path

        if self.pm is None:
            raise RuntimeError("ProjectManager is required for font configuration")

        project_dir = self.pm._project_dir(project_name)
        fonts_dir = project_dir / "game" / "fonts"
        fonts_dir.mkdir(parents=True, exist_ok=True)

        staging_root = (
            project_dir / "game" / "__staging__" / round_id if round_id else None
        )
        if staging_root:
            staging_root.mkdir(parents=True, exist_ok=True)

        font_dest = fonts_dir / _CJK_FONT_DEST_NAME
        staged_font_dest = (
            staging_root / "fonts" / _CJK_FONT_DEST_NAME if staging_root else None
        )
        configured = False
        new_files: list[str] = []

        font_source = resolve_cjk_font_path()
        if font_source is not None and not font_dest.exists():
            try:
                target_font_path = staged_font_dest or font_dest
                target_font_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(font_source, target_font_path)
                configured = True
                new_files.append(
                    str(target_font_path.relative_to(project_dir).as_posix())
                )
            except OSError as exc:
                logger.warning("Failed to copy CJK font: %s", exc)
        elif font_dest.exists():
            configured = True

        runtime_config_rel = "game/prototype_fonts.rpy"
        config_path = (
            (staging_root / "prototype_fonts.rpy")
            if staging_root
            else (project_dir / runtime_config_rel)
        )
        if font_dest.exists() or (staged_font_dest and staged_font_dest.exists()):
            lines = [
                "# Auto-generated CJK font configuration for prototype",
                "# Uses init python so the overrides apply AFTER gui.rpy defaults load.",
            ]
            if self._script_renderer is not None:
                lines.extend(self._script_renderer.cjk_runtime_override_lines())
            config_path.write_text("\n".join(lines), encoding="utf-8")
        else:
            config_path.write_text(
                "# Auto-generated CJK font configuration for prototype\n"
                "# Font file not available -- CJK fallback disabled.\n",
                encoding="utf-8",
            )
        new_files.append(str(config_path.relative_to(project_dir).as_posix()))

        return {
            "configured": configured,
            "font_path": (Path("game") / "fonts" / _CJK_FONT_DEST_NAME).as_posix()
            if (font_dest.exists() or (staged_font_dest and staged_font_dest.exists()))
            else None,
            "config_path": runtime_config_rel,
            "new_files": new_files,
        }
