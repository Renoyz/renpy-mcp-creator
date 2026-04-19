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

    def _staging_path_from_final(self, final_path: str) -> str:
        """Derive the staging path from a final prototype script path."""
        p = Path(final_path)
        return str(p.with_name(f"{p.stem}.__staging__{p.suffix}"))

    def _final_path_from_staging(self, staging_path: str) -> str:
        """Derive the final path from a staging prototype script path."""
        return staging_path.replace(".__staging__", "")

    def write_script(
        self, project_name: str, chapter: ChapterSummary, scenes: list[PrototypeScene]
    ) -> str:
        """Generate and write a minimal executable .rpy script skeleton to a staging file.

        The script is written to a staging path (e.g.
        "game/prototype_ch1.__staging__.rpy").  Callers must invoke
        commit_prototype_replacement() to promote it to the final path.

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

        for i, scene in enumerate(scenes):
            lines.append(f"label {scene.entry_label}:")
            # Safe placeholder: scene black works without any image assets
            lines.append('    scene black')
            if scene.location:
                safe_location = scene.location.replace('"', '\\"')
                lines.append(f'    "【地点：{safe_location}】"')
            if scene.characters_present:
                chars = "、".join(scene.characters_present)
                safe_chars = chars.replace('"', '\\"')
                lines.append(f'    "【登场角色：{safe_chars}】"')
            # Use summary as narration text
            narration = scene.summary.replace('"', '\\"')
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
        """
        if self.pm is None:
            return

        project_dir = self.pm._project_dir(project_name)
        final_script_path = self._final_path_from_staging(staging_script_path)
        staging_file = project_dir / staging_script_path
        final_file = project_dir / final_script_path

        # 1. Promote staging file to final path
        if staging_file.exists():
            try:
                if final_file.exists():
                    final_file.unlink()
                staging_file.rename(final_file)
            except OSError:
                logger.warning("Failed to promote staging file: %s", staging_file)

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

        for i, scene in enumerate(scenes):
            index["scenes"][scene.scene_id] = {
                "chapter_id": chapter.id,
                "scene_id": scene.scene_id,
                "title": scene.title,
                "summary": scene.summary,
                "location": scene.location,
                "next_scene_id": scene.next_scene_id,
                "label": scene.entry_label,
                "file_path": script_path,
                "source": "prototype",
                "order": i + 1,
            }

        self.pm.write_project_index(project_name, index)
