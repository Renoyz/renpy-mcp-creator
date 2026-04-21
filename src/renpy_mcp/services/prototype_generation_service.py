"""Prototype generation service: from confirmed blueprint to playable scene skeleton."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any


_RENPY_KEYWORDS = frozenset({
    "define", "image", "label", "scene", "show", "hide", "with", "menu",
    "return", "jump", "call", "if", "elif", "else", "while", "for", "in",
    "True", "False", "None", "and", "or", "not", "is", "pass", "continue",
    "break", "init", "python", "default", "transform", "screen", "style",
})


def _safe_character_id(name: str) -> str:
    """Convert a display name to a safe Ren'Py identifier.

    Keeps ASCII alphanumerics; everything else becomes underscore.
    Collapses consecutive underscores.  Falls back to empty string
    for empty, numeric-leading, or keyword identifiers.
    """
    result = "".join(c if c.isascii() and c.isalnum() else "_" for c in name)
    while "__" in result:
        result = result.replace("__", "_")
    result = result.strip("_")
    if not result or result[0].isdigit() or result in _RENPY_KEYWORDS:
        return ""
    return result


def _escape_renpy_string(text: str) -> str:
    """Escape a string for safe use inside Ren'Py double-quoted strings."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _safe_image_tag(scene_id: str) -> str:
    """Convert a scene_id to a safe Ren'Py image tag.

    Non-alphanumeric characters become underscores.
    """
    return "".join(c if c.isalnum() else "_" for c in scene_id)


def _to_renpy_asset_path(project_dir_relative_path: str) -> str:
    """Strip the leading 'game/' segment from a project-relative path.

    Ren'Py image references are resolved relative to the game/ directory,
    so 'game/images/background/foo.png' must be written as
    'images/background/foo.png' in the script.
    """
    if project_dir_relative_path.startswith("game/"):
        return project_dir_relative_path[5:]
    return project_dir_relative_path

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
    spoken_line: str = ""


class SpritePlanItem(BaseModel):
    """A single character sprite placement within a scene."""

    character_name: str
    character_id: str = ""
    sprite_path: str | None = None
    sprite_check_path: str | None = None
    sprite_placeholder: bool = True
    sprite_renderable: bool = False
    sprite_quality_reason: str = ""
    position: str = "center"
    expression: str = "neutral"
    layout_mode: str = "solo"
    transform_name: str = "proto_center_solo"


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
    sprite_plan: list[SpritePlanItem] = Field(default_factory=list)
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
  - spoken_line: the final in-character spoken dialogue line for the game UI
- entry_label: Ren'Py label name for this scene (e.g., "prototype_ch1_start")
- next_scene_id: scene_id of the next scene, or null for the last scene

