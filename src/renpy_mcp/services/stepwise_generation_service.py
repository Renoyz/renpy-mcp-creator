"""Service layer for Tier 4 stepwise generation orchestration."""

from __future__ import annotations

import json
import logging
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from PIL import Image

from renpy_mcp.services.imported_asset_service import ImportedAssetService
from renpy_mcp.services.prototype_activation_service import PrototypeActivationService
from renpy_mcp.services.script_render_service import ScriptRenderService, final_path_from_staging
from renpy_mcp.models import ImageGenerationResult

from renpy_mcp.blueprint.models import ChapterSummary, PrototypeManifest
from renpy_mcp.services.prototype_generation_service import PrototypeScene

if TYPE_CHECKING:
    from renpy_mcp.services.project_manager import ProjectManager


logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        pm: "ProjectManager",
        imported_asset_service: ImportedAssetService | None = None,
        image_service: Any | None = None,
    ) -> None:
        if pm is None:
            raise ValueError("ProjectManager is required")
        self.pm = pm
        self.imported_asset_service = imported_asset_service or ImportedAssetService(pm)
        self._script_renderer = ScriptRenderService(pm)
        self._prototype_activation = PrototypeActivationService(pm)
        if image_service is None:
            from renpy_mcp.ai.image_service import ImageService

            image_service = ImageService(pm.settings)
        self.image_service = image_service

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
        value = str(value)
        normalized = ImportedAssetService._normalize_component(value, "asset")
        if normalized != "asset" or value.strip().casefold() == "asset":
            return normalized
        digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
        return f"u_{digest}"

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
            required_targets = {
                self._normalize_target(str(req.get("target", "")))
                for req in self._collect_character_requirements(project_name)
                if req.get("target")
            }
            if not required_targets:
                return list(state[collection].keys())
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
        for requirement in self._collect_character_requirements(project_name):
            character_target = self._coerce_prompt_text(requirement.get("target"))
            safe_character = self._normalize_target(character_target)
            if not character_target or not safe_character:
                continue
            char_asset_id = self._slot_asset_id("character_sprite", safe_character, "normal")
            existing = state["character_assets"].get(char_asset_id)
            if existing is None:
                legacy_slot_id = self._find_existing_character_design_slot_id(
                    state,
                    requirement=requirement,
                    variant="normal",
                    exclude_asset_id=char_asset_id,
                )
                if legacy_slot_id:
                    existing = state["character_assets"].pop(legacy_slot_id)
                    existing["asset_id"] = char_asset_id
                    existing["target"] = character_target
                    existing["variant"] = "normal"
                    state["character_assets"][char_asset_id] = existing
            if existing is None:
                slot = self._build_empty_slot(
                    kind="character_sprite",
                    target=character_target,
                    variant="normal",
                )
                state["character_assets"][char_asset_id] = self._apply_character_metadata(slot, requirement)
                continue
            state["character_assets"][char_asset_id] = self._apply_character_metadata(existing, requirement)

    def _find_existing_character_design_slot_id(
        self,
        state: dict[str, Any],
        *,
        requirement: dict[str, str],
        variant: str,
        exclude_asset_id: str,
    ) -> str | None:
        display_name = self._coerce_prompt_text(requirement.get("display_name"))
        target = self._coerce_prompt_text(requirement.get("target"))
        match_keys = {
            self._normalized_slot_match_key(value)
            for value in (display_name, target)
            if value
        }
        if not match_keys:
            return None
        variant_key = self._normalized_variant_match_key(variant)
        for slot_id, slot in state["character_assets"].items():
            if slot_id == exclude_asset_id or slot.get("kind") != "character_sprite":
                continue
            if self._normalized_variant_match_key(str(slot.get("variant", ""))) != variant_key:
                continue
            slot_keys = {
                self._normalized_slot_match_key(value)
                for value in (
                    self._coerce_prompt_text(slot.get("display_name")),
                    self._coerce_prompt_text(slot.get("target")),
                )
                if value
            }
            if match_keys & slot_keys:
                return slot_id
        return None

    def _collect_character_requirements(self, project_name: str) -> list[dict[str, str]]:
        """Collect character asset slots from finalized design artifacts."""
        blueprint_requirements = self._blueprint_character_requirements(project_name)
        brief_requirements = self._brief_character_requirements(project_name)
        design_lookup = {
            self._normalized_slot_match_key(item["target"]): item
            for item in [*brief_requirements, *blueprint_requirements]
            if item.get("target")
        }
        for item in [*brief_requirements, *blueprint_requirements]:
            display_name = item.get("display_name", "")
            if display_name:
                design_lookup.setdefault(self._normalized_slot_match_key(display_name), item)

        scene_requirements = self._scene_package_character_requirements(project_name, design_lookup)
        if scene_requirements:
            return scene_requirements
        if blueprint_requirements:
            return blueprint_requirements
        return brief_requirements

    def _scene_package_character_requirements(
        self,
        project_name: str,
        design_lookup: dict[str, dict[str, str]],
    ) -> list[dict[str, str]]:
        scene_packages = self.pm.read_scene_packages(project_name)
        if scene_packages is None:
            return []

        requirements: dict[str, dict[str, str]] = {}

        def add_character(target: str, display_name: str = "") -> None:
            safe_target = self._normalize_target(target)
            if not safe_target:
                return
            design = design_lookup.get(self._normalized_slot_match_key(safe_target))
            if design is None and display_name:
                design = design_lookup.get(self._normalized_slot_match_key(display_name))
            item = dict(design or {})
            item["target"] = target
            item["display_name"] = item.get("display_name") or display_name or target
            item["character_source"] = "scene_package"
            requirements.setdefault(self._normalized_slot_match_key(safe_target), item)

        for chapter in scene_packages.chapters:
            for scene in chapter.scenes:
                for plan_item in scene.sprite_plan:
                    add_character(
                        plan_item.character_id or plan_item.character_name,
                        plan_item.character_name,
                    )
                for character in scene.characters_present:
                    add_character(character, character)
        return list(requirements.values())

    def _blueprint_character_requirements(self, project_name: str) -> list[dict[str, str]]:
        try:
            blueprint = self.pm.read_blueprint(project_name)
        except ValueError:
            return []
        if blueprint is None:
            return []
        requirements: list[dict[str, str]] = []
        for character in blueprint.characters:
            target = self._coerce_prompt_text(character.name)
            if not target:
                continue
            requirements.append(
                {
                    "target": target,
                    "display_name": character.name,
                    "role": character.role,
                    "appearance": character.appearance,
                    "character_source": "blueprint",
                    "prompt": self._character_prompt_from_parts(
                        display_name=character.name,
                        role=character.role,
                        appearance=character.appearance,
                        personality=character.personality,
                    ),
                }
            )
        return requirements

    def _brief_character_requirements(self, project_name: str) -> list[dict[str, str]]:
        try:
            brief = self.pm.read_project_brief(project_name)
        except ValueError:
            return []
        if brief is None:
            return []
        card = brief.cards.get("character_identity")
        if card is None or not isinstance(card.content, dict):
            return []
        characters = card.content.get("characters")
        if not isinstance(characters, list):
            return []
        requirements: list[dict[str, str]] = []
        for raw in characters:
            if not isinstance(raw, dict):
                continue
            target = self._coerce_prompt_text(raw.get("character_id")) or self._coerce_prompt_text(raw.get("name"))
            safe_target = self._normalize_target(target)
            if not safe_target:
                continue
            visual_anchors = raw.get("visual_identity_anchors")
            if not isinstance(visual_anchors, list):
                visual_anchors = []
            personality_anchors = raw.get("personality_anchors")
            if not isinstance(personality_anchors, list):
                personality_anchors = []
            appearance = ", ".join(str(anchor).strip() for anchor in visual_anchors if str(anchor).strip())
            personality = ", ".join(str(anchor).strip() for anchor in personality_anchors if str(anchor).strip())
            display_name = self._coerce_prompt_text(raw.get("name")) or safe_target
            role = self._coerce_prompt_text(raw.get("story_role"))
            motivation = self._coerce_prompt_text(raw.get("core_motivation"))
            requirements.append(
                {
                    "target": safe_target,
                    "display_name": display_name,
                    "role": role,
                    "appearance": appearance,
                    "character_source": "brief",
                    "prompt": self._character_prompt_from_parts(
                        display_name=display_name,
                        role=role,
                        appearance=appearance,
                        personality=personality,
                        motivation=motivation,
                    ),
                }
            )
        return requirements

    def _apply_character_metadata(self, slot: dict[str, Any], metadata: dict[str, str]) -> dict[str, Any]:
        for key in ("display_name", "role", "appearance", "character_source", "prompt"):
            value = self._coerce_prompt_text(metadata.get(key))
            if value:
                slot[key] = value
        return slot

    @staticmethod
    def _character_prompt_from_parts(
        *,
        display_name: str,
        role: str = "",
        appearance: str = "",
        personality: str = "",
        motivation: str = "",
    ) -> str:
        parts = [
            f"Generate a visual novel character sprite for {display_name}.",
            "One character only, full body, transparent background.",
        ]
        if role:
            parts.append(f"Role: {role}.")
        if appearance:
            parts.append(f"Appearance: {appearance}.")
        if personality:
            parts.append(f"Personality: {personality}.")
        if motivation:
            parts.append(f"Motivation: {motivation}.")
        return " ".join(parts)

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
                existing = state["background_assets"].get(bg_asset_id)
                if existing is None:
                    slot = self._build_empty_slot(
                        kind="background",
                        target=safe_scene_id,
                        variant="main",
                    )
                    state["background_assets"][bg_asset_id] = self._apply_background_metadata(
                        project_name=project_name,
                        slot=slot,
                        target=safe_scene_id,
                        existing_slot=None,
                    )
                    continue

                self._apply_background_metadata(
                    project_name=project_name,
                    slot=existing,
                    target=safe_scene_id,
                    existing_slot=existing,
                )
                state["background_assets"][bg_asset_id] = existing

    def _background_description_from_scene_package(
        self,
        project_name: str,
        target: str,
    ) -> tuple[str, str] | None:
        scene_packages = self.pm.read_scene_packages(project_name)
        if scene_packages is None:
            return None

        target_key = self._normalized_slot_match_key(target)
        for chapter in scene_packages.chapters:
            for scene in chapter.scenes:
                if self._normalized_slot_match_key(scene.scene_id) != target_key:
                    continue
                description = self._background_description_from_scene(scene)
                if description:
                    return description, "scene_package"
        return None

    def _background_description_for_target(
        self,
        project_name: str,
        target: str,
        existing_slot: dict[str, Any] | None = None,
        override_description: str | None = None,
    ) -> tuple[str, str]:
        if isinstance(override_description, str) and override_description.strip():
            return self._coerce_prompt_text(override_description), "user"

        existing_description = None
        existing_source = None
        if isinstance(existing_slot, dict):
            existing_description = existing_slot.get("description")
            existing_source = existing_slot.get("description_source")
        if (
            isinstance(existing_description, str)
            and existing_description.strip()
            and self._coerce_prompt_text(existing_source) != "target"
        ):
            return self._coerce_prompt_text(existing_description), self._coerce_prompt_text(existing_source) or "user"

        scene_description = self._background_description_from_scene_package(
            project_name=project_name,
            target=target,
        )
        if scene_description is not None:
            return scene_description

        if isinstance(existing_description, str) and existing_description.strip():
            return self._coerce_prompt_text(existing_description), self._coerce_prompt_text(existing_source) or "target"

        normalized_target = self._coerce_prompt_text(target)
        if not normalized_target:
            normalized_target = self._coerce_prompt_text(self._slot_target(existing_slot or {}))
        return normalized_target or "", "target"

    def _apply_background_metadata(
        self,
        *,
        project_name: str,
        slot: dict[str, Any],
        target: str,
        existing_slot: dict[str, Any] | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        description, description_source = self._background_description_for_target(
            project_name=project_name,
            target=target,
            existing_slot=existing_slot,
            override_description=description,
        )
        slot["description"] = self._coerce_prompt_text(description)
        slot["description_source"] = self._coerce_prompt_text(description_source) or "target"
        return slot

    def ensure_required_slots(self, project_name: str, state: dict[str, Any]) -> None:
        """Create required slots from scene packages when available."""
        self._ensure_required_character_slots(project_name, state)
        self._ensure_required_background_slots(project_name, state)

    def prepare_asset_slots(self, project_name: str) -> dict[str, Any]:
        """Materialize required asset review slots without starting generation jobs.

        The generation dashboard should show the derived character/background lists as
        soon as the frozen blueprint is ready. This method creates empty review slots
        and moves the stepwise workflow to the first manual asset stage, but it does
        not call image generation or import any user-visible files.
        """
        state = self.get_state(project_name)
        if state["state"] in {"script_preview", "committed"}:
            return state
        self._require_state(
            state,
            "idle",
            "scene_outline_draft",
            "scene_outline_confirmed",
            "character_assets_draft",
            "character_assets_confirmed",
            "background_assets_draft",
            "background_assets_confirmed",
            action="prepare asset slots",
        )
        before = json.dumps(self._safe_state(state), ensure_ascii=False, sort_keys=True)

        self.ensure_required_slots(project_name, state)
        has_required_slots = bool(state["character_assets"] or state["background_assets"])
        if has_required_slots and state.get("round_id") is None:
            state["round_id"] = self._round_for_project(project_name, state)
        if has_required_slots and state["state"] in {"idle", "scene_outline_draft", "scene_outline_confirmed"}:
            state["state"] = "character_assets_draft"

        after = json.dumps(self._safe_state(state), ensure_ascii=False, sort_keys=True)
        if after != before:
            self.save_state(project_name, state)
        return state

    @staticmethod
    def _background_description_from_scene(scene: Any) -> str:
        location_visual_brief = getattr(scene, "location_visual_brief", "")
        if isinstance(location_visual_brief, str):
            location_visual_brief = location_visual_brief.strip()
            if location_visual_brief:
                return location_visual_brief

        summary = getattr(scene, "summary", "")
        if not isinstance(summary, str):
            summary = ""
        location = getattr(scene, "location", "")
        if not isinstance(location, str):
            location = ""
        mood = getattr(scene, "mood", "")
        if not isinstance(mood, str):
            mood = ""

        return ", ".join(part.strip() for part in (summary, location, mood) if part and part.strip())

    def _build_empty_slot(
        self,
        *,
        kind: str,
        target: str,
        variant: str,
        description: str | None = None,
        description_source: str | None = None,
    ) -> dict[str, Any]:
        slot = {
            "asset_id": self._slot_asset_id(kind, self._normalize_target(target), variant),
            "kind": kind,
            "target": target,
            "variant": variant,
            "source": None,
            "status": "empty",
            "placeholder": False,
            "renderable": False,
        }
        if kind == "background":
            source = self._coerce_prompt_text(description_source) or "target"
            resolved_target = self._normalize_target(target)
            resolved_description = self._coerce_prompt_text(description)
            if not resolved_description:
                resolved_description = resolved_target
            slot["description"] = resolved_description
            slot["description_source"] = source
        return slot

    @staticmethod
    def _default_character_prompt(target: str, variant: str) -> str:
        return (
            f"Generate a visual novel character sprite for {target} in variant {variant}. "
            "Style should match the project and be one character only, full body, transparent background."
        )

    @staticmethod
    def _default_background_prompt(target: str, variant: str, description: str = "") -> str:
        context = f" Scene description: {description}." if description else ""
        return (
            f"Generate a visual novel background plate for {target}, variant {variant}. "
            "Use 16:9 composition, no characters or text."
            f"{context}"
        )

    def _default_generation_prompt(
        self,
        *,
        kind: str,
        target: str,
        variant: str,
        prompt: str,
        description: str = "",
    ) -> str:
        prompt = self._coerce_prompt_text(prompt)
        if prompt:
            return prompt
        if kind == "character_sprite":
            return self._default_character_prompt(target, variant)
        if kind == "background":
            return self._default_background_prompt(target, variant, description)
        raise ValueError(f"Unsupported asset kind: {kind!r}")

    @staticmethod
    def _coerce_prompt_text(prompt: str | None) -> str:
        return prompt.strip() if isinstance(prompt, str) else ""

    def _cleanup_generated_intermediates(self, project_dir: Path, files: list[Path]) -> None:
        image_root = (project_dir / "game" / "images").resolve()
        for file_path in files:
            try:
                resolved = file_path.resolve()
                if resolved.exists() and resolved.is_file() and resolved.is_relative_to(image_root):
                    resolved.unlink()
            except Exception:
                logger.warning("Failed to clean generated intermediate image %s", file_path, exc_info=True)

    def _mock_generate_image_file(
        self,
        *,
        project_dir: Path,
        image_type: str,
        base_name: str,
        prompt: str,
    ) -> ImageGenerationResult:
        output_dir = project_dir / "game" / "images" / image_type
        output_dir.mkdir(parents=True, exist_ok=True)
        primary = output_dir / f"{base_name}.png"
        if image_type == "background":
            image = Image.new("RGBA", (1280, 720), color=(28, 40, 64, 255))
        else:
            image = Image.new("RGBA", (640, 720), color=(80, 48, 96, 255))
        image.save(primary, format="PNG")
        return ImageGenerationResult(
            success=True,
            prompt=prompt,
            image_type=image_type,
            files=[primary],
            primary_file=primary,
        )

    def _build_generated_slot(
        self,
        *,
        project_name: str,
        round_id: str,
        kind: str,
        target: str,
        variant: str,
        generation_prompt: str,
        generated_file: Path,
        description: str | None = None,
        description_source: str | None = None,
    ) -> dict[str, Any]:
        width, height, has_alpha = self.imported_asset_service._decode(generated_file.read_bytes())
        normalized_kind = self.imported_asset_service._normalize_kind(kind)
        safe_target = self._normalize_target(target)
        safe_variant = self._normalize_target(variant)
        safe_extension = generated_file.suffix.lower() or ".png"
        if safe_extension not in ImportedAssetService._ALLOWED_EXTENSIONS:
            safe_extension = ".png"

        validation = self.imported_asset_service._build_validation(
            width,
            height,
            normalized_kind,
            has_alpha,
        )
        renderable = (
            normalized_kind == "background"
            or (validation["ok"] and validation["reason"] == "ok")
        )
        asset_id = self._slot_asset_id(normalized_kind, safe_target, safe_variant)
        staging_path = self.imported_asset_service._staging_relpath(
            round_id=self.imported_asset_service._safe_round_id(round_id),
            kind=normalized_kind,
            asset_id=asset_id,
            extension=safe_extension,
        )
        final_path = self.imported_asset_service._final_relpath(
            kind=normalized_kind,
            asset_id=asset_id,
            extension=safe_extension,
        )
        slot = {
            "asset_id": asset_id,
            "kind": normalized_kind,
            "target": safe_target,
            "variant": safe_variant,
            "source": "generated",
            "status": "generated",
            "path": final_path,
            "staging_path": staging_path,
            "preview_url": self.imported_asset_service._build_preview_url(
                project_name=project_name,
                staging_path=staging_path,
            ),
            "placeholder": False,
            "renderable": renderable,
            "validation": validation,
            "generation_prompt": generation_prompt,
        }
        if normalized_kind == "background":
            resolved_description = self._coerce_prompt_text(description)
            resolved_source = self._coerce_prompt_text(description_source) or "target"
            if not resolved_description and resolved_source == "target":
                resolved_description = safe_target
            slot["description"] = resolved_description
            slot["description_source"] = resolved_source
        return slot

    async def _generate_and_stage_image(
        self,
        project_name: str,
        project_dir: Path,
        kind: str,
        target: str,
        variant: str,
        prompt: str,
        round_id: str,
        description: str = "",
        description_source: str | None = None,
    ) -> tuple[dict[str, Any], Path]:
        generation_prompt = self._default_generation_prompt(
            kind=kind,
            target=target,
            variant=variant,
            prompt=prompt,
            description=description,
        )
        service_prompt = generation_prompt
        prompt_text = self._coerce_prompt_text(prompt)
        description_text = self._coerce_prompt_text(description)
        if kind == "background" and prompt_text and description_text:
            service_prompt = f"{prompt_text}\nScene description: {description_text}."
        normalized_target = self._normalize_target(target)
        normalized_variant = self._normalize_target(variant)
        image_type = "background" if kind == "background" else "character"
        base_name = f"{normalized_target}_{normalized_variant}"

        if os.environ.get("RENPY_MCP_MOCK_IMAGE_GEN"):
            result = self._mock_generate_image_file(
                project_dir=project_dir,
                prompt=service_prompt,
                image_type=image_type,
                base_name=base_name,
            )
        else:
            if not self.image_service.is_available():
                raise RuntimeError("Image generation service is not available")
            result = await self.image_service.generate_image(
                project_dir=project_dir,
                prompt=service_prompt,
                image_type=image_type,
                base_name=base_name,
            )
        if not isinstance(result, ImageGenerationResult):
            raise RuntimeError("Image service returned an unexpected result type")
        if not result.success:
            raise RuntimeError(f"Image generation failed: {result.error or 'unknown error'}")
        if result.primary_file is None:
            raise RuntimeError("Image generation did not return a primary file")

        generated_file = Path(result.primary_file)
        if not generated_file.exists():
            raise RuntimeError("Generated image file is missing")

        slot = self._build_generated_slot(
            project_name=project_name,
            round_id=round_id,
            kind=kind,
            target=normalized_target,
            variant=normalized_variant,
            generation_prompt=generation_prompt,
            generated_file=generated_file,
            description=description,
            description_source=description_source,
        )
        destination = project_dir / cast(str, slot["staging_path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(generated_file.read_bytes())
        cleanup_files = [Path(path) for path in result.files]
        if generated_file not in cleanup_files:
            cleanup_files.append(generated_file)
        self._cleanup_generated_intermediates(project_dir, cleanup_files)
        return slot, destination

    def _persist_generated_slot(
        self,
        state: dict[str, Any],
        collection: Literal["character_assets", "background_assets"],
        slot_id: str,
        new_slot: dict[str, Any],
        replace: bool,
    ) -> dict[str, Any]:
        existing_slot = state[collection].get(slot_id)
        if existing_slot is not None and existing_slot.get("status") == "accepted" and not replace:
            raise ValueError(f"Asset {slot_id} is already accepted")

        existing_slot = state[collection].get(slot_id)
        if existing_slot is not None:
            new_slot["asset_id"] = existing_slot.get("asset_id", slot_id)
            new_slot["target"] = existing_slot.get("target", new_slot["target"])
            new_slot["kind"] = existing_slot.get("kind", new_slot["kind"])
            new_slot["variant"] = existing_slot.get("variant", new_slot["variant"])
            new_slot["placeholder"] = False

        state[collection][slot_id] = new_slot
        return new_slot

    def _ensure_round_id(self, state: dict[str, Any], project_name: str) -> str:
        if state.get("round_id") is None or not isinstance(state["round_id"], str):
            state["round_id"] = self._round_for_project(project_name, state)
        return cast(str, state["round_id"])

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
            slot["description"] = existing.get("description", slot.get("description"))
            slot["description_source"] = existing.get("description_source", slot.get("description_source"))
            for key in ("display_name", "role", "appearance", "character_source", "prompt"):
                if key in existing:
                    slot[key] = existing[key]

        state["character_assets"][target_slot_id] = slot
        if original_slot_id != target_slot_id:
            state["character_assets"].pop(original_slot_id, None)

        self._ensure_required_character_slots(project_name, state)
        state["round_id"] = round_id
        if state["state"] == "character_assets_confirmed":
            state["state"] = "character_assets_draft"
        self.save_state(project_name, state)
        return slot

    async def generate_character_asset(
        self,
        *,
        project_name: str,
        character_id: str,
        variant: str,
        prompt: str,
        replace: bool = False,
    ) -> dict[str, Any]:
        state = self.get_state(project_name)
        self._require_state(
            state,
            "character_assets_draft",
            "character_assets_confirmed",
            "background_assets_draft",
            "background_assets_confirmed",
            action="generate character asset",
        )
        round_id = self._ensure_round_id(state, project_name)

        collection = "character_assets"
        existing_slot_id = self._find_existing_slot_id(
            state,
            collection,
            "character_sprite",
            character_id,
            variant,
        )
        slot_id = existing_slot_id or self._slot_asset_id(
            kind="character_sprite",
            target=self._normalize_target(character_id),
            variant=self._normalize_target(variant),
        )
        existing_slot = state[collection].get(slot_id)
        if existing_slot is not None and existing_slot.get("status") == "accepted" and not replace:
            raise ValueError(f"Asset {slot_id} is already accepted")
        description = ""
        description_source: str | None = None
        prompt_for_generation = self._coerce_prompt_text(prompt)
        if existing_slot is not None:
            description_value = existing_slot.get("description")
            if isinstance(description_value, str):
                description = description_value
            source_value = existing_slot.get("description_source")
            if isinstance(source_value, str):
                description_source = source_value
            if not prompt_for_generation:
                prompt_for_generation = self._coerce_prompt_text(existing_slot.get("prompt"))

        project_dir = self.pm._project_dir(project_name)
        slot, _ = await self._generate_and_stage_image(
            project_name=project_name,
            project_dir=project_dir,
            kind="character_sprite",
            target=character_id,
            variant=variant,
            prompt=prompt_for_generation,
            round_id=round_id,
            description=description,
            description_source=description_source,
        )
        if existing_slot is not None:
            for key in ("display_name", "role", "appearance", "character_source", "prompt"):
                if key in existing_slot:
                    slot[key] = existing_slot[key]
        _ = self._persist_generated_slot(
            state=state,
            collection=collection,
            slot_id=slot_id,
            new_slot=slot,
            replace=replace,
        )

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
        description: str | None = None,
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
        slot = self._apply_background_metadata(
            project_name=project_name,
            slot=slot,
            target=location_id,
            existing_slot=existing,
            description=description,
        )

        state["background_assets"][target_slot_id] = slot
        if original_slot_id != target_slot_id:
            state["background_assets"].pop(original_slot_id, None)

        self._ensure_required_background_slots(project_name, state)
        state["round_id"] = round_id
        if state["state"] == "background_assets_confirmed":
            state["state"] = "background_assets_draft"
        self.save_state(project_name, state)
        return slot

    async def generate_background_asset(
        self,
        *,
        project_name: str,
        location_id: str,
        variant: str,
        prompt: str,
        replace: bool = False,
        description: str | None = None,
    ) -> dict[str, Any]:
        state = self.get_state(project_name)
        self._require_state(
            state,
            "background_assets_draft",
            "background_assets_confirmed",
            "character_assets_confirmed",
            action="generate background asset",
        )
        round_id = self._ensure_round_id(state, project_name)

        collection = "background_assets"
        existing_slot_id = self._find_existing_slot_id(
            state,
            collection,
            "background",
            location_id,
            variant,
        )
        slot_id = existing_slot_id or self._slot_asset_id(
            kind="background",
            target=self._normalize_target(location_id),
            variant=self._normalize_target(variant),
        )
        existing_slot = state[collection].get(slot_id)
        if existing_slot is not None and existing_slot.get("status") == "accepted" and not replace:
            raise ValueError(f"Asset {slot_id} is already accepted")

        description, description_source = self._background_description_for_target(
            project_name=project_name,
            target=location_id,
            existing_slot=existing_slot,
            override_description=description,
        )
        project_dir = self.pm._project_dir(project_name)
        slot, _ = await self._generate_and_stage_image(
            project_name=project_name,
            project_dir=project_dir,
            kind="background",
            target=location_id,
            variant=variant,
            prompt=self._coerce_prompt_text(prompt),
            round_id=round_id,
            description=description,
            description_source=description_source,
        )
        _ = self._persist_generated_slot(
            state=state,
            collection=collection,
            slot_id=slot_id,
            new_slot=slot,
            replace=replace,
        )

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
