"""ScriptRenderService — Ren'Py .rpy script generation.

Extracted from PrototypeGenerationService (P2-1) to isolate the script
rendering responsibility: character definitions, sprite transforms,
background image references, dialogue beats, and scene chaining.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from renpy_mcp.services.prototype_generation_service import (
    PrototypeScene,
    SpritePlanItem,
    _escape_renpy_string,
    _safe_character_id,
    _safe_image_tag,
    _to_renpy_asset_path,
)

if TYPE_CHECKING:
    from renpy_mcp.blueprint.models import ChapterSummary
    from renpy_mcp.services.project_manager import ProjectManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Path helpers (stateless, shared with PrototypeActivationService)
# ---------------------------------------------------------------------------

def staging_path_from_final(final_path: str) -> str:
    """Derive the staging path from a final prototype script path."""
    p = Path(final_path)
    return str(p.with_name(f"{p.stem}.__staging__{p.suffix}"))


def final_path_from_staging(staging_path: str) -> str:
    """Derive the final path from a staging prototype script path."""
    return staging_path.replace(".__staging__", "")


class ScriptRenderService:
    """Generate Ren'Py .rpy script files from prototype scene data.

    Responsibilities:
    - Character registry building (display name → safe Ren'Py identifier)
    - Sprite plan assignment (layout mode, transforms)
    - CJK font runtime override generation
    - Complete .rpy script rendering to a staging file
    """

    # Sprite layout definitions
    _SPRITE_LAYOUTS = {
        "solo": {
            "positions": ["center"],
            "transforms": ["proto_center_solo"],
        },
        "duo": {
            "positions": ["left", "right"],
            "transforms": ["proto_left_duo", "proto_right_duo"],
        },
        "trio": {
            "positions": ["left", "center", "right"],
            "transforms": ["proto_left_trio", "proto_center_trio", "proto_right_trio"],
        },
    }

    def __init__(self, pm: ProjectManager | None) -> None:
        self.pm = pm

    # ------------------------------------------------------------------
    # Character registry
    # ------------------------------------------------------------------

    def build_character_registry(self, scenes: list[PrototypeScene]) -> dict[str, str]:
        """Map display names to safe Ren'Py character identifiers.

        Only characters listed in characters_present are registered.
        Dialogue speakers not in this registry will fall back to narration.
        """
        registry: dict[str, str] = {}
        fallback_idx = 0
        for scene in scenes:
            for name in scene.characters_present:
                if name and name not in registry:
                    safe = _safe_character_id(name)
                    if not safe or safe in registry.values():
                        safe = f"char_{fallback_idx}"
                        fallback_idx += 1
                    registry[name] = safe
        return registry

    # ------------------------------------------------------------------
    # CJK runtime override
    # ------------------------------------------------------------------

    def cjk_runtime_override_lines(self) -> list[str]:
        """Return reusable runtime CJK font override lines."""
        return [
            "init python:",
            '    import os',
            '    _font_file = os.path.join(config.gamedir, "fonts", "simhei.ttf")',
            '    if os.path.exists(_font_file):',
            '        style.default.font = "fonts/simhei.ttf"',
            '        gui.text_font = "fonts/simhei.ttf"',
            '        gui.name_text_font = "fonts/simhei.ttf"',
            '        gui.interface_text_font = "fonts/simhei.ttf"',
            '        for _style_name in ("say_dialogue", "say_label", "namebox", "window", "input", "button_text", "hyperlink_text"):',
            '            try:',
            '                getattr(style, _style_name).font = "fonts/simhei.ttf"',
            '            except Exception:',
            '                pass',
            '        config.font_replacement_map["DejaVuSans.ttf"] = "fonts/simhei.ttf"',
            '        config.font_replacement_map["DejaVuSans-Bold.ttf"] = "fonts/simhei.ttf"',
            '        config.font_replacement_map["DejaVuSans-Oblique.ttf"] = "fonts/simhei.ttf"',
            '        config.font_replacement_map["DejaVuSans-BoldOblique.ttf"] = "fonts/simhei.ttf"',
        ]

    # ------------------------------------------------------------------
    # Sprite plan
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_layout_mode(char_count: int) -> str:
        if char_count == 1:
            return "solo"
        elif char_count == 2:
            return "duo"
        return "trio"

    @staticmethod
    def _character_subject_height_guidance(layout_mode: str) -> str:
        if layout_mode == "solo":
            return "subject occupies about 60-70% of frame height"
        if layout_mode == "duo":
            return "subject occupies about 50-60% of frame height"
        return "subject occupies about 45-55% of frame height"

    def build_sprite_plan(
        self,
        scenes: list[PrototypeScene],
        character_assets: dict[str, dict],
        project_name: str | None = None,
    ) -> None:
        """Assign sprite plans to each scene based on characters_present and available assets.

        Layout mode is determined by character count:
            1 character -> solo (center)
            2 characters -> duo (left, right)
            3+ characters -> trio (left, center, right)
        Each sprite gets a layout-specific transform that controls zoom,
        vertical anchor, and horizontal alignment.

        Sprites marked as unrenderable (placeholder, normalization failure,
        or quality gate rejection) are recorded but will not produce show
        statements in the generated script.
        """
        char_registry = self.build_character_registry(scenes)
        project_dir = self.pm._project_dir(project_name) if project_name and self.pm else None

        for scene in scenes:
            sprite_plan: list[SpritePlanItem] = []
            chars = scene.characters_present
            count = len(chars)
            layout_mode = self._resolve_layout_mode(count)
            layout = self._SPRITE_LAYOUTS[layout_mode]
            positions = layout["positions"]
            transforms = layout["transforms"]

            for idx, char_name in enumerate(chars):
                asset = character_assets.get(char_name, {})
                safe_id = char_registry.get(char_name) or _safe_character_id(char_name) or f"char_{idx}"
                sprite_path = asset.get("path")
                is_placeholder = asset.get("placeholder", True)
                # Backward-compatible default: non-placeholder assets without explicit
                # renderable field are assumed renderable (legacy test / caller path)
                is_renderable = asset.get("renderable", not is_placeholder) if not is_placeholder else False
                renderable_reason = asset.get("renderable_reason", "")

                # Additional gate: if the file doesn't actually exist, mark unrenderable
                # Prefer staging_path for existence check when available
                check_path = asset.get("staging_path") or sprite_path
                if check_path:
                    exists = False
                    if isinstance(check_path, Path):
                        exists = check_path.exists()
                    elif project_dir is not None:
                        exists = (project_dir / check_path).exists()
                    elif Path(check_path).is_absolute():
                        exists = Path(check_path).exists()
                    if not exists:
                        is_renderable = False
                        renderable_reason = "file_missing"

                sprite_plan.append(SpritePlanItem(
                    character_name=char_name,
                    character_id=safe_id,
                    sprite_path=str(sprite_path) if sprite_path else None,
                    sprite_check_path=str(check_path) if check_path else None,
                    sprite_placeholder=is_placeholder,
                    sprite_renderable=is_renderable,
                    sprite_quality_reason=renderable_reason,
                    position=positions[idx] if idx < len(positions) else positions[-1],
                    expression="neutral",
                    layout_mode=layout_mode,
                    transform_name=transforms[idx] if idx < len(transforms) else transforms[-1],
                ))
            scene.sprite_plan = sprite_plan

    # ------------------------------------------------------------------
    # Background path extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_bg_path(bg_asset: Any) -> Path | None:
        """Extract path from background asset (supports dict and legacy Path)."""
        if isinstance(bg_asset, dict):
            return bg_asset.get("path")
        if isinstance(bg_asset, Path):
            return bg_asset
        return None

    # ------------------------------------------------------------------
    # Script rendering
    # ------------------------------------------------------------------

    def write_script(
        self,
        project_name: str,
        chapter: ChapterSummary,
        scenes: list[PrototypeScene],
        background_assets: dict[str, Any] | None = None,
        character_assets: dict[str, dict] | None = None,
        cjk_font_config: dict | None = None,
        next_chapter_start_label: str | None = None,
    ) -> str:
        """Generate and write a minimal executable .rpy script skeleton to a staging file.

        The script is written to a staging path (e.g.
        "game/prototype_ch1.__staging__.rpy").  Callers must invoke
        commit_prototype_replacement() to promote it to the final path.

        Args:
            background_assets: Optional mapping of scene_id -> background asset info.
                Supports both new dict format {"path": Path, "placeholder": bool}
                and legacy Path format for backward compatibility.
            character_assets: Optional mapping of character_name -> {"path": Path, "placeholder": bool}.
            next_chapter_start_label: When the last scene in this chapter has no
                ``next_scene_id``, jump to this label instead of returning.  Used
                by the multi-chapter script generator to chain chapters.

        Returns:
            The staging relative file path.
        """
        if self.pm is None:
            raise RuntimeError("ProjectManager is required for script writeback")

        safe_name = "".join(c if c.isalnum() else "_" for c in chapter.name)
        file_name = f"prototype_{chapter.id}_{safe_name}.rpy"
        final_path = f"game/{file_name}"
        s_path = staging_path_from_final(final_path)

        project_dir = self.pm._project_dir(project_name)
        game_dir = project_dir / "game"
        game_dir.mkdir(parents=True, exist_ok=True)
        staging_file = game_dir / Path(s_path).name

        # Build character registry for safe say-statement generation
        char_registry = self.build_character_registry(scenes)

        lines: list[str] = []
        lines.append(f"# Prototype chapter: {chapter.name}")
        lines.append("")

        if cjk_font_config and cjk_font_config.get("configured"):
            lines.extend(self.cjk_runtime_override_lines())
            lines.append("")

        # Emit character definitions
        for display_name, safe_id in char_registry.items():
            escaped_name = _escape_renpy_string(display_name)
            lines.append(f'define {safe_id} = Character("{escaped_name}")')
        if char_registry:
            lines.append("")

        # Emit character sprite image definitions
        char_assets = character_assets or {}
        for char_name, asset in char_assets.items():
            # Prefer staging_path for existence check; emit path (final) in script
            check_path = asset.get("staging_path") or asset.get("path")
            char_exists = False
            if isinstance(check_path, Path):
                char_exists = check_path.exists()
            elif isinstance(check_path, str):
                char_exists = (project_dir / check_path).exists()
            emit_path = asset.get("path") or asset.get("staging_path")
            if emit_path and char_exists:
                rel_path = emit_path if isinstance(emit_path, str) else emit_path.relative_to(project_dir).as_posix()
                runtime_path = _to_renpy_asset_path(rel_path)
                safe_id = char_registry.get(char_name) or _safe_character_id(char_name) or "char_unknown"
                lines.append(f'image {safe_id}_neutral = "{runtime_path}"')
        if char_assets:
            lines.append("")

        # Emit prototype stage transforms for sprite layout
        lines.append("# Prototype stage transforms")
        lines.append("transform proto_center_solo:")
        lines.append("    xalign 0.5")
        lines.append("    yanchor 1.0")
        lines.append("    ypos 0.92")
        lines.append("    zoom 0.60")
        lines.append("")
        lines.append("transform proto_left_duo:")
        lines.append("    xalign 0.30")
        lines.append("    yanchor 1.0")
        lines.append("    ypos 0.92")
        lines.append("    zoom 0.48")
        lines.append("")
        lines.append("transform proto_right_duo:")
        lines.append("    xalign 0.70")
        lines.append("    yanchor 1.0")
        lines.append("    ypos 0.92")
        lines.append("    zoom 0.48")
        lines.append("")
        lines.append("transform proto_left_trio:")
        lines.append("    xalign 0.22")
        lines.append("    yanchor 1.0")
        lines.append("    ypos 0.92")
        lines.append("    zoom 0.40")
        lines.append("")
        lines.append("transform proto_center_trio:")
        lines.append("    xalign 0.5")
        lines.append("    yanchor 1.0")
        lines.append("    ypos 0.92")
        lines.append("    zoom 0.40")
        lines.append("")
        lines.append("transform proto_right_trio:")
        lines.append("    xalign 0.78")
        lines.append("    yanchor 1.0")
        lines.append("    ypos 0.92")
        lines.append("    zoom 0.40")
        lines.append("")

        # Emit image definitions for backgrounds
        bg_assets = background_assets or {}
        for scene in scenes:
            bg_asset = bg_assets.get(scene.scene_id)
            bg_path = self._extract_bg_path(bg_asset)
            # Prefer staging_path for existence check
            bg_staging = bg_asset.get("staging_path") if isinstance(bg_asset, dict) else None
            check_path = bg_staging or bg_path
            bg_exists = False
            if isinstance(check_path, Path):
                bg_exists = check_path.exists()
            elif isinstance(check_path, str):
                bg_exists = (project_dir / check_path).exists()
            emit_path = bg_path or bg_staging
            if emit_path and bg_exists:
                rel_path = emit_path if isinstance(emit_path, str) else emit_path.relative_to(project_dir).as_posix()
                runtime_path = _to_renpy_asset_path(rel_path)
                safe_tag = _safe_image_tag(scene.scene_id)
                lines.append(f'image bg_{safe_tag} = "{runtime_path}"')
        if bg_assets:
            lines.append("")

        for i, scene in enumerate(scenes):
            lines.append(f"label {scene.entry_label}:")
            # Use real background asset if available, else controlled fallback
            bg_asset = bg_assets.get(scene.scene_id)
            bg_path = self._extract_bg_path(bg_asset)
            bg_staging = bg_asset.get("staging_path") if isinstance(bg_asset, dict) else None
            check_path = bg_staging or bg_path
            safe_tag = _safe_image_tag(scene.scene_id)
            bg_exists = False
            if isinstance(check_path, Path):
                bg_exists = check_path.exists()
            elif isinstance(check_path, str):
                bg_exists = (project_dir / check_path).exists()
            if bg_path and bg_exists:
                lines.append(f"    scene bg_{safe_tag}")
            else:
                escaped_loc = _escape_renpy_string(scene.location)
                lines.append(f"    scene black  # PLACEHOLDER: {escaped_loc}")
            if scene.location:
                escaped_loc = _escape_renpy_string(scene.location)
                lines.append(f"    # 地点：{escaped_loc}")
            if scene.characters_present:
                chars = "、".join(scene.characters_present)
                escaped_chars = _escape_renpy_string(chars)
                lines.append(f"    # 登场角色：{escaped_chars}")
            # Show sprites for characters in this scene (only when renderable)
            shown_sprites: list[str] = []
            for sp in scene.sprite_plan:
                sprite_check_path = sp.sprite_check_path or sp.sprite_path
                sprite_abs = None
                if sprite_check_path:
                    sprite_abs = project_dir / sprite_check_path if not Path(sprite_check_path).is_absolute() else Path(sprite_check_path)
                if sp.sprite_renderable and sprite_abs and sprite_abs.exists():
                    safe_id = sp.character_id or char_registry.get(sp.character_name) or _safe_character_id(sp.character_name) or "char_unknown"
                    transform_name = sp.transform_name
                    lines.append(f"    show {safe_id}_neutral at {transform_name}")
                    shown_sprites.append(sp.character_name)
                elif sprite_abs and sprite_abs.exists() and not sp.sprite_renderable:
                    # Log why a sprite was suppressed (comment in script for debug)
                    reason = sp.sprite_quality_reason or "quality_gate"
                    lines.append(f"    # SUPPRESSED: {sp.character_name} sprite ({reason})")
            # Output dialogue beats as say statements
            for beat in scene.dialogue_beats:
                safe_id = char_registry.get(beat.speaker)
                line_text = beat.spoken_line or beat.content_brief
                escaped_brief = _escape_renpy_string(line_text)
                if safe_id:
                    lines.append(f'    {safe_id} "{escaped_brief}"')
                else:
                    lines.append(f'    "{escaped_brief}"  # UNKNOWN SPEAKER: {beat.speaker}')
            # If no dialogue beats, use summary as narration fallback
            if not scene.dialogue_beats:
                escaped_summary = _escape_renpy_string(scene.summary)
                lines.append(f'    "{escaped_summary}"')
            if scene.next_scene_id:
                next_scene = next((s for s in scenes if s.scene_id == scene.next_scene_id), None)
                if next_scene:
                    lines.append(f"    jump {next_scene.entry_label}")
                elif next_chapter_start_label:
                    lines.append(f"    jump {next_chapter_start_label}")
                else:
                    lines.append('    "To be continued..."')
                    lines.append("    return")
            else:
                if next_chapter_start_label:
                    lines.append(f"    jump {next_chapter_start_label}")
                else:
                    lines.append('    "End of prototype."')
                    lines.append("    return")
            lines.append("")

        staging_file.write_text("\n".join(lines), encoding="utf-8")
        return s_path
