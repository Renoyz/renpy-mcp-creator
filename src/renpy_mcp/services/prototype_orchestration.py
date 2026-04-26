"""Prototype orchestration service — 10-step pipeline coordination.

Extracted from ``BlueprintOrchestrator.handle_confirmation_response`` (P2-3)
so that the prototype generation pipeline can be:

* unit-tested with mocked sub-services (no WebSocket)
* reused outside the chat confirmation flow
* reasoned about independently of transport
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from ..blueprint.models import ProjectBlueprint
from ..services.project_manager import ProjectManager

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int], Awaitable[None]]


@dataclass
class PipelineResult:
    """Result of a prototype generation pipeline run."""

    success: bool = True
    prototype_error: str | None = None
    build_error: str | None = None


class PrototypeOrchestrationService:
    """Coordinates the 10-step prototype generation pipeline.

    Decoupled from WebSocket transport — progress is reported via an
    optional async callback.
    """

    def __init__(self, pm: ProjectManager) -> None:
        self.pm = pm

    async def _run_generation_steps(
        self,
        project_name: str,
        draft: ProjectBlueprint,
        on_progress: ProgressCallback | None = None,
    ) -> tuple[
        str | None,    # staging_path
        list[str],     # new_scene_ids
        str | None,    # old_script_content
        dict | None,   # bg_assets
        dict | None,   # char_assets
        dict | None,   # cjk_font_config
        str | None,    # round_id
        str | None,    # final_path
    ]:
        """Run the 10 generation steps, returning intermediate artifacts."""
        from ..web.chat_ws import _get_provider
        from ..services.prototype_generation_service import PrototypeGenerationService

        provider = _get_provider()
        service = PrototypeGenerationService(self.pm, provider)
        chapter = service.select_prototype_chapter(draft)
        round_id = f"r{uuid.uuid4().hex[:8]}"

        contract = service.build_generation_contract(project_name, draft, chapter)

        # Step 1: generate scenes
        if on_progress:
            await on_progress("Generating scenes...", 15)
        scenes = await service.generate_scenes(chapter, draft, contract=contract)
        new_scene_ids = [s.scene_id for s in scenes]

        # Step 2: generate background assets
        if on_progress:
            await on_progress("Generating backgrounds...", 35)
        bg_assets = await service.generate_background_assets(
            project_name, scenes, round_id=round_id, contract=contract,
        )

        # Step 3: generate character sprite assets
        if on_progress:
            await on_progress("Generating characters...", 55)
        char_assets = await service.generate_character_assets(
            project_name, draft, scenes, round_id=round_id, contract=contract,
        )

        # Step 4: build sprite plans
        service.build_sprite_plan(scenes, char_assets, project_name=project_name)

        # Step 5: ensure CJK font configuration
        cjk_font_config = service.ensure_cjk_font_config(project_name, round_id=round_id)

        # Step 6: write prototype script to staging
        if on_progress:
            await on_progress("Writing script...", 75)
        staging_path = service.write_script(
            project_name, chapter, scenes,
            background_assets=bg_assets, character_assets=char_assets,
            cjk_font_config=cjk_font_config,
        )
        final_path = service._final_path_from_staging(staging_path)

        # Step 7: backup main script
        old_script_content = service.backup_main_script(project_name)

        # Step 8: wire main script to prototype entry
        service.wire_main_script_to_prototype(project_name, scenes[0].entry_label)

        # Step 9: update index
        service.update_index(
            project_name, chapter, scenes, final_path,
            background_assets=bg_assets, character_assets=char_assets,
            cjk_font_config=cjk_font_config,
        )

        # Step 10: commit
        if on_progress:
            await on_progress("Committing prototype...", 90)
        service.commit_prototype_replacement(
            project_name, new_scene_ids, staging_path, round_id=round_id,
        )

        # Step 10b: activate single-chapter prototype
        service.activate_single_chapter_prototype(
            project_name,
            entry_label=scenes[0].entry_label,
            entry_file=final_path,
            chapter_ids=[chapter.id],
            script_files=[final_path],
        )

        return (staging_path, new_scene_ids, old_script_content,
                bg_assets, char_assets, cjk_font_config, round_id, final_path)

    async def _run_auto_build(self, project_name: str) -> None:
        """Run the auto-build step after successful prototype generation."""
        from ..models import BuildRequest, BuildResult
        from ..services.build_manager import BuildManager
        from ..config import get_settings
        from ..web.fastapi_app import _write_build_status

        _write_build_status(project_name, "building", "Building playable prototype...", None)

        if os.environ.get("RENPY_MCP_MOCK_BUILD"):
            settings = get_settings()
            build_dir = (
                settings.workspace / f"{project_name}-dists" / f"{project_name}-web"
            )
            build_dir.mkdir(parents=True, exist_ok=True)
            (build_dir / "index.html").write_text(
                "<html><body>mock preview</body></html>", encoding="utf-8"
            )
            build_result = BuildResult(
                project_name=project_name, target="web",
                success=True, output_path=build_dir,
            )
        else:
            build_manager = BuildManager(get_settings())
            build_result = await build_manager.build(
                BuildRequest(project_name=project_name, target="web")
            )

        if not build_result.success:
            error = build_result.error or "Build failed"
            _write_build_status(project_name, "failed", error, None)
            raise RuntimeError(error)

        _write_build_status(
            project_name, "success",
            f"Prototype built to {build_result.output_path}",
            build_result.output_path,
        )

    async def run_pipeline(
        self,
        project_name: str,
        draft: ProjectBlueprint,
        on_progress: ProgressCallback | None = None,
    ) -> PipelineResult:
        """Run the complete prototype generation + auto-build pipeline.

        Returns a ``PipelineResult`` describing success/failure.
        """
        result = PipelineResult()

        # Preparation progress
        if on_progress:
            await on_progress("Preparing prototype generation...", 1)

        # --- Generation steps ---
        staging_path: str | None = None
        new_scene_ids: list[str] = []
        old_script_content: str | None = None
        bg_assets: dict | None = None
        char_assets: dict | None = None
        cjk_font_config: dict | None = None
        round_id: str | None = None

        try:
            (staging_path, new_scene_ids, old_script_content,
             bg_assets, char_assets, cjk_font_config, round_id, _) = \
                await self._run_generation_steps(project_name, draft, on_progress)
        except Exception as e:
            result.success = False
            result.prototype_error = str(e)
            logger.exception("Prototype generation failed for project %s", project_name)
            # Rollback
            self._attempt_rollback(
                project_name, staging_path, new_scene_ids,
                old_script_content, bg_assets, char_assets,
                cjk_font_config, round_id,
            )
            return result

        # --- Auto-build ---
        try:
            await self._run_auto_build(project_name)
        except Exception as e:
            result.build_error = str(e)
            logger.exception("Prototype auto-build failed for project %s", project_name)

        return result

    def _attempt_rollback(
        self,
        project_name: str,
        staging_path: str | None,
        new_scene_ids: list[str],
        old_script_content: str | None,
        bg_assets: dict | None,
        char_assets: dict | None,
        cjk_font_config: dict | None,
        round_id: str | None,
    ) -> None:
        """Best-effort rollback of partial prototype artifacts."""
        try:
            from ..services.prototype_generation_service import PrototypeGenerationService

            new_asset_paths: list[str] = []
            if bg_assets:
                for info in bg_assets.values():
                    if info.get("is_new_file") and info.get("path"):
                        new_asset_paths.append(str(info["path"]))
            if char_assets:
                for info in char_assets.values():
                    if info.get("is_new_file") and info.get("path"):
                        new_asset_paths.append(info["path"])
                    if info.get("intermediate_paths"):
                        new_asset_paths.extend(info["intermediate_paths"])
            if cjk_font_config:
                new_asset_paths.extend(cjk_font_config.get("new_files", []))

            rollback_service = PrototypeGenerationService(self.pm, None)
            rollback_service.rollback_prototype_generation(
                project_name, staging_path, new_scene_ids, old_script_content,
                generated_asset_paths=new_asset_paths,
                round_id=round_id,
            )
        except Exception:
            logger.exception(
                "Prototype rollback also failed for project %s", project_name
            )
