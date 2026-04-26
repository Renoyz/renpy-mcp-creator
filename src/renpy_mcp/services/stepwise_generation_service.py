"""Service layer for Tier 4 stepwise generation orchestration."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from renpy_mcp.services.imported_asset_service import ImportedAssetService
from renpy_mcp.services.prototype_activation_service import PrototypeActivationService
from renpy_mcp.services.script_render_service import ScriptRenderService, final_path_from_staging

from renpy_mcp.blueprint.models import ChapterSummary, PrototypeManifest
from renpy_mcp.services.prototype_generation_service import PrototypeScene

if TYPE_CHECKING:
    from renpy_mcp.services.project_manager import ProjectManager


class StepwiseGenerationService:
    """Owns state + commit logic for stepwise preview/accept workflows."""

    VALID_STATES = [
        "idle",
        "scene_outline_draft",
        "scene_outline_confirmed",
        "character_assets_draft",
        "character_assets_confirmed",
        "background_assets_draft",
        "background_assets_confirmed",
        "script_preview",
        "committed",
        "failed",
    ]

    def __init__(self, pm: "ProjectManager", imported_asset_service: ImportedAssetService | None = None) -> None:
        if pm is None:
            raise ValueError("ProjectManager is required")
        self.pm = pm
        self.imported_asset_service = imported_asset_service or ImportedAssetService(pm)
        self._script_renderer = ScriptRenderService(pm)
        self._prototype_activation = PrototypeActivationService(pm)

    # ------------------------------------------------------------------
    # State persistence helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_round_id(counter: int) -> str:
        return f"r{counter:04d}"

    def _state_path(self, project_name: str) -> Path:
        return self.pm._project_dir(project_name) / "meta" / "generation_state.json"

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "state": "idle",
            "round_id": None,
            "character_assets": {},
            "background_assets": {},
            "script_preview": None,
        }

    @staticmethod
    def _safe_state(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "state": state.get("state", "idle"),
            "round_id": state.get("round_id"),
            "character_assets": state.get("character_assets", {}),
            "background_assets": state.get("background_assets", {}),
            "script_preview": state.get("script_preview"),
        }

    def get_state(self, project_name: str) -> dict[str, Any]:
        path = self._state_path(project_name)
        if not path.exists():
            return self._empty_state()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"generation_state.json for {project_name!r} is invalid") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"generation_state.json for {project_name!r} is invalid")
        return self._safe_state(cast(dict[str, Any], payload))

    def save_state(self, project_name: str, state: dict[str, Any]) -> None:
        state = self._safe_state(state)
        if state["state"] not in self.VALID_STATES:
            raise ValueError(f"Invalid state value: {state['state']!r}")
        path = self._state_path(project_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Round management
    # ------------------------------------------------------------------

    def _new_round_id(self, project_dir: Path) -> str:
        staging_root = project_dir / "game" / "__staging__"
        if not staging_root.exists():
            return self._safe_round_id(1)

        max_round = 0
        for candidate in staging_root.glob("r*"):
            if not candidate.is_dir():
                continue
            name = candidate.name
            if not (name.startswith("r") and len(name) > 1):
                continue
            number = name[1:]
            if number.isdigit():
                max_round = max(max_round, int(number))

        return self._safe_round_id(max_round + 1)

    def _round_for_project(self, project_name: str, state: dict[str, Any]) -> str:
        round_id = state.get("round_id")
        if isinstance(round_id, str) and round_id:
            return round_id
        project_dir = self.pm._project_dir(project_name)
        return self._new_round_id(project_dir)

    # ------------------------------------------------------------------
    # Asset collection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_accepted_slot(slot: dict[str, Any]) -> bool:
        return slot.get("status") == "accepted"

    @staticmethod
    def _normalize_target(value: str) -> str:
        return ImportedAssetService._normalize_component(value, "asset")

    def _slot_asset_id(self, kind: str, target: str, variant: str) -> str:
        return self.imported_asset_service._make_asset_id(kind, target, variant)

    @staticmethod
    def _slot_target(slot: dict[str, Any]) -> str:
        target = slot.get("target")
        return target if isinstance(target, str) else ""

    def _find_asset(self, state: dict[str, Any], asset_id: str) -> tuple[str, dict[str, Any]] | None:
        for collection, assets in (("character_assets", state["character_assets"]), ("background_assets", state["background_assets"])):
            if asset_id in assets:
                return collection, assets[asset_id]
        return None

    @classmethod
    def _normalized_slot_match_key(cls, target: str) -> str:
        return cls._normalize_target(target).casefold()

    @classmethod
    def _normalized_variant_match_key(cls, variant: str) -> str:
        return cls._normalize_target(variant).casefold()

    def _find_existing_slot_id(
        self,
        state: dict[str, Any],
        collection: str,
        kind: str,
        target: str,
        variant: str,
    ) -> str | None:
        target_key = self._normalized_slot_match_key(target)
        variant_key = self._normalized_variant_match_key(variant)
        for slot_id, slot in state[collection].items():
            slot_target = self._slot_target(slot)
            if (
                self._normalized_slot_match_key(slot_target) == target_key
                and self._normalized_variant_match_key(str(slot.get("variant", ""))) == variant_key
                and slot.get("kind") == kind
            ):
                return slot_id
        return None

    def _all_required_slot_ids(self, project_name: str, state: dict[str, Any], collection: str) -> list[str]:
        scene_packages = self.pm.read_scene_packages(project_name)
        if scene_packages is None:
            return list(state[collection].keys())

        if collection == "character_assets":
            required_targets: set[str] = set()
            for chapter in scene_packages.chapters:
                for scene in chapter.scenes:
                    for character in scene.characters_present:
                        required_targets.add(self._normalize_target(character))
            return [
                slot_id for slot_id, slot in state[collection].items()
                if self._slot_target(slot) and self._normalize_target(self._slot_target(slot)) in required_targets
            ]

        required_scene_ids: set[str] = set()
        for chapter in scene_packages.chapters:
            for scene in chapter.scenes:
                required_scene_ids.add(self._normalize_target(scene.scene_id))
        return [
            slot_id for slot_id, slot in state[collection].items()
            if self._slot_target(slot) and self._normalize_target(self._slot_target(slot)) in required_scene_ids
        ]

    def _ensure_required_slots_accepted(self, project_name: str, state: dict[str, Any], collection: str) -> None:
        slot_ids = self._all_required_slot_ids(project_name, state, collection)
        if not slot_ids:
            if not self.pm.read_scene_packages(project_name):
                return
            raise ValueError(f"No {collection.replace('_', ' ')} to confirm")
        for slot_id in slot_ids:
            slot = state[collection][slot_id]
            if slot.get("status") != "accepted":
                label = "Character" if collection == "character_assets" else "Background"
                raise ValueError(f"{label} asset {slot_id} must be accepted first")

    def _ensure_required_character_slots(self, project_name: str, state: dict[str, Any]) -> None:
        scene_packages = self.pm.read_scene_packages(project_name)
        if scene_packages is None:
            return

        for chapter in scene_packages.chapters:
            for scene in chapter.scenes:
                for character in scene.characters_present:
                    safe_character = self._normalize_target(character)
                    if not safe_character:
                        continue
                    char_asset_id = self._slot_asset_id("character_sprite", safe_character, "normal")
                    state["character_assets"].setdefault(
                        char_asset_id,
                        self._build_empty_slot(
                            kind="character_sprite",
                            target=safe_character,
                            variant="normal",
                        ),
                    )

    def _ensure_required_background_slots(self, project_name: str, state: dict[str, Any]) -> None:
        scene_packages = self.pm.read_scene_packages(project_name)
        if scene_packages is None:
            return

        for chapter in scene_packages.chapters:
            for scene in chapter.scenes:
                safe_scene_id = self._normalize_target(scene.scene_id)
                if not safe_scene_id:
                    continue
                bg_asset_id = self._slot_asset_id("background", safe_scene_id, "main")
                state["background_assets"].setdefault(
                    bg_asset_id,
                    self._build_empty_slot(
                        kind="background",
                        target=safe_scene_id,
                        variant="main",
                    ),
                )

    def ensure_required_slots(self, project_name: str, state: dict[str, Any]) -> None:
        """Create required slots from scene packages when available."""
        self._ensure_required_character_slots(project_name, state)
        self._ensure_required_background_slots(project_name, state)

    def _build_empty_slot(self, *, kind: str, target: str, variant: str) -> dict[str, Any]:
        return {
            "asset_id": self._slot_asset_id(kind, self._normalize_target(target), variant),
            "kind": kind,
            "target": self._normalize_target(target),
            "variant": variant,
            "source": None,
            "status": "empty",
            "placeholder": False,
            "renderable": False,
        }

    # ------------------------------------------------------------------
    # Flow transitions
    # ------------------------------------------------------------------

    def _require_state(self, state: dict[str, Any], *allowed: str, action: str) -> None:
        if state["state"] not in allowed:
            raise ValueError(f"Cannot {action} in state {state['state']!r}")

    def start_scene_outline(self, project_name: str) -> dict[str, Any]:
        state = self.get_state(project_name)
        self._require_state(
            state,
            "idle",
            "scene_outline_draft",
            "scene_outline_confirmed",
            action="start scene outline",
        )
        state["state"] = "scene_outline_draft"
        self.save_state(project_name, state)
        return state

    def confirm_scene_outline(self, project_name: str) -> dict[str, Any]:
        state = self.get_state(project_name)
        self._require_state(state, "scene_outline_draft", action="confirm scene outline")
        state["state"] = "scene_outline_confirmed"
        self.save_state(project_name, state)
        return state

    def start_characters(self, project_name: str) -> dict[str, Any]:
        state = self.get_state(project_name)
        self._require_state(
            state,
            "idle",
            "scene_outline_draft",
            "scene_outline_confirmed",
            "character_assets_draft",
            "character_assets_confirmed",
            action="start characters",
        )
        if state.get("round_id") is None:
            state["round_id"] = self._round_for_project(project_name, state)
        state["state"] = "character_assets_draft"
        self._ensure_required_character_slots(project_name, state)
        self.save_state(project_name, state)
        return state

    def start_backgrounds(self, project_name: str) -> dict[str, Any]:
        state = self.get_state(project_name)
        self._require_state(
            state,
            "character_assets_draft",
            "character_assets_confirmed",
            "background_assets_draft",
            "background_assets_confirmed",
            action="start backgrounds",
        )
        if state.get("round_id") is None:
            state["round_id"] = self._round_for_project(project_name, state)
        state["state"] = "background_assets_draft"
        self._ensure_required_background_slots(project_name, state)
        self.save_state(project_name, state)
        return state

    # ------------------------------------------------------------------
    # Slot operations
    # ------------------------------------------------------------------

    def upload_character_asset(
        self,
        *,
        project_name: str,
        character_id: str,
        variant: str,
        filename: str,
        file_bytes: bytes,
        replace: bool = False,
    ) -> dict[str, Any]:
        state = self.get_state(project_name)
        self._require_state(
            state,
            "character_assets_draft",
            "character_assets_confirmed",
            "background_assets_draft",
            "background_assets_confirmed",
            action="upload character asset",
        )
        round_id = self._round_for_project(project_name, state)
        existing_slot_id = self._find_existing_slot_id(
            state,
            "character_assets",
            "character_sprite",
            character_id,
            variant,
        )
        target_slot_id = existing_slot_id or self._slot_asset_id(
            kind="character_sprite",
            target=self._normalize_target(character_id),
            variant=self._normalize_target(variant),
        )
        existing = state["character_assets"].get(target_slot_id)
        if existing is not None and existing.get("status") == "accepted" and not replace:
            raise ValueError(f"Asset {target_slot_id} is already accepted")

        slot = self.imported_asset_service.import_image(
            project_name=project_name,
            round_id=round_id,
            kind="character_sprite",
            target=character_id,
            variant=variant,
            filename=filename,
            file_bytes=file_bytes,
        )
        original_slot_id = slot["asset_id"]

        if existing is not None:
            # Keep required-slot identity if it was pre-created from scene packages.
            slot["asset_id"] = existing.get("asset_id", target_slot_id)
            slot["target"] = existing.get("target", slot["target"])
            slot["kind"] = existing.get("kind", slot["kind"])
            slot["variant"] = existing.get("variant", slot["variant"])
            slot["placeholder"] = existing.get("placeholder", slot["placeholder"])

        state["character_assets"][target_slot_id] = slot
        if original_slot_id != target_slot_id:
            state["character_assets"].pop(original_slot_id, None)

        self._ensure_required_character_slots(project_name, state)
        state["round_id"] = round_id
        if state["state"] == "character_assets_confirmed":
            state["state"] = "character_assets_draft"
        self.save_state(project_name, state)
        return slot

    def upload_background_asset(
        self,
        *,
        project_name: str,
        location_id: str,
        variant: str,
        filename: str,
        file_bytes: bytes,
        replace: bool = False,
    ) -> dict[str, Any]:
        state = self.get_state(project_name)
        self._require_state(
            state,
            "background_assets_draft",
            "background_assets_confirmed",
            "character_assets_confirmed",
            action="upload background asset",
        )
        round_id = self._round_for_project(project_name, state)
        existing_slot_id = self._find_existing_slot_id(
            state,
            "background_assets",
            "background",
            location_id,
            variant,
        )
        target_slot_id = existing_slot_id or self._slot_asset_id(
            kind="background",
            target=self._normalize_target(location_id),
            variant=self._normalize_target(variant),
        )
        existing = state["background_assets"].get(target_slot_id)
        if existing is not None and existing.get("status") == "accepted" and not replace:
            raise ValueError(f"Asset {target_slot_id} is already accepted")

        slot = self.imported_asset_service.import_image(
            project_name=project_name,
            round_id=round_id,
            kind="background",
            target=location_id,
            variant=variant,
            filename=filename,
            file_bytes=file_bytes,
        )
        original_slot_id = slot["asset_id"]

        if existing is not None:
            # Keep required-slot identity if it was pre-created from scene packages.
            slot["asset_id"] = existing.get("asset_id", target_slot_id)
            slot["target"] = existing.get("target", slot["target"])
            slot["kind"] = existing.get("kind", slot["kind"])
            slot["variant"] = existing.get("variant", slot["variant"])
            slot["placeholder"] = existing.get("placeholder", slot["placeholder"])

        state["background_assets"][target_slot_id] = slot
        if original_slot_id != target_slot_id:
            state["background_assets"].pop(original_slot_id, None)

        self._ensure_required_background_slots(project_name, state)
        state["round_id"] = round_id
        if state["state"] == "background_assets_confirmed":
            state["state"] = "background_assets_draft"
        self.save_state(project_name, state)
        return slot

    def accept_asset(self, project_name: str, asset_id: str, *, allow_non_renderable: bool = False) -> dict[str, Any]:
        state = self.get_state(project_name)
        found = self._find_asset(state, asset_id)
        if not found:
            raise ValueError(f"Asset {asset_id!r} not found")

        collection, asset = found
        status = asset.get("status")
        source = asset.get("source")

        if status not in {"uploaded", "generated"}:
            raise ValueError(
                f"Cannot accept asset {asset_id} before it is uploaded or generated (status={status!r})"
            )

        if source not in {"uploaded", "generated"}:
            raise ValueError(
                f"Cannot accept asset {asset_id} with unsupported source {source!r}; must be uploaded/generated"
            )

        if not isinstance(asset.get("path"), str) and not isinstance(asset.get("staging_path"), str):
            raise ValueError(f"Cannot accept asset {asset_id} because it has no staged or final path")

        if asset.get("placeholder"):
            raise ValueError(f"Asset {asset_id} is placeholder")

        if collection == "character_assets" and not allow_non_renderable:
            if asset.get("renderable") is False:
                raise ValueError(f"Cannot accept non-renderable character asset {asset_id} without explicit override")

        asset["status"] = "accepted"
        state[collection][asset_id] = asset
        self.save_state(project_name, state)
        return asset

    def confirm_characters(self, project_name: str) -> dict[str, Any]:
        state = self.get_state(project_name)
        self._require_state(
            state,
            "character_assets_draft",
            "character_assets_confirmed",
            "background_assets_draft",
            "background_assets_confirmed",
            action="confirm characters",
        )
        self._ensure_required_character_slots(project_name, state)
        self._ensure_required_slots_accepted(project_name, state, "character_assets")
        if not state["character_assets"]:
            raise ValueError("No character assets to confirm")
        if state["state"] == "character_assets_draft":
            state["state"] = "character_assets_confirmed"
        self.save_state(project_name, state)
        return state

    def confirm_backgrounds(self, project_name: str) -> dict[str, Any]:
        state = self.get_state(project_name)
        self._require_state(
            state,
            "character_assets_confirmed",
            "background_assets_draft",
            "background_assets_confirmed",
            action="confirm backgrounds",
        )
        self._ensure_required_background_slots(project_name, state)
        self._ensure_required_slots_accepted(project_name, state, "background_assets")
        if not state["background_assets"]:
            raise ValueError("No background assets to confirm")
        state["state"] = "background_assets_confirmed"
        self.save_state(project_name, state)
        return state

    # ------------------------------------------------------------------
    # Preview and commit
    # ------------------------------------------------------------------

    def _collect_accepted(self, state: dict[str, Any], key: Literal["character_assets", "background_assets"]) -> dict[str, dict[str, Any]]:
        return {
            asset_id: slot
            for asset_id, slot in state[key].items()
            if self._is_accepted_slot(slot)
        }

    def _build_preview_plan(
        self,
        project_name: str,
        state: dict[str, Any],
    ) -> list[dict[str, Any]]:
        character_assets_accepted = self._collect_accepted(state, "character_assets")
        background_assets_accepted = self._collect_accepted(state, "background_assets")
        character_map: dict[str, dict[str, Any]] = {}
        background_map: dict[str, dict[str, Any]] = {}
        seen_character_targets: dict[str, str] = {}
        seen_background_targets: dict[str, str] = {}

        for slot in character_assets_accepted.values():
            target = self._slot_target(slot)
            if target:
                target_key = self._normalized_slot_match_key(target)
                if target_key in seen_character_targets:
                    raise ValueError("multiple variants for same character display name are accepted")
                seen_character_targets[target_key] = target
                character_map[target] = slot

        for slot in background_assets_accepted.values():
            target = self._slot_target(slot)
            if target:
                target_key = self._normalized_slot_match_key(target)
                if target_key in seen_background_targets:
                    raise ValueError("multiple variants for same background target are accepted")
                seen_background_targets[target_key] = target
                background_map[target] = slot

        scene_packages = self.pm.read_scene_packages(project_name)
        if scene_packages is None:
            scene_chars = list(character_map.keys())
            scenes: list[PrototypeScene] = []
            scene_id = "stepwise_scene"
            entry_label = "prototype_stepwise_start"
            scenes.append(
                PrototypeScene(
                    scene_id=scene_id,
                    title="Stepwise Preview",
                    summary="Runtime scene preview from stepwise imports.",
                    location="stepwise_preview",
                    location_visual_brief="",
                    mood="",
                    characters_present=scene_chars,
                    dialogue_beats=[],
                    entry_label=entry_label,
                    next_scene_id=None,
                )
            )
            if background_map:
                first_bg = next(iter(background_map.values()))
                background_map = {scene_id: first_bg}
            else:
                background_map = {}
            chapter = ChapterSummary(
                id="stepwise",
                name="Stepwise",
                order=1,
                scenes=[],
            )
            return [
                {
                    "chapter": chapter,
                    "scenes": scenes,
                    "character_assets": character_map,
                    "background_assets": background_map,
                    "scene_ids": [scene_id],
                    "final_script_path": None,
                    "staging_script_path": None,
                }
            ]

        plans: list[dict[str, Any]] = []
        for chapter in scene_packages.chapters:
            scene_order = 1
            scenes: list[PrototypeScene] = []
            for scene in chapter.scenes:
                resolved_scene_id = self._normalize_target(scene.scene_id) or f"scene_{scene_order}"
                entry_label = (
                    f"prototype_{chapter.chapter_id}_{resolved_scene_id}"
                    if scene_order == 1
                    else f"prototype_{chapter.chapter_id}_{resolved_scene_id}_start"
                )
                scenes.append(
                    PrototypeScene(
                        scene_id=resolved_scene_id,
                        title=scene.title,
                        summary=scene.summary,
                        location=scene.location,
                        location_visual_brief=scene.location_visual_brief,
                        mood=scene.mood,
                        characters_present=[c for c in scene.characters_present if c],
                        dialogue_beats=scene.dialogue_beats,
                        entry_label=entry_label,
                        next_scene_id=None,
                    )
                )
                scene_order += 1

            # Keep only required background keys mapped to the required scene ids.
            normalized_background_map: dict[str, dict[str, Any]] = {}
            for scene in scenes:
                slot = background_map.get(scene.scene_id)
                if slot is not None:
                    normalized_background_map[scene.scene_id] = slot
            chapter_background_map = normalized_background_map

            # Preserve character keys exactly as required scene names to match the registry.
            required_character_map: dict[str, dict[str, Any]] = {}
            for slot in character_assets_accepted.values():
                required_character_map[self._slot_target(slot)] = slot

            chapter_summary = ChapterSummary(
                id=chapter.chapter_id,
                name=chapter.chapter_name or chapter.chapter_id,
                order=chapter.chapter_order,
                scenes=[],
            )

            plans.append(
                {
                    "chapter": chapter_summary,
                    "scenes": scenes,
                    "character_assets": required_character_map,
                    "background_assets": chapter_background_map,
                    "scene_ids": [scene.scene_id for scene in scenes],
                    "final_script_path": None,
                    "staging_script_path": None,
                }
            )

        return plans

    def preview_script(self, project_name: str) -> dict[str, Any]:
        state = self.get_state(project_name)
        self._require_state(
            state,
            "character_assets_confirmed",
            "background_assets_confirmed",
            "script_preview",
            action="generate preview",
        )
        self._ensure_required_slots_accepted(project_name, state, "character_assets")
        self._ensure_required_slots_accepted(project_name, state, "background_assets")

        preview_plans = self._build_preview_plan(project_name, state)
        script_text_parts: list[str] = []
        staging_paths: list[str] = []
        script_files: list[str] = []
        chapter_ids: list[str] = []
        all_scene_ids: list[str] = []

        for idx, plan in enumerate(preview_plans):
            scenes = plan["scenes"]
            chapter = plan["chapter"]
            character_assets = plan["character_assets"]
            background_assets = plan["background_assets"]

            self._script_renderer.build_sprite_plan(scenes, character_assets, project_name=project_name)
            next_chapter_start_label = None
            if idx + 1 < len(preview_plans):
                next_scenes = preview_plans[idx + 1]["scenes"]
                next_chapter_start_label = next_scenes[0].entry_label if next_scenes else None

            staging_path = self._script_renderer.write_script(
                project_name=project_name,
                chapter=chapter,
                scenes=scenes,
                background_assets=background_assets,
                character_assets=character_assets,
                next_chapter_start_label=next_chapter_start_label,
            )
            if not isinstance(staging_path, str):
                raise RuntimeError("Failed to generate preview script")

            staging_path_obj = self.pm._project_dir(project_name) / staging_path
            if not staging_path_obj.exists():
                raise RuntimeError("Generated preview script is missing")

            script_text_parts.append(staging_path_obj.read_text(encoding="utf-8"))
            final_script_path = final_path_from_staging(staging_path)
            script_text_parts.append(f"\n# End of {final_script_path}\n")

            staging_paths.append(staging_path)
            script_files.append(final_script_path)
            chapter_ids.append(chapter.id)
            all_scene_ids.extend(plan["scene_ids"])

            plan["staging_script_path"] = staging_path
            plan["final_script_path"] = final_script_path

        script_text = "\n\n".join(script_text_parts)

        state["state"] = "script_preview"
        state["script_preview"] = {
            "staging_paths": staging_paths,
            "staging_path": staging_paths[0] if staging_paths else None,
            "script_files": script_files,
            "entry_label": preview_plans[0]["scenes"][0].entry_label if preview_plans else "prototype_stepwise_start",
            "scene_ids": all_scene_ids,
            "chapter_ids": chapter_ids,
        }
        self.save_state(project_name, state)

        return {
            "label": "script_preview",
            "script": script_text,
            "staging_paths": staging_paths,
            "staging_path": staging_paths[0] if staging_paths else None,
            "script_files": script_files,
            "entry_label": preview_plans[0]["scenes"][0].entry_label if preview_plans else "prototype_stepwise_start",
            "scene_ids": all_scene_ids,
        }

    def _restore_index(self, project_name: str, old_index_text: str | None) -> None:
        index_path = self.pm._project_dir(project_name) / "meta" / "index.json"
        if old_index_text is None:
            if index_path.exists():
                index_path.unlink()
            return
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(old_index_text, encoding="utf-8")

    def _restore_manifest(self, project_name: str, old_manifest_text: str | None) -> None:
        manifest_path = self.pm._project_dir(project_name) / "meta" / "prototype_manifest.json"
        if old_manifest_text is None:
            if manifest_path.exists():
                manifest_path.unlink()
            return
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(old_manifest_text, encoding="utf-8")

    def _collect_file_backups(self, project_dir: Path, file_paths: list[str]) -> dict[Path, bytes | None]:
        backups: dict[Path, bytes | None] = {}
        for file_path in file_paths:
            path = project_dir / file_path
            backups[path] = path.read_bytes() if path.exists() else None
        return backups

    def _restore_file_backups(self, backups: dict[Path, bytes | None]) -> None:
        for path, old in backups.items():
            if old is None:
                if path.exists():
                    path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(old)

    def _collect_existing_prototype_file_backups(self, project_dir: Path) -> dict[Path, bytes]:
        backups: dict[Path, bytes] = {}
        for proto_file in (project_dir / "game").glob("prototype_*.rpy"):
            if proto_file.is_file():
                backups[proto_file] = proto_file.read_bytes()
        return backups

    def _restore_prototype_file_backups(self, backups: dict[Path, bytes]) -> None:
        for path, old_content in backups.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(old_content)

    def _promote_round_staged_files(self, project_dir: Path, round_id: str) -> None:
        staging_dir = project_dir / "game" / "__staging__" / round_id
        if not staging_dir.exists():
            return

        for src in staging_dir.rglob("*"):
            if not src.is_file():
                continue
            if "__backup__" in src.as_posix():
                continue
            rel = src.relative_to(staging_dir)
            dst = project_dir / "game" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.replace(dst)

        try:
            import shutil

            shutil.rmtree(staging_dir)
        except OSError:
            pass

    def _collect_preview_asset_slots(self, preview_plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
        slots: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        for plan in preview_plans:
            for collection in ("character_assets", "background_assets"):
                assets = plan.get(collection)
                if not isinstance(assets, dict):
                    continue
                for slot in assets.values():
                    if not isinstance(slot, dict):
                        continue
                    path = slot.get("path")
                    if not isinstance(path, str) or path in seen_paths:
                        continue
                    seen_paths.add(path)
                    slots.append(slot)
        return slots

    def _collect_asset_backups(self, project_dir: Path, slots: list[dict[str, Any]]) -> dict[Path, bytes | None]:
        backups: dict[Path, bytes | None] = {}
        for slot in slots:
            path = slot.get("path")
            if not isinstance(path, str):
                continue
            target_path = project_dir / path
            backups[target_path] = target_path.read_bytes() if target_path.exists() else None
        return backups

    def _promote_staged_asset_slots(self, project_dir: Path, slots: list[dict[str, Any]]) -> None:
        import shutil

        for slot in slots:
            staging_path = slot.get("staging_path")
            path = slot.get("path")
            if not isinstance(staging_path, str) or not isinstance(path, str):
                continue
            src = project_dir / staging_path
            if not src.exists() or not src.is_file():
                continue
            dst = project_dir / path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    def _cleanup_round_staging_dir(self, project_dir: Path, round_id: str) -> None:
        staging_dir = project_dir / "game" / "__staging__" / round_id
        if not staging_dir.exists():
            return
        try:
            import shutil

            shutil.rmtree(staging_dir)
        except OSError:
            pass

    def _promote_script_staging(self, project_dir: Path, staging_paths: list[str]) -> list[str]:
        final_paths: list[str] = []
        for staging_path in staging_paths:
            if not staging_path:
                continue
            staging_file = project_dir / staging_path
            final_path = final_path_from_staging(staging_path)
            final_file = project_dir / final_path
            final_file.parent.mkdir(parents=True, exist_ok=True)
            if staging_file.exists():
                staging_file.replace(final_file)
            final_paths.append(final_path)
        return final_paths

    def _cleanup_stale_prototype_files(self, project_dir: Path, active_final_paths: list[str]) -> None:
        game_dir = project_dir / "game"
        if not game_dir.exists():
            return

        keep = {Path(path).name for path in active_final_paths}
        for proto_file in game_dir.glob("prototype_*.rpy"):
            if proto_file.name not in keep:
                try:
                    proto_file.unlink()
                except OSError:
                    pass
        for staging_file in game_dir.glob("prototype_*.__staging__.rpy"):
            try:
                staging_file.unlink()
            except OSError:
                pass

    def _cleanup_stale_prototype_index_entries(self, project_name: str, active_scene_ids: list[str]) -> None:
        index = self.pm.read_project_index(project_name)
        if not index or "scenes" not in index:
            return

        active_scene_set = set(active_scene_ids)
        changed = False
        scenes = index["scenes"]
        if not isinstance(scenes, dict):
            return

        for scene_id, scene_data in list(scenes.items()):
            if not isinstance(scene_data, dict):
                continue
            if scene_data.get("source") != "prototype":
                continue
            if scene_id not in active_scene_set:
                scenes.pop(scene_id, None)
                changed = True

        if changed:
            self.pm.write_project_index(project_name, index)

    def commit(self, project_name: str) -> dict[str, Any]:
        state = self.get_state(project_name)
        if state.get("state") != "script_preview":
            raise ValueError("Cannot commit before script preview is generated")

        script_preview = state.get("script_preview")
        if not isinstance(script_preview, dict) or not script_preview:
            raise ValueError("No preview script available")

        staging_paths = script_preview.get("staging_paths")
        if isinstance(staging_paths, list) and staging_paths:
            staging_paths = [str(path) for path in staging_paths if isinstance(path, str)]
        else:
            legacy_staging_path = script_preview.get("staging_path")
            if not isinstance(legacy_staging_path, str) or not legacy_staging_path:
                raise ValueError("No preview script available")
            staging_paths = [legacy_staging_path]

        script_files = script_preview.get("script_files")
        if not isinstance(script_files, list) or not script_files:
            script_files = [final_path_from_staging(path) for path in staging_paths]
        elif len(script_files) != len(staging_paths):
            raise ValueError("Preview state does not match generated scripts")

        entry_label = script_preview.get("entry_label")
        scene_ids = script_preview.get("scene_ids")
        if not isinstance(scene_ids, list):
            raise ValueError("Invalid preview metadata")
        if not entry_label or not isinstance(entry_label, str):
            raise ValueError("Invalid preview metadata")

        self._ensure_required_slots_accepted(project_name, state, "character_assets")
        self._ensure_required_slots_accepted(project_name, state, "background_assets")

        preview_plans = self._build_preview_plan(project_name, state)
        if len(preview_plans) != len(staging_paths):
            raise ValueError("Preview state does not match generated scripts")

        project_dir = self.pm._project_dir(project_name)
        round_id = state.get("round_id")
        if not isinstance(round_id, str) or not round_id:
            raise ValueError("Missing round_id")

        for idx, plan in enumerate(preview_plans):
            plan["final_script_path"] = script_files[idx]

        old_script = self._prototype_activation.backup_main_script(project_name)
        old_manifest_text = (
            (project_dir / "meta" / "prototype_manifest.json").read_text(encoding="utf-8")
            if (project_dir / "meta" / "prototype_manifest.json").exists()
            else None
        )
        old_index_text = (
            (project_dir / "meta" / "index.json").read_text(encoding="utf-8")
            if (project_dir / "meta" / "index.json").exists()
            else None
        )

        preview_asset_slots = self._collect_preview_asset_slots(preview_plans)
        asset_backups = self._collect_asset_backups(project_dir, preview_asset_slots)

        script_backups = self._collect_file_backups(project_dir, script_files)
        prototype_file_backups: dict[Path, bytes] = self._collect_existing_prototype_file_backups(project_dir)

        try:
            self._prototype_activation.wire_main_script_to_prototype(project_name, entry_label)

            for plan in preview_plans:
                self._prototype_activation.update_index(
                    project_name=project_name,
                    chapter=plan["chapter"],
                    scenes=plan["scenes"],
                    script_path=cast(str, plan["final_script_path"]),
                    background_assets=plan["background_assets"],
                    character_assets=plan["character_assets"],
                )

            if len(preview_plans) == 1:
                self._promote_staged_asset_slots(project_dir, preview_asset_slots)
                self._prototype_activation.commit_prototype_replacement(
                    project_name=project_name,
                    new_scene_ids=cast(list[str], preview_plans[0].get("scene_ids", [])),
                    staging_script_path=staging_paths[0],
                    round_id=None,
                )
            else:
                self._promote_script_staging(project_dir, staging_paths)
                self._promote_staged_asset_slots(project_dir, preview_asset_slots)
                self._cleanup_stale_prototype_files(project_dir, script_files)
                self._cleanup_stale_prototype_index_entries(
                    project_name,
                    [scene.scene_id for plan in preview_plans for scene in plan["scenes"]],
                )

            manifest = PrototypeManifest(
                mode="multi_chapter" if len(preview_plans) > 1 else "single_chapter",
                entry_label=entry_label,
                entry_file=script_files[0],
                chapter_ids=[plan["chapter"].id for plan in preview_plans],
                script_files=script_files,
                source="prototype",
                updated_at=datetime.utcnow().isoformat(),
            )
            self.pm.write_prototype_manifest(project_name, manifest)
            state["state"] = "committed"
            state["script_preview"] = {
                "staging_paths": staging_paths,
                "staging_path": staging_paths[0],
                "script_files": script_files,
                "entry_label": entry_label,
                "scene_ids": scene_ids,
                "chapter_ids": [plan["chapter"].id for plan in preview_plans],
                "committed_at": datetime.utcnow().isoformat(),
            }
            self.save_state(project_name, state)
            self._cleanup_round_staging_dir(project_dir, round_id)
            return state
        except Exception:
            for target_path, old in asset_backups.items():
                if old is None:
                    if target_path.exists():
                        target_path.unlink()
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_bytes(old)

            self._restore_file_backups(script_backups)
            self._restore_prototype_file_backups(prototype_file_backups)
            self._restore_manifest(project_name, old_manifest_text)
            self._restore_index(project_name, old_index_text)
            self._prototype_activation.restore_main_script(project_name, old_script)

            state["state"] = "failed"
            state["script_preview"] = {
                "staging_paths": staging_paths,
                "staging_path": staging_paths[0],
                "script_files": script_files,
                "entry_label": entry_label,
                "scene_ids": scene_ids,
                "chapter_ids": [plan["chapter"].id for plan in preview_plans],
            }
            self.save_state(project_name, state)
            raise
