"""Prototype generation service: from confirmed blueprint to playable scene skeleton."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from renpy_mcp.blueprint.models import ChapterSummary, ProjectBlueprint
from renpy_mcp.services.project_manager import ProjectManager

logger = logging.getLogger(__name__)

_CJK_FONT_SOURCE = Path(r"C:\Windows\Fonts\simhei.ttf")
_CJK_FONT_DEST_NAME = "simhei.ttf"


class DialogueBeat(BaseModel):
    """A single dialogue beat within a scene."""

    speaker: str
    intent: str
    content_brief: str


class PrototypeScene(BaseModel):
    """A detailed scene generated for the prototype chapter."""

    scene_id: str
    title: str
    summary: str
    location: str
    location_visual_brief: str = ""
    mood: str = ""
    characters_present: list[str] = Field(default_factory=list)
    dialogue_beats: list[DialogueBeat] = Field(default_factory=list)
    entry_label: str
    next_scene_id: str | None = None


class PrototypeGenerationService:
    """Generate a minimum playable prototype from a confirmed blueprint."""

    def __init__(self, pm: ProjectManager | None, provider: Any | None) -> None:
        self.pm = pm
        self.provider = provider

    # ------------------------------------------------------------------
    # Chapter selection
    # ------------------------------------------------------------------

    def select_prototype_chapter(self, blueprint: ProjectBlueprint) -> ChapterSummary:
        """Return the first chapter as the prototype chapter.

        Raises:
            ValueError: If the blueprint has no chapters.
        """
        if not blueprint.chapters:
            raise ValueError("Blueprint has no chapters")
        return blueprint.chapters[0]

    # ------------------------------------------------------------------
    # Scene generation (LLM)
    # ------------------------------------------------------------------

    def _validate_scene_consistency(self, scenes: list[PrototypeScene]) -> None:
        """Validate and auto-correct scene consistency rules.

        Rules enforced:
        1. dialogue_beats.speaker must belong to characters_present.
        2. location_visual_brief must not be empty.
        3. mood must not be empty.
        """
        for scene in scenes:
            # Rule 1: speakers must be in characters_present
            valid_speakers = set(scene.characters_present)
            filtered_beats: list[DialogueBeat] = []
            for beat in scene.dialogue_beats:
                if beat.speaker in valid_speakers:
                    filtered_beats.append(beat)
            scene.dialogue_beats = filtered_beats

            # Rule 2: location_visual_brief fallback
            if not scene.location_visual_brief.strip():
                scene.location_visual_brief = scene.location

            # Rule 3: mood fallback
            if not scene.mood.strip():
                scene.mood = "neutral"

    async def generate_scenes(
        self, chapter: ChapterSummary, blueprint: ProjectBlueprint
    ) -> list[PrototypeScene]:
        """Generate 2-4 structured scenes for the prototype chapter via LLM.

        Args:
            chapter: The prototype chapter selected from the blueprint.
            blueprint: The full confirmed blueprint.

        Returns:
            List of structured PrototypeScene objects.

        Raises:
            RuntimeError: If the provider is not configured or fails.
            ValueError: If the provider response cannot be parsed into valid scenes.
        """
        if self.provider is None:
            raise RuntimeError("No LLM provider configured for prototype generation.")

        characters_desc = "\n".join(
            f"- {c.name} ({c.role}): {c.personality}, {c.appearance}"
            for c in blueprint.characters
        )

        prompt = f"""Based on the following blueprint, generate 2-4 detailed scenes for the prototype chapter.

Project: {blueprint.title}
Genre: {blueprint.genre}
Worldview: {blueprint.worldview}
Themes: {', '.join(blueprint.themes)}

Characters:
{characters_desc}

Prototype Chapter: {chapter.name}