Consistency rules:
- Every dialogue_beats.speaker MUST be in characters_present.
- The mood must be reflected in both the location_visual_brief and the dialogue beats.
- If the location changes between scenes, the visual brief must also change.
- spoken_line must be direct spoken dialogue, not narration or a third-person summary.
- Do NOT write spoken_line like "询问对方...", "低声自语...", "展开双臂说...".
- spoken_line should read like natural VN dialogue the character can say aloud in Chinese, 1-2 sentences max.

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

    def _runtime_asset_relpath(self, project_dir: Path, asset_path: Path, round_id: str | None = None) -> str:
        """Return the final project-relative path for a generated asset.

        When an asset lives under game/__staging__/{round_id}/..., the runtime path
        must point at the eventual promoted game/... location, not the staging file.
        """
        rel = asset_path.relative_to(project_dir)
        if round_id:
            staging_root = Path("game") / "__staging__" / round_id
            if rel.parts[: len(staging_root.parts)] == staging_root.parts:
                rel = Path("game") / Path(*rel.parts[len(staging_root.parts):])
        return rel.as_posix()

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
                edges = gray.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(5))
                px = edges.load()
                width, height = edges.size
                threshold = 52
                binary = [[1 if px[x, y] >= threshold else 0 for x in range(width)] for y in range(height)]

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
                            for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
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

                focus_density = _density(int(width * 0.18), int(width * 0.82), int(height * 0.15), int(height * 0.95))
                lower_focus_density = _density(int(width * 0.18), int(width * 0.82), int(height * 0.45), int(height * 0.98))
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
                if focus_density > 0.19 and focus_density > peripheral_density * 1.55 and lower_focus_density > 0.13:
                    return False, "foreground_too_busy"
        except Exception as exc:
            logger.warning("Background composition assessment failed for %s: %s", image_path, exc)
        return True, "ok"

    def _cjk_runtime_override_lines(self) -> list[str]:
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
    # Background asset generation
    # ------------------------------------------------------------------

    async def generate_background_assets(
        self, project_name: str, scenes: list[PrototypeScene], round_id: str | None = None,
    ) -> dict[str, dict]:
        """Generate background images for each scene.

        Tries ImageService first; falls back to PIL placeholder on failure.

        Returns:
            Mapping scene_id -> {"path": Path | None, "placeholder": bool, "source": str}
            where source is one of "image_service", "pil_fallback", or "none".
        """
        if self.pm is None:
            raise RuntimeError("ProjectManager is required for asset generation")

        project_dir = self.pm._project_dir(project_name)
        bg_dir = project_dir / "game" / "images" / "background"
        bg_dir.mkdir(parents=True, exist_ok=True)

        staging_bg_dir: Path | None = None
        if round_id:
            staging_bg_dir = project_dir / "game" / "__staging__" / round_id / "images" / "background"
            staging_bg_dir.mkdir(parents=True, exist_ok=True)

        result: dict[str, dict] = {}
        for scene in scenes:
            file_name = f"bg_{scene.scene_id}.png"
            final_path = bg_dir / file_name
            staging_path = staging_bg_dir / file_name if staging_bg_dir else final_path

            # Compute relative paths for return value
            rel_final = str(final_path.relative_to(project_dir).as_posix())
            rel_staging = str(staging_path.relative_to(project_dir).as_posix()) if staging_bg_dir else None

            # Protect pre-existing asset when round_id is provided
            old_backup: Path | None = None
            if round_id and final_path.exists():
                old_backup = project_dir / "game" / "__staging__" / round_id / "__backup__" / file_name
                old_backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(final_path, old_backup)

            image_generated = False
            gate_rejected = False
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
                        "Visual novel background plate, 16:9, no characters, no text, no giant statues, "
                        "no giant masks, no close foreground props, no dominant central subject, "
                        "keep the lower foreground visually open for foreground sprites."
                    )
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
                        passes_gate, gate_reason = self._assess_background_composition(gate_check_path)
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
                logger.warning("ImageService background generation failed for %s: %s", scene.scene_id, exc)

            if not image_generated:
                try:
                    self._generate_placeholder_background(staging_path, scene)
                    if round_id and staging_bg_dir:
                        result[scene.scene_id] = {
                            "path": rel_final,
                            "staging_path": rel_staging,
                            "placeholder": True,
                            "source": "composition_warned_fallback" if gate_rejected else "pil_fallback",
                            "is_new_file": True,
                        }
                    else:
                        result[scene.scene_id] = {
                            "path": staging_path,
                            "placeholder": True,
                            "source": "composition_warned_fallback" if gate_rejected else "pil_fallback",
                            "is_new_file": True,
                        }
                except Exception as exc:
                    logger.warning("PIL placeholder generation failed for %s: %s", scene.scene_id, exc)
                    result[scene.scene_id] = {
                        "path": None,
                        "staging_path": None,
                        "placeholder": True,
                        "source": "none",
                        "is_new_file": False,
                    }

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
    # Character sprite asset generation
    # ------------------------------------------------------------------

    async def generate_character_assets(
        self, project_name: str, blueprint: ProjectBlueprint, scenes: list[PrototypeScene],
        round_id: str | None = None,
    ) -> dict[str, dict]:
        """Generate character sprite images for all characters in prototype scenes.

        Tries ImageService first; falls back to PIL placeholder on failure.
        Attempts background removal via BackgroundRemover when available.
        Post-processes sprites with normalize_sprite for consistent baseline.

        When round_id is provided, all new files are written to a round-scoped
        staging directory and only promoted to final paths on commit.

        Returns:
            Mapping character_name -> {
                "path": str,              # final project-relative path
                "staging_path": str | None,
                "placeholder": bool,
                "renderable": bool,
                "renderable_reason": str,
                "bbox": dict | None,
                "baseline_offset": int,
                "is_new_file": bool,
                "intermediate_paths": list[str],
            }
        """
        if self.pm is None:
            raise RuntimeError("ProjectManager is required for asset generation")

        project_dir = self.pm._project_dir(project_name)
        char_dir = project_dir / "game" / "images" / "character"
        char_dir.mkdir(parents=True, exist_ok=True)

        staging_char_dir: Path | None = None
        if round_id:
            staging_char_dir = project_dir / "game" / "__staging__" / round_id / "images" / "character"
            staging_char_dir.mkdir(parents=True, exist_ok=True)

        # Collect unique characters from all scenes
        unique_chars: set[str] = set()
        for scene in scenes:
            for name in scene.characters_present:
                unique_chars.add(name)

        # Build character info lookup from blueprint
        char_info: dict[str, dict] = {}
        for c in blueprint.characters:
            char_info[c.name] = {
                "appearance": c.appearance,
                "personality": c.personality,
            }

        # Build scene context lookup per character
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
        char_registry = self._build_character_registry(scenes)

        for char_name in unique_chars:
            safe_id = char_registry.get(char_name) or _safe_character_id(char_name) or "char_unknown"
            file_name = f"{safe_id}_neutral.png"
            final_path = char_dir / file_name
            staging_path = staging_char_dir / file_name if staging_char_dir else final_path

            rel_final = str(final_path.relative_to(project_dir).as_posix())
            rel_staging = str(staging_path.relative_to(project_dir).as_posix()) if staging_char_dir else None

            info = char_info.get(char_name, {})
            appearance = info.get("appearance", "anime character")
            personality = info.get("personality", "")
            ctx = char_scene_context.get(char_name, {})
            layout_mode = self._resolve_layout_mode(ctx.get("character_count", 1))
            framing = "medium shot" if layout_mode == "solo" else ("medium shot" if layout_mode == "duo" else "medium-long shot")
            subject_height_guidance = self._character_subject_height_guidance(layout_mode)

            char_prompt = (
                f"Portrait of {char_name}. "
                f"Appearance: {appearance}. "
                f"Personality: {personality}. "
                f"Scene setting: {ctx.get('location', 'unknown')}. "
                f"Visual direction: {ctx.get('location_visual_brief', '')}. "
                f"Mood: {ctx.get('mood', 'neutral')}. "
                f"Camera framing: {framing}, centered on character. "
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

            intermediate_paths: list[str] = []
            image_generated = False
            generated_path: Path | None = None
            bg_removed = False

            # Protect pre-existing asset when round_id is provided
            old_backup: Path | None = None
            if round_id and final_path.exists():
                old_backup = project_dir / "game" / "__staging__" / round_id / "__backup__" / file_name
                old_backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(final_path, old_backup)

            try:
                from renpy_mcp.config import get_settings
                from renpy_mcp.ai.image_service import ImageService

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
                            # Move generated file into staging
                            shutil.move(str(raw_generated), str(staging_path))
                            if old_backup and old_backup.exists():
                                shutil.copy2(old_backup, final_path)
                            generated_path = staging_path
                            intermediate_paths.append(rel_staging)
                        else:
                            generated_path = raw_generated

                        # Try background removal on the staging/generated file
                        transparent_path: Path | None = None
                        try:
                            from renpy_mcp.ai.background_remover import BackgroundRemover
                            remover = BackgroundRemover()
                            transparent_path = remover.remove_background(generated_path)
                        except Exception as exc:
                            logger.warning("Background removal failed for %s: %s", char_name, exc)

                        if transparent_path and transparent_path.exists():
                            # Ensure transparent result stays inside staging if we are staging
                            if round_id and staging_char_dir and not str(transparent_path).startswith(str(staging_char_dir)):
                                dest = staging_char_dir / transparent_path.name
                                shutil.move(str(transparent_path), str(dest))
                                transparent_path = dest
                                intermediate_paths.append(str(dest.relative_to(project_dir).as_posix()))
                            elif round_id and staging_char_dir:
                                rel_tp = str(transparent_path.relative_to(project_dir).as_posix())
                                if rel_tp not in intermediate_paths:
                                    intermediate_paths.append(rel_tp)
                            generated_path = transparent_path
                            bg_removed = True
                        image_generated = True
            except Exception as exc:
                logger.warning("Character image generation failed for %s: %s", char_name, exc)

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
                    if normalized_path and normalized_path.exists() and round_id and staging_char_dir:
                        rel_np = str(normalized_path.relative_to(project_dir).as_posix())
                        if rel_np not in intermediate_paths:
                            intermediate_paths.append(rel_np)
                except Exception as exc:
                    logger.warning("Sprite normalization failed for %s: %s", char_name, exc)

            # Determine final path and renderability
            final_sprite_path = normalized_path if normalized_path and normalized_path.exists() else generated_path
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
                    logger.warning("Character placeholder generation failed for %s: %s", char_name, exc)
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
                    logger.info("Sprite for %s marked unrenderable: %s", char_name, reason)

                runtime_rel = self._runtime_asset_relpath(project_dir, final_sprite_path, round_id)
                staging_rel = str(final_sprite_path.relative_to(project_dir).as_posix())
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

    def _generate_placeholder_character(self, file_path: Path, char_name: str) -> None:
        """Generate a transparent placeholder character sprite using PIL."""
        from PIL import Image, ImageDraw

        img = Image.new("RGBA", (400, 750), color=(0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), f"{char_name}", fill=(200, 200, 200, 255))
        draw.text((20, 50), "SPRITE PLACEHOLDER", fill=(180, 180, 180, 255))

        file_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(file_path, "PNG")

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

    def _resolve_layout_mode(self, char_count: int) -> str:
        if char_count == 1:
            return "solo"
        elif char_count == 2:
            return "duo"
        return "trio"

    def _character_subject_height_guidance(self, layout_mode: str) -> str:
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
        char_registry = self._build_character_registry(scenes)
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
    # CJK font configuration
    # ------------------------------------------------------------------

    def ensure_cjk_font_config(self, project_name: str, round_id: str | None = None) -> dict:
        """Ensure the project has CJK-safe font configuration.

        Copies a system CJK font into the project and writes a Ren'Py config
        file that references it.  The config is only enabled when the font
        file actually exists so the runtime never references a missing file.

        Returns:
            dict with keys: configured (bool), font_path (str | None), config_path (str)
        """
        if self.pm is None:
            raise RuntimeError("ProjectManager is required for font configuration")

        project_dir = self.pm._project_dir(project_name)
        fonts_dir = project_dir / "game" / "fonts"
        fonts_dir.mkdir(parents=True, exist_ok=True)

        staging_root = project_dir / "game" / "__staging__" / round_id if round_id else None
        if staging_root:
            staging_root.mkdir(parents=True, exist_ok=True)

        font_dest = fonts_dir / _CJK_FONT_DEST_NAME
        staged_font_dest = staging_root / "fonts" / _CJK_FONT_DEST_NAME if staging_root else None
        configured = False
        new_files: list[str] = []

        if _CJK_FONT_SOURCE.exists() and not font_dest.exists():
            try:
                target_font_path = staged_font_dest or font_dest
                target_font_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(_CJK_FONT_SOURCE, target_font_path)
                configured = True
                new_files.append(str(target_font_path.relative_to(project_dir).as_posix()))
            except OSError as exc:
                logger.warning("Failed to copy CJK font: %s", exc)
        elif font_dest.exists():
            configured = True

        # Write font config rpy only when the font is actually available
        runtime_config_rel = "game/prototype_fonts.rpy"
        config_path = (staging_root / "prototype_fonts.rpy") if staging_root else (project_dir / runtime_config_rel)
        if font_dest.exists() or (staged_font_dest and staged_font_dest.exists()):
            lines = [
                "# Auto-generated CJK font configuration for prototype",
                "# Uses init python so the overrides apply AFTER gui.rpy defaults load.",
            ]
            lines.extend(self._cjk_runtime_override_lines())
            config_path.write_text("\n".join(lines), encoding="utf-8")
        else:
            # Write a no-op stub so callers have a stable file path
            config_path.write_text(
                "# Auto-generated CJK font configuration for prototype\n"
                "# Font file not available -- CJK fallback disabled.\n",
                encoding="utf-8",
            )
        # The config file is (re)written every round; treat it as a new artifact
        new_files.append(str(config_path.relative_to(project_dir).as_posix()))

        return {
            "configured": configured,
            "font_path": (Path("game") / "fonts" / _CJK_FONT_DEST_NAME).as_posix()
            if (font_dest.exists() or (staged_font_dest and staged_font_dest.exists()))
            else None,
            "config_path": runtime_config_rel,
            "new_files": new_files,
        }
    def _build_character_registry(self, scenes: list[PrototypeScene]) -> dict[str, str]:
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

    def _extract_bg_path(self, bg_asset: Any) -> Path | None:
        """Extract path from background asset (supports dict and legacy Path)."""
        if isinstance(bg_asset, dict):
            return bg_asset.get("path")
        if isinstance(bg_asset, Path):
            return bg_asset
        return None

    def write_script(
        self,
        project_name: str,
        chapter: ChapterSummary,
        scenes: list[PrototypeScene],
        background_assets: dict[str, Any] | None = None,
        character_assets: dict[str, dict] | None = None,
        cjk_font_config: dict | None = None,
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

        # Build character registry for safe say-statement generation
        char_registry = self._build_character_registry(scenes)

        lines: list[str] = []
        lines.append(f"# Prototype chapter: {chapter.name}")
        lines.append("")

        if cjk_font_config and cjk_font_config.get("configured"):
            lines.extend(self._cjk_runtime_override_lines())
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
                lines.append(f'    "【地点：{escaped_loc}】"')
            if scene.characters_present:
                chars = "、".join(scene.characters_present)
                escaped_chars = _escape_renpy_string(chars)
                lines.append(f'    "【登场角色：{escaped_chars}】"')
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
        round_id: str | None = None,
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

        # 2. Promote round-scoped staging assets to final paths
        if round_id:
            staging_dir = project_dir / "game" / "__staging__" / round_id
            if staging_dir.exists():
                for src in staging_dir.rglob("*"):
                    if src.is_file() and "__backup__" not in str(src):
                        rel = src.relative_to(staging_dir)
                        dst = project_dir / "game" / rel
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        src.replace(dst)
                # Remove empty staging dir and backup dir
                try:
                    import shutil
                    shutil.rmtree(staging_dir)
                except OSError:
                    logger.warning("Failed to remove staging dir: %s", staging_dir)

        # 3. Remove old prototype index entries (keep only new_scene_ids)
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

        # 4. Remove old prototype files (keep only the new final file)
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
        generated_asset_paths: list[str] | None = None,
        round_id: str | None = None,
    ) -> None:
        """Rollback a failed prototype generation round.

        Restores the main script, removes the staging prototype file,
        removes newly written index entries, and deletes any visual assets
        that were generated during this round.  The previous stable
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

        # 4. Remove round-scoped staging directory (primary rollback mechanism)
        if round_id:
            project_dir = self.pm._project_dir(project_name)
            staging_dir = project_dir / "game" / "__staging__" / round_id
            if staging_dir.exists():
                try:
                    import shutil
                    shutil.rmtree(staging_dir)
                except OSError:
                    logger.warning("Failed to remove staging dir: %s", staging_dir)

        # 5. Fallback: remove individual generated asset paths (legacy path)
        if generated_asset_paths:
            project_dir = self.pm._project_dir(project_name)
            for p in generated_asset_paths:
                abs_path = Path(p)
                if not abs_path.is_absolute():
                    abs_path = project_dir / p
                try:
                    if abs_path.exists() and abs_path.is_file():
                        abs_path.unlink()
                except OSError:
                    logger.warning("Failed to remove generated asset: %s", abs_path)

    # ------------------------------------------------------------------
    # Index writeback
    # ------------------------------------------------------------------
    def update_index(
        self,
        project_name: str,
        chapter: ChapterSummary,
        scenes: list[PrototypeScene],
        script_path: str,
        background_assets: dict[str, Any] | None = None,
        character_assets: dict[str, dict] | None = None,
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
        char_assets = character_assets or {}
        project_dir = self.pm._project_dir(project_name)

        for i, scene in enumerate(scenes):
            bg_asset = bg_assets.get(scene.scene_id)
            bg_path_raw = bg_asset.get("path") if isinstance(bg_asset, dict) else bg_asset
            bg_check_raw = bg_asset.get("staging_path") if isinstance(bg_asset, dict) else None
            bg_placeholder = bg_asset.get("placeholder", True) if isinstance(bg_asset, dict) else True
            bg_path_str: str | None = None
            if isinstance(bg_path_raw, Path):
                if bg_path_raw.exists() or (
                    isinstance(bg_check_raw, str) and (project_dir / bg_check_raw).exists()
                ) or (
                    isinstance(bg_check_raw, Path) and bg_check_raw.exists()
                ):
                    bg_path_str = str(bg_path_raw.relative_to(project_dir).as_posix())
            elif isinstance(bg_path_raw, str):
                if (project_dir / bg_path_raw).exists() or (
                    isinstance(bg_check_raw, str) and (project_dir / bg_check_raw).exists()
                ) or (
                    isinstance(bg_check_raw, Path) and bg_check_raw.exists()
                ):
                    bg_path_str = bg_path_raw

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
                "sprite_plan": [sp.model_dump(exclude={"sprite_check_path"}) for sp in scene.sprite_plan],
                "next_scene_id": scene.next_scene_id,
                "label": scene.entry_label,
                "file_path": script_path,
                "source": "prototype",
                "order": i + 1,
                "background_asset_path": bg_path_str,
                "background_placeholder": bg_placeholder,
            }
            index["scenes"][scene.scene_id] = entry

        # Persist character asset metadata at index top level
        if char_assets:
            def _char_asset_path(info: dict) -> str | None:
                p = info.get("path")
                check = info.get("staging_path") or p
                if isinstance(p, str):
                    if (project_dir / p).exists():
                        return p
                    if isinstance(check, str) and (project_dir / check).exists():
                        return p
                    if isinstance(check, Path) and check.exists():
                        return p
                    return None
                if isinstance(p, Path):
                    if p.exists():
                        return str(p.relative_to(project_dir).as_posix())
                    if isinstance(check, str) and (project_dir / check).exists():
                        return str(p.relative_to(project_dir).as_posix())
                    if isinstance(check, Path) and check.exists():
                        return str(p.relative_to(project_dir).as_posix())
                    return None
                return None

            index["character_assets"] = {
                name: {
                    "path": _char_asset_path(info),
                    "placeholder": info.get("placeholder", True),
                    "renderable": info.get("renderable", False),
                    "renderable_reason": info.get("renderable_reason", ""),
                }
                for name, info in char_assets.items()
            }

        if cjk_font_config:
            index["cjk_font_config"] = cjk_font_config

        self.pm.write_project_index(project_name, index)
