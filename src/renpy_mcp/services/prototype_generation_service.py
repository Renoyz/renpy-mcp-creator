"""Prototype generation service: from confirmed blueprint to playable scene skeleton."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from renpy_mcp.blueprint.models import ChapterSummary, ProjectBlueprint
from renpy_mcp.services.project_manager import ProjectManager

logger = logging.getLogger(__name__)


class PrototypeScene(BaseModel):
    """A detailed scene generated for the prototype chapter."""

    scene_id: str
    title: str
    summary: str
    location: str
    characters_present: list[str] = Field(default_factory=list)
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
- characters_present: list of character names appearing in this scene
- entry_label: Ren'Py label name for this scene (e.g., "prototype_ch1_start")
- next_scene_id: scene_id of the next scene, or null for the last scene

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

    def write_script(
        self, project_name: str, chapter: ChapterSummary, scenes: list[PrototypeScene]
    ) -> str:
        """Generate and write a minimal executable .rpy script skeleton.

        Returns:
            The relative file path (e.g., "game/prototype_ch1.rpy").
        """
        if self.pm is None:
            raise RuntimeError("ProjectManager is required for script writeback")

        safe_name = "".join(c if c.isalnum() else "_" for c in chapter.name)
        file_name = f"prototype_{chapter.id}_{safe_name}.rpy"
        rel_path = f"game/{file_name}"

        project_dir = self.pm._project_dir(project_name)
        game_dir = project_dir / "game"
        game_dir.mkdir(parents=True, exist_ok=True)
        file_path = game_dir / file_name

        lines: list[str] = []
        lines.append(f"# Prototype chapter: {chapter.name}")
        lines.append("")

        for i, scene in enumerate(scenes):
            lines.append(f"label {scene.entry_label}:")
            lines.append(f'    scene {scene.location}')
            # Use summary as narration text
            narration = scene.summary.replace('"', '\\"')
            lines.append(f'    "{narration}"')
            if scene.characters_present:
                for char_name in scene.characters_present:
                    safe_char = char_name.replace('"', '\\"')
                    lines.append(f'    show {safe_char} at center')
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

        file_path.write_text("\n".join(lines), encoding="utf-8")
        return rel_path

    # ------------------------------------------------------------------
    # Main script wiring
    # ------------------------------------------------------------------

    def wire_main_script_to_prototype(self, project_name: str, entry_label: str) -> None:
        """Rewrite game/script.rpy so label start calls the prototype entry label.

        Args:
            project_name: Target project name.
            entry_label: The prototype scene label to call from label start.

        Raises:
            RuntimeError: If ProjectManager is not available.
        """
        if self.pm is None:
            raise RuntimeError("ProjectManager is required for script wiring")

        project_dir = self.pm._project_dir(project_name)
        script_path = project_dir / "game" / "script.rpy"
        script_path.parent.mkdir(parents=True, exist_ok=True)

        content = f"""label start:
    # Prototype entry point
    call {entry_label}
    return
"""
        script_path.write_text(content, encoding="utf-8")

    # ------------------------------------------------------------------
    # Index writeback
    # ------------------------------------------------------------------

    def update_index(
        self,
        project_name: str,
        chapter: ChapterSummary,
        scenes: list[PrototypeScene],
        script_path: str,
    ) -> None:
        """Update meta/index.json with prototype scene mappings."""
        if self.pm is None:
            raise RuntimeError("ProjectManager is required for index writeback")

        index = self.pm.read_project_index(project_name) or {"scenes": {}}
        if "scenes" not in index:
            index["scenes"] = {}

        for scene in scenes:
            index["scenes"][scene.scene_id] = {
                "chapter_id": chapter.id,
                "label": scene.entry_label,
                "file_path": script_path,
            }

        self.pm.write_project_index(project_name, index)
