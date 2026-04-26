"""Prototype generation service: from confirmed blueprint to playable scene skeleton."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from datetime import datetime
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

from renpy_mcp.blueprint.models import (
    ChapterStyleProfile,
    ChapterStyleProfiles,
    ChapterSummary,
    CharacterBible,
    CharacterContract,
    CharacterStyleEntry,
    ContinuityBible,
    ContinuityContract,
    DialogueBeat,
    GenerationContract,
    PrototypeManifest,
    ProjectBlueprint,
    ProjectStyleBible,
    ScenePackageChapter,
    ScenePackageScene,
    ScenePackageSpritePlanItem,
    ScenePackagesSnapshot,
    SpritePlanItem,
    ToneBible,
    ToneContract,
    VisualBible,
    VisualContract,
)
from renpy_mcp.services.project_manager import ProjectManager

logger = logging.getLogger(__name__)

_CJK_FONT_DEST_NAME = "simhei.ttf"

def _windows_cjk_fallbacks() -> list[Path]:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    return [
        Path(root) / "Fonts" / "simhei.ttf",
        Path(root) / "Fonts" / "msyh.ttf",
        Path(root) / "Fonts" / "msgothic.ttf",
    ]

_LINUX_CJK_FALLBACKS = [
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    Path("/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
    Path("/usr/share/fonts/truetype/arphic/ukai.ttc"),
]

_DARWIN_CJK_FALLBACKS = [
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
]


def resolve_cjk_font_path(config_path: Path | None = None) -> Path | None:
    """Resolve the best available CJK font path for the current platform.

    Precedence:
    1. *config_path* if it exists on disk
    2. Platform-specific fallback list (first one that exists)
    3. ``None`` if no font is available (CI / Docker)

    Callers should gracefully degrade when ``None`` is returned.
    """
    if config_path is not None and config_path.exists():
        return config_path

    fallbacks: list[Path]
    if os.name == "nt":
        fallbacks = _windows_cjk_fallbacks()
    elif os.uname().sysname == "Darwin":
        fallbacks = _DARWIN_CJK_FALLBACKS
    else:
        fallbacks = _LINUX_CJK_FALLBACKS

    for p in fallbacks:
        if p.exists():
            return p
    return None


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
    """Generate a minimum playable prototype from a confirmed blueprint.

    Acts as a facade coordinating sub-services.  Script rendering is
    delegated to :class:`ScriptRenderService`, scene generation to
    :class:`SceneGenerationService`, and prototype activation to
    :class:`PrototypeActivationService`.
    """

    def __init__(self, pm: ProjectManager | None, provider: Any | None) -> None:
        self.pm = pm
        self.provider = provider

        # Sub-service: script rendering (P2-1 extraction)
        from renpy_mcp.services.script_render_service import ScriptRenderService
        self._script_renderer = ScriptRenderService(pm)

        # Sub-service: prototype activation (P2-1 extraction)
        from renpy_mcp.services.prototype_activation_service import PrototypeActivationService
        self._activator = PrototypeActivationService(pm)

        # Sub-service: scene generation (P2-1 extraction)
        from renpy_mcp.services.scene_generation_service import SceneGenerationService
        self._scene_generator = SceneGenerationService(pm, provider)

        # Sub-service: asset generation (P2-1 extraction)
        from renpy_mcp.services.asset_generation_service import AssetGenerationService
        self._asset_generator = AssetGenerationService(pm, script_renderer=self._script_renderer)

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
    # Phase 6: Style bible inference and contract assembly
    # ------------------------------------------------------------------

    @staticmethod
    def infer_style_bible_from_blueprint(blueprint: ProjectBlueprint) -> ProjectStyleBible:
        """Infer a minimal project style bible from blueprint data."""
        from renpy_mcp.services.scene_generation_service import SceneGenerationService
        return SceneGenerationService.infer_style_bible_from_blueprint(blueprint)

    @staticmethod
    def infer_chapter_profiles_from_blueprint(blueprint: ProjectBlueprint) -> ChapterStyleProfiles:
        """Infer minimal chapter style profiles from blueprint chapter summaries."""
        from renpy_mcp.services.scene_generation_service import SceneGenerationService
        return SceneGenerationService.infer_chapter_profiles_from_blueprint(blueprint)

    def build_generation_contract(
        self,
        project_name: str,
        blueprint: ProjectBlueprint,
        chapter: ChapterSummary,
    ) -> GenerationContract:
        """Assemble a generation contract from project bible + chapter profile."""
        return self._scene_generator.build_generation_contract(project_name, blueprint, chapter)

    # ------------------------------------------------------------------
    # Multi-chapter scene generation
    # ------------------------------------------------------------------

    async def generate_all_chapter_scenes(
        self, project_name: str, blueprint: ProjectBlueprint
    ) -> dict[str, list[PrototypeScene]]:
        """Generate structured scene packages for all chapters in the blueprint."""
        return await self._scene_generator.generate_all_chapter_scenes(project_name, blueprint)

    # ------------------------------------------------------------------
    # Multi-chapter script generation
    # ------------------------------------------------------------------

    async def generate_multi_chapter_scripts(
        self, project_name: str, blueprint: ProjectBlueprint
    ) -> dict[str, Any]:
        """Generate multi-chapter prototype scripts from scene_packages snapshot.

        Reads the persisted ``meta/scene_packages.json``, generates background
        and character assets for all scenes, builds sprite plans, configures
        CJK-safe fonts, writes one ``.rpy`` per chapter, chains chapters via
        ``jump`` labels, updates ``meta/index.json`` with per-scene file/label
        mappings, and wires ``game/script.rpy`` to the first chapter start.

        This method is transactional: either all chapters are promoted and
        wired successfully, or the project is rolled back to its previous
        stable state.  After a successful commit, stale prototype index
        entries and chapter files from previous generations are removed.

        Args:
            project_name: Target project name.
            blueprint: The full project blueprint (used for character registry).

        Returns:
            ``{"chapters": [{"chapter_id": ..., "script_path": ..., "scene_count": ...}]}``

        Raises:
            RuntimeError: If ``scene_packages.json`` is missing or ProjectManager
                is not available.
        """
        if self.pm is None:
            raise RuntimeError("ProjectManager is required for multi-chapter script generation")

        snapshot = self.pm.read_scene_packages(project_name)
        if snapshot is None:
            raise RuntimeError(
                f"Project {project_name!r} has no scene packages. "
                "Run scene-packages/generate first."
            )

        project_dir = self.pm._project_dir(project_name)
        game_dir = project_dir / "game"

        # Sort chapters by order to ensure stable generation
        sorted_chapters = sorted(snapshot.chapters, key=lambda ch: ch.chapter_order)

        # ------------------------------------------------------------------
        # Phase 0: Build all PrototypeScene objects (no I/O)
        # ------------------------------------------------------------------
        chapter_data: list[dict] = []
        all_scenes: list[PrototypeScene] = []

        for i, ch in enumerate(sorted_chapters):
            scenes: list[PrototypeScene] = []
            scene_orders: dict[str, int] = {}
            for s in ch.scenes:
                entry_label = (
                    f"prototype_{ch.chapter_id}_start"
                    if s.scene_order == 1
                    else f"prototype_{ch.chapter_id}_scene_{s.scene_order}"
                )
                scene_orders[s.scene_id] = s.scene_order if s.scene_order else 1

                sprite_plan = [
                    SpritePlanItem(
                        character_name=sp.character_name,
                        character_id=sp.character_id,
                        sprite_path=sp.sprite_path,
                        sprite_placeholder=sp.sprite_placeholder,
                        sprite_renderable=sp.sprite_renderable,
                        sprite_quality_reason=sp.sprite_quality_reason,
                        position=sp.position,
                        expression=sp.expression,
                        layout_mode=sp.layout_mode,
                        transform_name=sp.transform_name,
                    )
                    for sp in s.sprite_plan
                ]

                scene = PrototypeScene(
                    scene_id=s.scene_id,
                    title=s.title,
                    summary=s.summary,
                    location=s.location,
                    location_visual_brief=s.location_visual_brief,
                    mood=s.mood,
                    characters_present=s.characters_present,
                    dialogue_beats=s.dialogue_beats,
                    sprite_plan=sprite_plan,
                    entry_label=entry_label,
                    next_scene_id=s.next_scene_id,
                )
                scenes.append(scene)
                all_scenes.append(scene)

            next_chapter_start_label: str | None = None
            if i + 1 < len(sorted_chapters):
                next_ch = sorted_chapters[i + 1]
                if next_ch.scenes:
                    next_chapter_start_label = f"prototype_{next_ch.chapter_id}_start"

            chapter_summary = ChapterSummary(
                id=ch.chapter_id,
                name=ch.chapter_name or ch.chapter_id,
                order=ch.chapter_order,
                scenes=[],
            )

            chapter_data.append({
                "scenes": scenes,
                "scene_orders": scene_orders,
                "next_chapter_start_label": next_chapter_start_label,
                "chapter_summary": chapter_summary,
                "ch": ch,
            })

        # ------------------------------------------------------------------
        # Phase 0.5: Generate assets and CJK font for all scenes
        # ------------------------------------------------------------------
        bg_assets = await self.generate_background_assets(project_name, all_scenes)
        char_assets = await self.generate_character_assets(project_name, blueprint, all_scenes)
        self.build_sprite_plan(all_scenes, char_assets, project_name=project_name)
        cjk_font_config = self.ensure_cjk_font_config(project_name)

        # ------------------------------------------------------------------
        # Phase 1: Write all chapter scripts to staging (no promote)
        # ------------------------------------------------------------------
        chapter_infos: list[dict] = []

        for data in chapter_data:
            staging_path = self.write_script(
                project_name,
                data["chapter_summary"],
                data["scenes"],
                background_assets=bg_assets,
                character_assets=char_assets,
                cjk_font_config=cjk_font_config,
                next_chapter_start_label=data["next_chapter_start_label"],
            )
            final_path = Path(self._final_path_from_staging(staging_path)).as_posix()

            chapter_infos.append({
                "chapter_id": data["ch"].chapter_id,
                "staging_path": staging_path,
                "final_path": final_path,
                "scenes": data["scenes"],
                "scene_ids": [s.scene_id for s in data["scenes"]],
                "scene_orders": data["scene_orders"],
            })

        # ------------------------------------------------------------------
        # Phase 2: Commit — atomic-ish promote + wire + index
        # ------------------------------------------------------------------
        new_scene_ids: set[str] = set()
        new_final_paths: set[str] = set()
        for info in chapter_infos:
            new_scene_ids.update(info["scene_ids"])
            new_final_paths.add(info["final_path"])

        import copy
        old_index = copy.deepcopy(self.pm.read_project_index(project_name) or {"scenes": {}})
        old_manifest = self.pm.read_prototype_manifest(project_name)

        promoted_paths: list[str] = []
        old_final_contents: dict[str, str] = {}

        # Determine first chapter entry label for manifest (before any mutation)
        first_label: str | None = None
        if sorted_chapters and sorted_chapters[0].scenes:
            first_label = f"prototype_{sorted_chapters[0].chapter_id}_start"

        chapter_results = [
            {
                "chapter_id": info["chapter_id"],
                "script_path": info["final_path"],
                "scene_count": len(info["scenes"]),
            }
            for info in chapter_infos
        ]

        manifest = PrototypeManifest(
            mode=None,
            entry_label=first_label,
            entry_file=chapter_infos[0]["final_path"] if chapter_infos else None,
            chapter_ids=[info["chapter_id"] for info in chapter_infos],
            script_files=[info["final_path"] for info in chapter_infos],
            source="prototype",
            generated_from="scene_packages",
            updated_at=datetime.utcnow().isoformat(),
        )

        try:
            # 1. Promote all staging -> final
            for info in chapter_infos:
                staging_file = project_dir / info["staging_path"]
                final_file = project_dir / info["final_path"]
                if staging_file.exists():
                    if final_file.exists():
                        old_final_contents[info["final_path"]] = final_file.read_text(encoding="utf-8")
                    staging_file.replace(final_file)
                    promoted_paths.append(info["final_path"])

            # 2. Update index.json with all new scene entries
            index = self.pm.read_project_index(project_name) or {"scenes": {}}
            if "scenes" not in index:
                index["scenes"] = {}
            for info in chapter_infos:
                ch_id = info["chapter_id"]
                final_path = info["final_path"]
                scene_orders = info["scene_orders"]
                for s in info["scenes"]:
                    index["scenes"][s.scene_id] = {
                        "chapter_id": ch_id,
                        "scene_id": s.scene_id,
                        "title": s.title,
                        "summary": s.summary,
                        "location": s.location,
                        "location_visual_brief": s.location_visual_brief,
                        "mood": s.mood,
                        "characters_present": s.characters_present,
                        "dialogue_beats": [
                            b.model_dump(mode="json") for b in s.dialogue_beats
                        ],
                        "sprite_plan": [
                            sp.model_dump(mode="json", exclude={"sprite_check_path"})
                            for sp in s.sprite_plan
                        ],
                        "next_scene_id": s.next_scene_id,
                        "label": s.entry_label,
                        "file_path": final_path,
                        "source": "prototype",
                        "order": scene_orders.get(s.scene_id, 1),
                        "status": "generated",
                    }
            self.pm.write_project_index(project_name, index)

            # 3. Write prototype_manifest.json (candidate, not yet active)
            self.pm.write_prototype_manifest(project_name, manifest)

        except Exception:
            # Rollback: restore index (best-effort), restore manifest (best-effort),
            # remove newly promoted files, then restore old final files
            try:
                self.pm.write_project_index(project_name, old_index)
            except Exception:
                logger.warning(
                    "Failed to restore index during rollback", exc_info=True
                )
            try:
                if old_manifest is not None:
                    self.pm.write_prototype_manifest(project_name, old_manifest)
                else:
                    # First-time generate failed: remove orphaned manifest
                    manifest_path = (
                        self.pm._project_dir(project_name) / "meta" / "prototype_manifest.json"
                    )
                    if manifest_path.exists():
                        manifest_path.unlink()
            except Exception:
                logger.warning(
                    "Failed to restore manifest during rollback", exc_info=True
                )
            for fp in promoted_paths:
                f = project_dir / fp
                if f.exists():
                    f.unlink()
            # Restore old final files that were overwritten during promote
            for fp, content in old_final_contents.items():
                old_file = project_dir / fp
                old_file.write_text(content, encoding="utf-8")
            # Clean up any leftover staging files from this round
            for info in chapter_infos:
                staging_file = project_dir / info["staging_path"]
                if staging_file.exists():
                    staging_file.unlink()
            raise

        # ------------------------------------------------------------------
        # Post-commit cleanup: remove stale prototype entries and files
        # ------------------------------------------------------------------
        # 4. Remove stale prototype index entries
        index = self.pm.read_project_index(project_name) or {"scenes": {}}
        if "scenes" in index:
            stale_ids = [
                sid for sid, entry in list(index["scenes"].items())
                if isinstance(entry, dict)
                and entry.get("source") == "prototype"
                and sid not in new_scene_ids
            ]
            if stale_ids:
                for sid in stale_ids:
                    del index["scenes"][sid]
                self.pm.write_project_index(project_name, index)

        # 5. Remove stale prototype files
        new_file_names = {Path(p).name for p in new_final_paths}
        if game_dir.exists():
            for proto_file in game_dir.glob("prototype_*.rpy"):
                if proto_file.name not in new_file_names:
                    try:
                        proto_file.unlink()
                    except OSError:
                        logger.warning("Failed to remove stale prototype file: %s", proto_file)

        return {"chapters": chapter_results}

    # ------------------------------------------------------------------
    # Prototype activation
    # ------------------------------------------------------------------

    def activate_multi_chapter_prototype(self, project_name: str) -> dict[str, Any]:
        """Activate a previously generated multi-chapter prototype as the runtime entry."""
        return self._activator.activate_multi_chapter_prototype(project_name)

    def activate_single_chapter_prototype(
        self,
        project_name: str,
        entry_label: str,
        entry_file: str,
        chapter_ids: list[str],
        script_files: list[str],
    ) -> None:
        """Write the prototype manifest for an active single-chapter prototype."""
        return self._activator.activate_single_chapter_prototype(
            project_name, entry_label, entry_file, chapter_ids, script_files,
        )

    # ------------------------------------------------------------------
    # Prototype runtime readiness
    # ------------------------------------------------------------------

    def _read_managed_entry_label(self, project_name: str) -> str | None:
        """Read the current wired entry label from game/script.rpy managed region."""
        return self._activator.read_managed_entry_label(project_name)

    def get_prototype_runtime_status(self, project_name: str) -> dict:
        """Return the full prototype readiness status."""
        return self._activator.get_prototype_runtime_status(project_name)

    # ------------------------------------------------------------------
    # Scene generation (LLM)
    # ------------------------------------------------------------------

    def _validate_scene_consistency(self, scenes: list[PrototypeScene]) -> None:
        """Validate and auto-correct scene consistency rules."""
        return self._scene_generator._validate_scene_consistency(scenes)

    async def generate_scenes(
        self,
        chapter: ChapterSummary,
        blueprint: ProjectBlueprint,
        contract: GenerationContract | None = None,
    ) -> list[PrototypeScene]:
        """Generate 2-4 structured scenes for the prototype chapter via LLM."""
        return await self._scene_generator.generate_scenes(chapter, blueprint, contract=contract)

    # ------------------------------------------------------------------
    # Script writeback
    # ------------------------------------------------------------------

    def _staging_path_from_final(self, final_path: str) -> str:
        """Derive the staging path from a final prototype script path."""
        from renpy_mcp.services.script_render_service import staging_path_from_final
        return staging_path_from_final(final_path)

    def _final_path_from_staging(self, staging_path: str) -> str:
        """Derive the final path from a staging prototype script path."""
        from renpy_mcp.services.script_render_service import final_path_from_staging
        return final_path_from_staging(staging_path)

    def _runtime_asset_relpath(self, project_dir: Path, asset_path: Path, round_id: str | None = None) -> str:
        """Return the final project-relative path for a generated asset."""
        return self._asset_generator._runtime_asset_relpath(project_dir, asset_path, round_id)

    def _assess_background_composition(self, image_path: Path) -> tuple[bool, str]:
        """Reject obviously subject-heavy background plates."""
        return self._asset_generator._assess_background_composition(image_path)

    def _cjk_runtime_override_lines(self) -> list[str]:
        """Return reusable runtime CJK font override lines."""
        return self._script_renderer.cjk_runtime_override_lines()

    # ------------------------------------------------------------------
    # Background asset generation
    # ------------------------------------------------------------------

    async def generate_background_assets(
        self,
        project_name: str,
        scenes: list[PrototypeScene],
        round_id: str | None = None,
        contract: GenerationContract | None = None,
    ) -> dict[str, dict]:
        """Generate background images for each scene."""
        return await self._asset_generator.generate_background_assets(
            project_name, scenes, round_id=round_id, contract=contract,
        )

    def _generate_placeholder_background(self, file_path: Path, scene: PrototypeScene) -> None:
        """Generate a simple colored placeholder background using PIL."""
        return self._asset_generator._generate_placeholder_background(file_path, scene)

    # ------------------------------------------------------------------
    # Character sprite asset generation
    # ------------------------------------------------------------------

    async def generate_character_assets(
        self,
        project_name: str,
        blueprint: ProjectBlueprint,
        scenes: list[PrototypeScene],
        round_id: str | None = None,
        contract: GenerationContract | None = None,
    ) -> dict[str, dict]:
        """Generate character sprite images for all characters in prototype scenes."""
        return await self._asset_generator.generate_character_assets(
            project_name, blueprint, scenes, round_id=round_id, contract=contract,
        )

    def _generate_placeholder_character(self, file_path: Path, char_name: str) -> None:
        """Generate a transparent placeholder character sprite using PIL."""
        return self._asset_generator._generate_placeholder_character(file_path, char_name)

    def _resolve_layout_mode(self, char_count: int) -> str:
        return self._script_renderer._resolve_layout_mode(char_count)

    def _character_subject_height_guidance(self, layout_mode: str) -> str:
        return self._script_renderer._character_subject_height_guidance(layout_mode)

    def build_sprite_plan(
        self,
        scenes: list[PrototypeScene],
        character_assets: dict[str, dict],
        project_name: str | None = None,
    ) -> None:
        """Assign sprite plans to each scene based on characters_present and available assets."""
        return self._script_renderer.build_sprite_plan(scenes, character_assets, project_name)

    # ------------------------------------------------------------------
    # CJK font configuration
    # ------------------------------------------------------------------

    def ensure_cjk_font_config(self, project_name: str, round_id: str | None = None) -> dict:
        """Ensure the project has CJK-safe font configuration."""
        return self._asset_generator.ensure_cjk_font_config(project_name, round_id=round_id)
    def _build_character_registry(self, scenes: list[PrototypeScene]) -> dict[str, str]:
        """Map display names to safe Ren'Py character identifiers.

        Only characters listed in characters_present are registered.
        Dialogue speakers not in this registry will fall back to narration.
        """
        return self._script_renderer.build_character_registry(scenes)

    def _extract_bg_path(self, bg_asset: Any) -> Path | None:
        """Extract path from background asset (supports dict and legacy Path)."""
        return self._script_renderer._extract_bg_path(bg_asset)

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

        Delegates to :class:`ScriptRenderService`.
        """
        return self._script_renderer.write_script(
            project_name,
            chapter,
            scenes,
            background_assets=background_assets,
            character_assets=character_assets,
            cjk_font_config=cjk_font_config,
            next_chapter_start_label=next_chapter_start_label,
        )
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
        """Update game/script.rpy to call the prototype entry label."""
        return self._activator.wire_main_script_to_prototype(project_name, entry_label)

    # ------------------------------------------------------------------
    # Main script backup / restore
    # ------------------------------------------------------------------

    def backup_main_script(self, project_name: str) -> str | None:
        """Return the current content of game/script.rpy for potential rollback."""
        return self._activator.backup_main_script(project_name)

    def restore_main_script(self, project_name: str, content: str | None) -> None:
        """Restore game/script.rpy to a previously backed-up content."""
        return self._activator.restore_main_script(project_name, content)

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
        """Finalize prototype replacement by promoting the staging script and removing old artifacts."""
        return self._activator.commit_prototype_replacement(
            project_name, new_scene_ids, staging_script_path, round_id,
        )

    def rollback_prototype_generation(
        self,
        project_name: str,
        staging_script_path: str | None,
        new_scene_ids: list[str],
        old_script_content: str | None,
        generated_asset_paths: list[str] | None = None,
        round_id: str | None = None,
    ) -> None:
        """Rollback a failed prototype generation round."""
        return self._activator.rollback_prototype_generation(
            project_name,
            staging_script_path,
            new_scene_ids,
            old_script_content,
            generated_asset_paths,
            round_id,
        )

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
        """Update meta/index.json with full prototype scene metadata."""
        return self._activator.update_index(
            project_name, chapter, scenes, script_path,
            background_assets, character_assets, cjk_font_config,
        )