Generate a JSON array of scenes. Each scene must have these fields:
- scene_id: unique identifier string
- title: scene title
- summary: 1-2 sentence narration summary
- location: setting name (e.g., "library", "cafe")
- location_visual_brief: visual description for background generation (e.g., "被火焰吞噬的村庄废墟，夜色、残墙、余烬、低能见度")
- mood: emotional tone of the scene (e.g., "悲怆", "紧张", "压迫", "短暂温暖", "怀疑")
- characters_present: list of character names appearing in this scene
- dialogue_beats: array of dialogue beats, each with:
  - speaker: character name (must be in characters_present)
  - intent: what the character is trying to do or feel
  - content_brief: brief description of what they say
- entry_label: Ren'Py label name for this scene (e.g., "prototype_ch1_start")
- next_scene_id: scene_id of the next scene, or null for the last scene

Consistency rules:
- Every dialogue_beats.speaker MUST be in characters_present.
- The mood must be reflected in both the location_visual_brief and the dialogue beats.
- If the location changes between scenes, the visual brief must also change.

Requirements:
- 2 to 4 scenes total
- Linear flow: each scene (except last) points to the next
- Last scene has next_scene_id = null
- Output ONLY the JSON array, nothing else.
"""

        max_retries = 2
        last_error: str | None = None

        for attempt in range(max_retries + 1):
            try:
                response = await asyncio.to_thread(
                    self.provider.chat,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4096,
                )
            except Exception as e:
                raise RuntimeError(f"Prototype generation provider error: {e}") from e

            try:
                text = response.text.strip()
                # Extract JSON from markdown code blocks if present
                if text.startswith("```"):
                    lines = text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    text = "\n".join(lines).strip()

                data = json.loads(text)
                if not isinstance(data, list):
                    raise ValueError("Expected JSON array of scenes")

                scenes = [PrototypeScene(**item) for item in data]
                self._validate_scene_consistency(scenes)
                return scenes

            except json.JSONDecodeError as e:
                last_error = f"JSON parse error: {e}"
                prompt += f"\n\nERROR: Your previous response was not valid JSON ({e}). Return ONLY a valid JSON array."
            except (ValidationError, ValueError) as e:
                last_error = f"Schema validation error: {e}"
                prompt += f"\n\nERROR: Your previous response did not match the required scene schema ({e}). Fix and return a valid JSON array."

        raise RuntimeError(
            f"Prototype scene generation failed after {max_retries + 1} attempts. {last_error}"
        )

    # ------------------------------------------------------------------
    # Script writeback
    # ------------------------------------------------------------------

    def _staging_path_from_final(self, final_path: str) -> str:
        """Derive the staging path from a final prototype script path."""
        p = Path(final_path)
        return str(p.with_name(f"{p.stem}.__staging__{p.suffix}"))

    def _final_path_from_staging(self, staging_path: str) -> str:
        """Derive the final path from a staging prototype script path."""
        return staging_path.replace(".__staging__", "")

    # ------------------------------------------------------------------
    # Background asset generation
    # ------------------------------------------------------------------

    async def generate_background_assets(
        self, project_name: str, scenes: list[PrototypeScene]
    ) -> dict[str, Path]:
        """Generate background images for each scene.

        Tries ImageService first; falls back to PIL placeholder on failure.
        Returns a mapping of scene_id -> background file path.
        """
        if self.pm is None:
            raise RuntimeError("ProjectManager is required for asset generation")

        project_dir = self.pm._project_dir(project_name)
        bg_dir = project_dir / "game" / "images" / "background"
        bg_dir.mkdir(parents=True, exist_ok=True)

        result: dict[str, Path] = {}
        for scene in scenes:
            file_name = f"bg_{scene.scene_id}.png"
            file_path = bg_dir / file_name

            # Try ImageService if available
            image_generated = False
            try:
                from renpy_mcp.config import get_settings
                from renpy_mcp.ai.image_service import ImageService

                settings = get_settings()
                image_service = ImageService(settings)
                if image_service.is_available():
                    bg_prompt = (
                        f"Background: {scene.location}. "
                        f"Visual: {scene.location_visual_brief}. "
                        f"Mood: {scene.mood}. "
                        "Visual novel background style, 16:9, no characters, no text."
                    )
                    gen_result = await image_service.generate_image(
                        project_dir=project_dir,
                        prompt=bg_prompt,
                        image_type="background",
                        base_name=f"bg_{scene.scene_id}",
                    )
                    if gen_result.success and gen_result.primary_file:
                        result[scene.scene_id] = gen_result.primary_file
                        image_generated = True
            except Exception as exc:
                logger.warning("ImageService background generation failed for %s: %s", scene.scene_id, exc)

            if not image_generated:
                # Fallback: generate a simple placeholder with PIL
                try:
                    self._generate_placeholder_background(file_path, scene)
                    result[scene.scene_id] = file_path
                except Exception as exc:
                    logger.warning("PIL placeholder generation failed for %s: %s", scene.scene_id, exc)

        return result

    def _generate_placeholder_background(self, file_path: Path, scene: PrototypeScene) -> None:
        """Generate a simple colored placeholder background using PIL."""
        from PIL import Image, ImageDraw

        # Map mood to base color
        mood_colors: dict[str, tuple[int, int, int]] = {
            "悲怆": (30, 30, 50),
            "紧张": (50, 20, 20),
            "压迫": (20, 20, 20),
            "短暂温暖": (60, 40, 30),
            "怀疑": (30, 40, 30),
        }
        base_color = mood_colors.get(scene.mood, (25, 25, 35))

        img = Image.new("RGB", (1280, 720), color=base_color)
        draw = ImageDraw.Draw(img)

        # Add a subtle gradient-like overlay
        for y in range(0, 720, 4):
            shade = int((y / 720) * 30)
            draw.line([(0, y), (1280, y)], fill=(
                min(255, base_color[0] + shade),
                min(255, base_color[1] + shade),
                min(255, base_color[2] + shade),
            ))

        # Add scene location text as watermark
        draw.text((20, 20), f"{scene.location}", fill=(200, 200, 200))
        draw.text((20, 50), f"{scene.mood}", fill=(180, 180, 180))

        file_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(file_path, "PNG")

    # ------------------------------------------------------------------
    # CJK font configuration
    # ------------------------------------------------------------------

    def ensure_cjk_font_config(self, project_name: str) -> dict:
        """Ensure the project has CJK-safe font configuration.

        Copies a system CJK font into the project and writes a Ren'Py config
        file that references it.

        Returns:
            dict with keys: configured (bool), font_path (str | None), config_path (str)
        """
        if self.pm is None:
            raise RuntimeError("ProjectManager is required for font configuration")

        project_dir = self.pm._project_dir(project_name)
        fonts_dir = project_dir / "game" / "fonts"
        fonts_dir.mkdir(parents=True, exist_ok=True)

        font_dest = fonts_dir / _CJK_FONT_DEST_NAME
        configured = False

        if _CJK_FONT_SOURCE.exists() and not font_dest.exists():
            try:
                shutil.copy2(_CJK_FONT_SOURCE, font_dest)
                configured = True
            except OSError as exc:
                logger.warning("Failed to copy CJK font: %s", exc)
        elif font_dest.exists():
            configured = True

        # Write font config rpy
        config_path = project_dir / "game" / "prototype_fonts.rpy"
        lines = [
            "# Auto-generated CJK font configuration for prototype",
            "init python:",
            '    gui.text_font = "fonts/simhei.ttf"',
            '    gui.name_text_font = "fonts/simhei.ttf"',
            '    gui.interface_text_font = "fonts/simhei.ttf"',
            "",
        ]
        config_path.write_text("\n".join(lines), encoding="utf-8")

        return {
            "configured": configured,
            "font_path": font_dest.relative_to(project_dir).as_posix() if font_dest.exists() else None,
            "config_path": config_path.relative_to(project_dir).as_posix(),
        }
    def write_script(
        self,
        project_name: str,
        chapter: ChapterSummary,
        scenes: list[PrototypeScene],
        background_assets: dict[str, Path] | None = None,
    ) -> str:
        """Generate and write a minimal executable .rpy script skeleton to a staging file.

        The script is written to a staging path (e.g.
        "game/prototype_ch1.__staging__.rpy").  Callers must invoke
        commit_prototype_replacement() to promote it to the final path.

        Args:
            background_assets: Optional mapping of scene_id -> background image path.
                If provided, the script will reference real background assets.

        Returns:
            The staging relative file path.
        """
        if self.pm is None:
            raise RuntimeError("ProjectManager is required for script writeback")

        safe_name = "".join(c if c.isalnum() else "_" for c in chapter.name)
        file_name = f"prototype_{chapter.id}_{safe_name}.rpy"
        final_path = f"game/{file_name}"
        staging_path = self._staging_path_from_final(final_path)

        project_dir = self.pm._project_dir(project_name)
        game_dir = project_dir / "game"
        game_dir.mkdir(parents=True, exist_ok=True)
        staging_file = game_dir / Path(staging_path).name

        lines: list[str] = []
        lines.append(f"# Prototype chapter: {chapter.name}")
        lines.append("")

        # Emit image definitions for backgrounds
        bg_assets = background_assets or {}
        for scene in scenes:
            bg_path = bg_assets.get(scene.scene_id)
            if bg_path and bg_path.exists():
                rel_path = bg_path.relative_to(project_dir).as_posix()
                lines.append(f'image bg_{scene.scene_id} = "{rel_path}"')
        if bg_assets:
            lines.append("")

        for i, scene in enumerate(scenes):
            lines.append(f"label {scene.entry_label}:")
            # Use real background asset if available, else controlled fallback
            bg_path = bg_assets.get(scene.scene_id)
            if bg_path and bg_path.exists():
                lines.append(f"    scene bg_{scene.scene_id}")
            else:
                lines.append(f"    scene black  # PLACEHOLDER: {scene.location}")
            if scene.location:
                safe_location = scene.location.replace('"', '\"')
                lines.append(f'    "【地点：{safe_location}"')
            if scene.characters_present:
                chars = "、".join(scene.characters_present)
                safe_chars = chars.replace('"', '\"')
                lines.append(f'    "【登场角色：{safe_chars}"')
            # Use summary as narration text
            narration = scene.summary.replace('"', '\"')
            lines.append(f'    "{narration}"')
            if scene.next_scene_id:
                next_scene = next((s for s in scenes if s.scene_id == scene.next_scene_id), None)
                if next_scene:
                    lines.append(f"    jump {next_scene.entry_label}")
                else:
                    lines.append('    "To be continued..."')
                    lines.append("    return")
            else:
                lines.append('    "End of prototype."')
                lines.append("    return")
            lines.append("")

        staging_file.write_text("\n".join(lines), encoding="utf-8")
        return staging_path
    # ------------------------------------------------------------------
    # Main script wiring
    # ------------------------------------------------------------------

    _MANAGED_START = "    # PROTOTYPE START (managed)"
    _MANAGED_END = "    # PROTOTYPE END (managed)"
    _DEFAULT_TEMPLATE_MARKERS = (
        "Welcome to your new Ren'Py project!",
        "Hello from the Ren'Py MCP server!",
        "Generated by the Ren'Py MCP server.",
    )

    def wire_main_script_to_prototype(self, project_name: str, entry_label: str) -> None:
        """Update game/script.rpy to call the prototype entry label.

        Behavior:
            - If the file already contains a managed region, only the call
              statement inside that region is updated.
            - If the file is empty or contains default template content,
              it is replaced with a managed region.
            - Otherwise, a RuntimeError is raised to avoid overwriting
              user-customised script logic.

        Args:
            project_name: Target project name.
            entry_label: The prototype scene label to call from label start.

        Raises:
            RuntimeError: If ProjectManager is not available, or if the
                existing script cannot be safely modified.
        """
        if self.pm is None:
            raise RuntimeError("ProjectManager is required for script wiring")

        project_dir = self.pm._project_dir(project_name)
        script_path = project_dir / "game" / "script.rpy"
        script_path.parent.mkdir(parents=True, exist_ok=True)

        managed_start = self._MANAGED_START
        managed_end = self._MANAGED_END

        existing = script_path.read_text(encoding="utf-8") if script_path.exists() else ""

        # Case 1: Already has managed region → update only the region
        if managed_start in existing and managed_end in existing:
            lines = existing.splitlines()
            new_lines: list[str] = []
            skipping = False
            for line in lines:
                if line == managed_start:
                    skipping = True
                    new_lines.append(managed_start)
                    new_lines.append(f"    call {entry_label}")
                    new_lines.append("    return")
                    continue
                if line == managed_end:
                    skipping = False
                    new_lines.append(managed_end)
                    continue
                if not skipping:
                    new_lines.append(line)
            script_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            return

        # Case 2: Default template or empty → safe to replace
        is_default = any(marker in existing for marker in self._DEFAULT_TEMPLATE_MARKERS)
        if not existing.strip() or is_default:
            script_path.write_text(
                f"label start:\n{managed_start}\n    call {entry_label}\n    return\n{managed_end}\n",
                encoding="utf-8",
            )
            return

        # Case 3: Non-template content without managed region → fail explicitly
        raise RuntimeError(
            f"Cannot safely wire prototype to {script_path}: file contains unrecognized content. "
            "Either start from a default template or add a managed region."
        )

    # ------------------------------------------------------------------
    # Main script backup / restore
    # ------------------------------------------------------------------

    def backup_main_script(self, project_name: str) -> str | None:
        """Return the current content of game/script.rpy for potential rollback.

        Returns:
            The file content, or None if the file does not exist.
        """
        if self.pm is None:
            return None
        project_dir = self.pm._project_dir(project_name)
        script_path = project_dir / "game" / "script.rpy"
        if script_path.exists():
            return script_path.read_text(encoding="utf-8")
        return None

    def restore_main_script(self, project_name: str, content: str | None) -> None:
        """Restore game/script.rpy to a previously backed-up content.

        Args:
            project_name: Target project name.
            content: Content to restore, or None to skip.
        """
        if self.pm is None or content is None:
            return
        project_dir = self.pm._project_dir(project_name)
        script_path = project_dir / "game" / "script.rpy"
        try:
            script_path.write_text(content, encoding="utf-8")
        except OSError:
            logger.warning("Failed to restore script.rpy for project %s", project_name)

    # ------------------------------------------------------------------
    # Staged replace: commit and rollback
    # ------------------------------------------------------------------

    def commit_prototype_replacement(
        self,
        project_name: str,
        new_scene_ids: list[str],
        staging_script_path: str,
    ) -> None:
        """Finalize prototype replacement by promoting the staging script and removing old artifacts.

        This must only be called after all new prototype steps
        (write_script, wire_main_script, update_index) have succeeded.

        Raises:
            OSError: If the staging file cannot be promoted to the final path.
        """
        if self.pm is None:
            return

        project_dir = self.pm._project_dir(project_name)
        final_script_path = self._final_path_from_staging(staging_script_path)
        staging_file = project_dir / staging_script_path
        final_file = project_dir / final_script_path

        # 1. Promote staging file to final path (fail-fast, atomic-ish replace)
        #    If this raises, old stable prototype and index are untouched.
        if staging_file.exists():
            staging_file.replace(final_file)

        # 2. Remove old prototype index entries (keep only new_scene_ids)
        index = self.pm.read_project_index(project_name)
        if index and "scenes" in index:
            old_ids = [
                sid for sid, s in index["scenes"].items()
                if isinstance(s, dict) and s.get("source") == "prototype" and sid not in new_scene_ids
            ]
            if old_ids:
                for sid in old_ids:
                    del index["scenes"][sid]
                self.pm.write_project_index(project_name, index)

        # 3. Remove old prototype files (keep only the new final file)
        game_dir = project_dir / "game"
        if game_dir.exists():
            new_file_name = Path(final_script_path).name
            for proto_file in game_dir.glob("prototype_*.rpy"):
                if proto_file.name != new_file_name:
                    try:
                        proto_file.unlink()
                    except OSError:
                        logger.warning("Failed to remove old prototype file: %s", proto_file)
            # Also clean up any leftover staging files
            for leftover in game_dir.glob("prototype_*.__staging__.rpy"):
                try:
                    leftover.unlink()
                except OSError:
                    pass

    def rollback_prototype_generation(
        self,
        project_name: str,
        staging_script_path: str | None,
        new_scene_ids: list[str],
        old_script_content: str | None,
    ) -> None:
        """Rollback a failed prototype generation round.

        Restores the main script, removes the staging prototype file,
        and removes newly written index entries.  The previous stable
        prototype file (if any) is left untouched.
        """
        if self.pm is None:
            return

        # 1. Restore main script.rpy
        self.restore_main_script(project_name, old_script_content)

        # 2. Remove staging file only — never touch the stable final file
        if staging_script_path:
            project_dir = self.pm._project_dir(project_name)
            staging_file = project_dir / staging_script_path
            try:
                if staging_file.exists():
                    staging_file.unlink()
            except OSError:
                logger.warning("Failed to remove staging file: %s", staging_file)

        # 3. Remove newly written index entries
        index = self.pm.read_project_index(project_name)
        if index and "scenes" in index:
            changed = False
            for sid in new_scene_ids:
                if sid in index["scenes"]:
                    del index["scenes"][sid]
                    changed = True
            if changed:
                self.pm.write_project_index(project_name, index)

    # ------------------------------------------------------------------
    # Index writeback
    # ------------------------------------------------------------------
    def update_index(
        self,
        project_name: str,
        chapter: ChapterSummary,
        scenes: list[PrototypeScene],
        script_path: str,
        background_assets: dict[str, Path] | None = None,
        cjk_font_config: dict | None = None,
    ) -> None:
        """Update meta/index.json with full prototype scene metadata.

        Writes new prototype entries alongside any existing ones.
        Old entries are only removed by commit_prototype_replacement().
        """
        if self.pm is None:
            raise RuntimeError("ProjectManager is required for index writeback")

        index = self.pm.read_project_index(project_name) or {"scenes": {}}
        if "scenes" not in index:
            index["scenes"] = {}

        bg_assets = background_assets or {}
        for i, scene in enumerate(scenes):
            bg_path = bg_assets.get(scene.scene_id)
            entry = {
                "chapter_id": chapter.id,
                "scene_id": scene.scene_id,
                "title": scene.title,
                "summary": scene.summary,
                "location": scene.location,
                "location_visual_brief": scene.location_visual_brief,
                "mood": scene.mood,
                "characters_present": scene.characters_present,
                "dialogue_beats": [b.model_dump() for b in scene.dialogue_beats],
                "next_scene_id": scene.next_scene_id,
                "label": scene.entry_label,
                "file_path": script_path,
                "source": "prototype",
                "order": i + 1,
                "background_asset_path": str(bg_path.relative_to(self.pm._project_dir(project_name)).as_posix()) if bg_path and bg_path.exists() else None,
                "background_placeholder": not (bg_path and bg_path.exists()),
            }
            index["scenes"][scene.scene_id] = entry

        if cjk_font_config:
            index["cjk_font_config"] = cjk_font_config

        self.pm.write_project_index(project_name, index)
