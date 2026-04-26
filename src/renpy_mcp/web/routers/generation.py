"""Generation routes — scene packages, multi-chapter, scenes, storymap, prototype."""

import json
import logging
from collections import defaultdict
from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException
from fastapi import Body, UploadFile, File

from ...blueprint.models import (
    BlueprintFreezeStatus,
    FlowEdge,
    FlowNode,
    RefinementState,
    SceneScript,
)
from ...config import get_settings, resolve_project_dir
from ...services.project_manager import ProjectManager
from ...services.prototype_generation_service import PrototypeGenerationService
from ...services.stepwise_generation_service import StepwiseGenerationService
from ...services.refinement_logic import (
    compute_blueprint_freeze_status,
    compute_refinement_state,
    is_brief_fully_confirmed,
    is_outline_fully_confirmed,
)
from ..chat_ws import _get_provider
from ..fastapi_app import _read_build_status, _sanitize_sprite_plan_for_api

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_generation_gate(pm: ProjectManager, project_name: str) -> None:
    """Raise HTTPException(403) if downstream generation is not allowed."""
    try:
        brief = pm.read_project_brief(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        outline = pm.read_chapter_outline(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if brief is None and outline is None:
        try:
            blueprint = pm.read_blueprint(project_name)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        if blueprint is not None:
            return
        raise HTTPException(
            status_code=403,
            detail="Project has no blueprint. Complete requirements refinement or create a blueprint first.",
        )

    try:
        meta = pm.read_project_meta(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    target_state = compute_refinement_state(brief, outline)
    freeze_status = compute_blueprint_freeze_status(meta, brief, outline)
    if target_state != RefinementState.BLUEPRINT_READY:
        raise HTTPException(
            status_code=403,
            detail=f"Generation blocked: refinement state is '{target_state.value if target_state else 'none'}'. Reach 'blueprint_ready' before generating scenes or prototypes.",
        )
    if freeze_status != BlueprintFreezeStatus.FROZEN:
        raise HTTPException(
            status_code=403,
            detail=f"Generation blocked: blueprint freeze status is '{freeze_status.value if freeze_status else 'none'}'. Freeze the blueprint before generating scenes or prototypes.",
        )


def _has_prototype(project_name: str) -> bool:
    """Check whether the project has generated prototype artifacts on disk."""
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        return False
    settings = get_settings()
    pm = ProjectManager(settings)
    index = pm.read_project_index(project_name)
    proto_scenes = []
    if index and isinstance(index.get("scenes"), dict):
        proto_scenes = [
            s for s in index["scenes"].values()
            if isinstance(s, dict) and s.get("source") == "prototype"
        ]
    if not proto_scenes:
        return False
    script_paths = {s.get("file_path") for s in proto_scenes if s.get("file_path")}
    script_exists = all(
        (project_dir / p).exists() for p in script_paths
    ) if script_paths else False
    main_script = project_dir / "game" / "script.rpy"
    wired = main_script.exists() and "# PROTOTYPE START (managed)" in main_script.read_text(encoding="utf-8")
    return script_exists and wired


def _make_stepwise_service(project_name: str) -> StepwiseGenerationService:
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    settings = get_settings()
    return StepwiseGenerationService(ProjectManager(settings))


def _is_upload_client_error(exc: Exception) -> bool:
    detail = str(exc).lower()
    return any(
        token in detail
        for token in (
            "unsupported file extension",
            "valid image",
            "invalid image",
            "uploaded image is empty",
            "uploaded image exceeds",
            "uploaded data must be bytes",
            "invalid filename",
        )
    )


def _parse_accept_payload(payload: dict[str, object] | None) -> bool:
    if payload is None:
        return False
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON body for accept request")
    allow_non_renderable = payload.get("allow_non_renderable", False)
    if allow_non_renderable is None:
        return False
    if not isinstance(allow_non_renderable, bool):
        raise HTTPException(
            status_code=400,
            detail="allow_non_renderable must be a boolean",
        )
    return allow_non_renderable


async def _read_upload_bytes(file: UploadFile | None) -> bytes:
    if file is None:
        raise HTTPException(status_code=400, detail="Missing image file")
    return await file.read()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/api/projects/{project_name}/generation-state")
async def api_stepwise_generation_state(project_name: str):
    service = _make_stepwise_service(project_name)
    return service.get_state(project_name)


@router.post("/api/projects/{project_name}/generation/scene-outline/start")
async def api_stepwise_scene_outline_start(project_name: str):
    service = _make_stepwise_service(project_name)
    try:
        return service.start_scene_outline(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/api/projects/{project_name}/generation/scene-outline/confirm")
async def api_stepwise_scene_outline_confirm(project_name: str):
    service = _make_stepwise_service(project_name)
    try:
        return service.confirm_scene_outline(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/api/projects/{project_name}/generation/characters/start")
async def api_stepwise_characters_start(project_name: str):
    service = _make_stepwise_service(project_name)
    try:
        return service.start_characters(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/api/projects/{project_name}/generation/characters/{character_id}/{variant}/upload")
async def api_stepwise_character_upload(
    project_name: str,
    character_id: str,
    variant: str,
    file: UploadFile = File(...),
):
    service = _make_stepwise_service(project_name)
    try:
        file_bytes = await _read_upload_bytes(file)
        return service.upload_character_asset(
            project_name=project_name,
            character_id=character_id,
            variant=variant,
            filename=file.filename or f"{character_id}.{variant}",
            file_bytes=file_bytes,
        )
    except ValueError as exc:
        status = 400 if _is_upload_client_error(exc) else 409
        raise HTTPException(status_code=status, detail=str(exc))


@router.post("/api/projects/{project_name}/generation/characters/{character_id}/{variant}/generate")
async def api_stepwise_character_generate(
    project_name: str,
    character_id: str,
    variant: str,
):
    raise HTTPException(
        status_code=501,
        detail=f"Character asset generation for {character_id}/{variant} is not implemented in this task.",
    )


@router.post("/api/projects/{project_name}/generation/characters/{asset_id}/accept")
async def api_stepwise_character_accept(
    project_name: str,
    asset_id: str,
    payload: dict[str, object] | None = Body(default=None),
):
    service = _make_stepwise_service(project_name)
    allow_non_renderable = _parse_accept_payload(payload)
    try:
        return service.accept_asset(project_name, asset_id, allow_non_renderable=allow_non_renderable)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/api/projects/{project_name}/generation/characters/confirm")
async def api_stepwise_characters_confirm(project_name: str):
    service = _make_stepwise_service(project_name)
    try:
        return service.confirm_characters(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/api/projects/{project_name}/generation/backgrounds/start")
async def api_stepwise_backgrounds_start(project_name: str):
    service = _make_stepwise_service(project_name)
    try:
        return service.start_backgrounds(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/api/projects/{project_name}/generation/backgrounds/{location_id}/{variant}/upload")
async def api_stepwise_background_upload(
    project_name: str,
    location_id: str,
    variant: str,
    file: UploadFile = File(...),
):
    service = _make_stepwise_service(project_name)
    try:
        file_bytes = await _read_upload_bytes(file)
        return service.upload_background_asset(
            project_name=project_name,
            location_id=location_id,
            variant=variant,
            filename=file.filename or f"{location_id}.{variant}",
            file_bytes=file_bytes,
        )
    except ValueError as exc:
        status = 400 if _is_upload_client_error(exc) else 409
        raise HTTPException(status_code=status, detail=str(exc))


@router.post("/api/projects/{project_name}/generation/backgrounds/{location_id}/generate")
async def api_stepwise_background_generate(
    project_name: str,
    location_id: str,
):
    raise HTTPException(
        status_code=501,
        detail=f"Background asset generation for {location_id} is not implemented in this task.",
    )


@router.post("/api/projects/{project_name}/generation/backgrounds/{asset_id}/accept")
async def api_stepwise_background_accept(
    project_name: str,
    asset_id: str,
):
    service = _make_stepwise_service(project_name)
    try:
        return service.accept_asset(project_name, asset_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/api/projects/{project_name}/generation/backgrounds/confirm")
async def api_stepwise_backgrounds_confirm(project_name: str):
    service = _make_stepwise_service(project_name)
    try:
        return service.confirm_backgrounds(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/api/projects/{project_name}/generation/script/preview")
async def api_stepwise_script_preview(project_name: str):
    service = _make_stepwise_service(project_name)
    try:
        return service.preview_script(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/api/projects/{project_name}/generation/script/commit")
async def api_stepwise_script_commit(project_name: str):
    service = _make_stepwise_service(project_name)
    try:
        return service.commit(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/api/projects/{project_name}/scene-packages/generate")
async def api_generate_scene_packages(project_name: str):
    """Generate multi-chapter scene packages from the project blueprint."""
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    settings = get_settings()
    pm = ProjectManager(settings)
    _check_generation_gate(pm, project_name)

    try:
        blueprint = pm.read_blueprint(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if blueprint is None:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    provider = _get_provider()
    service = PrototypeGenerationService(pm=pm, provider=provider)

    try:
        packages = await service.generate_all_chapter_scenes(project_name, blueprint)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return {
        "success": True,
        "chapters": [
            {
                "chapter_id": ch_id,
                "scene_count": len(scenes),
            }
            for ch_id, scenes in packages.items()
        ],
    }


@router.post("/api/projects/{project_name}/prototype/multi-chapter/generate")
async def api_generate_multi_chapter_scripts(project_name: str):
    """Generate multi-chapter prototype scripts from scene_packages."""
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    settings = get_settings()
    pm = ProjectManager(settings)
    _check_generation_gate(pm, project_name)

    try:
        blueprint = pm.read_blueprint(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if blueprint is None:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    scene_packages = pm.read_scene_packages(project_name)
    if scene_packages is None:
        raise HTTPException(
            status_code=404,
            detail="Scene packages not found. Run /scene-packages/generate first.",
        )

    service = PrototypeGenerationService(pm=pm, provider=None)

    try:
        result = await service.generate_multi_chapter_scripts(project_name, blueprint)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return {"success": True, **result}


@router.get("/api/projects/{project_name}/scenes")
async def api_project_scenes(project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    settings = get_settings()
    pm = ProjectManager(settings)

    # Phase 6: Merge multi-chapter scene packages with richer prototype index
    try:
        scene_packages = pm.read_scene_packages(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if scene_packages is not None:
        chapters: list[dict] = []
        for ch in scene_packages.chapters:
            scenes = []
            for s in ch.scenes:
                scenes.append({
                    "id": s.scene_id,
                    "name": s.title,
                    "order": s.scene_order,
                    "characters": s.characters_present,
                    "backgrounds": [],
                    "music": None,
                    "choices": None,
                    "ending_name": None,
                    "status": "pending",
                    "type": "normal",
                    "is_ending": None,
                    "location": s.location,
                    "location_visual_brief": s.location_visual_brief,
                    "mood": s.mood,
                    "dialogue_beats": [beat.model_dump(mode="json") for beat in s.dialogue_beats],
                    "summary": s.summary,
                    "sprite_plan": _sanitize_sprite_plan_for_api(s.sprite_plan),
                })
            chapters.append({
                "id": ch.chapter_id,
                "name": ch.chapter_name or ch.chapter_id,
                "order": ch.chapter_order,
                "scenes": scenes,
            })

        chapter_names: dict[str, str] = {}
        chapter_orders: dict[str, int] = {}
        try:
            blueprint = pm.read_blueprint(project_name)
            if blueprint:
                for ch in blueprint.chapters:
                    chapter_names[ch.id] = ch.name
                    chapter_orders[ch.id] = ch.order
        except ValueError:
            pass

        index = pm.read_project_index(project_name)
        if index and isinstance(index.get("scenes"), dict):
            prototype_scenes = {
                sid: s for sid, s in index["scenes"].items()
                if isinstance(s, dict) and s.get("source") == "prototype"
            }
            scene_lookup: dict[str, dict] = {}
            chapter_lookup: dict[str, dict] = {}
            for ch in chapters:
                chapter_lookup[ch["id"]] = ch
                for s in ch["scenes"]:
                    scene_lookup[s["id"]] = s

            for sid, idx_scene in prototype_scenes.items():
                if sid in scene_lookup:
                    s = scene_lookup[sid]
                    if "order" in idx_scene:
                        s["order"] = idx_scene["order"]
                    if idx_scene.get("background_asset_path"):
                        s["backgrounds"] = [idx_scene["background_asset_path"]]
                    if idx_scene.get("background_placeholder") is not None:
                        s["background_placeholder"] = idx_scene["background_placeholder"]
                    if idx_scene.get("dialogue_beats"):
                        s["dialogue_beats"] = idx_scene["dialogue_beats"]
                    if idx_scene.get("sprite_plan"):
                        s["sprite_plan"] = _sanitize_sprite_plan_for_api(idx_scene["sprite_plan"])
                    if idx_scene.get("characters_present"):
                        s["characters"] = idx_scene["characters_present"]
                    for field in ("location", "location_visual_brief", "mood", "summary", "status"):
                        if idx_scene.get(field) is not None:
                            s[field] = idx_scene[field]
                else:
                    ch_id = idx_scene.get("chapter_id", "")
                    if ch_id not in chapter_lookup:
                        chapters.append({
                            "id": ch_id,
                            "name": chapter_names.get(ch_id, ch_id),
                            "order": chapter_orders.get(ch_id, 99),
                            "scenes": [],
                        })
                        chapter_lookup[ch_id] = chapters[-1]
                    chapter_lookup[ch_id]["scenes"].append({
                        "id": sid,
                        "name": idx_scene.get("title", sid),
                        "order": idx_scene.get("order", 0),
                        "characters": idx_scene.get("characters_present", []),
                        "backgrounds": [idx_scene["background_asset_path"]] if idx_scene.get("background_asset_path") else [],
                        "music": None,
                        "choices": None,
                        "ending_name": None,
                        "status": idx_scene.get("status", "generated"),
                        "type": "normal",
                        "is_ending": None,
                        "location": idx_scene.get("location"),
                        "location_visual_brief": idx_scene.get("location_visual_brief"),
                        "mood": idx_scene.get("mood"),
                        "dialogue_beats": idx_scene.get("dialogue_beats", []),
                        "summary": idx_scene.get("summary"),
                        "background_placeholder": idx_scene.get("background_placeholder"),
                        "sprite_plan": _sanitize_sprite_plan_for_api(idx_scene.get("sprite_plan")),
                    })

            for ch in chapters:
                ch["scenes"].sort(key=lambda s: s.get("order", 0))
            chapters.sort(key=lambda ch: ch.get("order", 0))

        return {"chapters": chapters}

    # Fallback: prefer prototype scenes from index when available
    index = pm.read_project_index(project_name)
    if index and isinstance(index.get("scenes"), dict):
        prototype_scenes = [
            s for s in index["scenes"].values()
            if isinstance(s, dict) and s.get("source") == "prototype"
        ]
        if prototype_scenes:
            chapter_names: dict[str, str] = {}
            try:
                blueprint = pm.read_blueprint(project_name)
                if blueprint:
                    for ch in blueprint.chapters:
                        chapter_names[ch.id] = ch.name
            except ValueError:
                pass

            chapters_map: dict[str, list[dict]] = defaultdict(list)
            for scene in sorted(prototype_scenes, key=lambda s: s.get("order", 0)):
                chapters_map[scene["chapter_id"]].append(scene)

            chapters = []
            for ch_id, scenes in chapters_map.items():
                chapters.append({
                    "id": ch_id,
                    "name": chapter_names.get(ch_id, scenes[0].get("title", ch_id)),
                    "order": 1,
                    "scenes": [
                        {
                            "id": s["scene_id"],
                            "name": s["title"],
                            "order": s.get("order", 0),
                            "characters": s.get("characters_present", []),
                            "backgrounds": [s["background_asset_path"]] if s.get("background_asset_path") else [],
                            "music": None,
                            "choices": None,
                            "ending_name": None,
                            "status": s.get("status", "generated"),
                            "type": "normal",
                            "is_ending": None,
                            "location": s.get("location"),
                            "location_visual_brief": s.get("location_visual_brief"),
                            "mood": s.get("mood"),
                            "dialogue_beats": s.get("dialogue_beats", []),
                            "summary": s.get("summary"),
                            "background_placeholder": s.get("background_placeholder"),
                            "sprite_plan": _sanitize_sprite_plan_for_api(s.get("sprite_plan")),
                        }
                        for s in scenes
                    ],
                })
            return {"chapters": chapters}

    # Fallback to blueprint
    try:
        blueprint = pm.read_blueprint(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if blueprint is None:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    return {"chapters": [ch.model_dump(mode="json") for ch in blueprint.chapters]}


@router.get("/api/projects/{project_name}/storymap")
async def api_project_storymap(project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    settings = get_settings()
    pm = ProjectManager(settings)

    index = pm.read_project_index(project_name)
    if index and isinstance(index.get("scenes"), dict):
        prototype_scenes = {
            sid: s for sid, s in index["scenes"].items()
            if isinstance(s, dict) and s.get("source") == "prototype"
        }
        if prototype_scenes:
            nodes: list[FlowNode] = []
            edges: list[FlowEdge] = []
            for sid, scene in prototype_scenes.items():
                nodes.append(
                    FlowNode(
                        id=sid,
                        chapter_id=scene["chapter_id"],
                        scene_id=sid,
                        type="normal",
                        label=scene.get("title", sid),
                    )
                )
                next_id = scene.get("next_scene_id")
                if next_id and next_id in prototype_scenes:
                    edges.append(
                        FlowEdge(
                            from_chapter_id=scene["chapter_id"],
                            from_scene_id=sid,
                            to_chapter_id=prototype_scenes[next_id]["chapter_id"],
                            to_scene_id=next_id,
                            type="main",
                        )
                    )
            return {
                "nodes": [n.model_dump(mode="json") for n in nodes],
                "edges": [e.model_dump(mode="json") for e in edges],
            }

    try:
        blueprint = pm.read_blueprint(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if blueprint is None:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    nodes: list[FlowNode] = []
    edges: list[FlowEdge] = []

    scene_to_chapter: dict[str, str] = {}
    for ch in blueprint.chapters:
        for scene in ch.scenes:
            scene_to_chapter[scene.id] = ch.id

    for ch in blueprint.chapters:
        prev_scene = None
        for scene in ch.scenes:
            nodes.append(
                FlowNode(
                    id=scene.id,
                    chapter_id=ch.id,
                    scene_id=scene.id,
                    type=scene.type or "normal",
                    label=scene.name,
                )
            )
            if prev_scene is not None:
                edges.append(
                    FlowEdge(
                        from_chapter_id=ch.id,
                        from_scene_id=prev_scene.id,
                        to_chapter_id=ch.id,
                        to_scene_id=scene.id,
                        type="main",
                    )
                )
            prev_scene = scene

    return {
        "nodes": [n.model_dump(mode="json") for n in nodes],
        "edges": [e.model_dump(mode="json") for e in edges],
    }


@router.get("/api/projects/{project_name}/scenes/{scene_id}/script")
async def api_project_scene_script(project_name: str, scene_id: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    index_path = project_dir / "meta" / "index.json"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Scene index not found")
    try:
        index_data = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Scene index is corrupt: {exc}")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot read scene index: {exc}")

    if not isinstance(index_data, dict):
        raise HTTPException(
            status_code=500,
            detail="Scene index has invalid structure: top-level value is not an object",
        )

    scenes_map = index_data.get("scenes")
    if not isinstance(scenes_map, dict):
        raise HTTPException(
            status_code=500, detail="Scene index has invalid structure: scenes is not an object"
        )

    if scene_id not in scenes_map:
        raise HTTPException(status_code=404, detail="Scene not found")
    mapping = scenes_map[scene_id]
    if not isinstance(mapping, dict):
        raise HTTPException(
            status_code=500,
            detail=f"Scene index has invalid structure: scene {scene_id} mapping is not an object",
        )

    required = ("chapter_id", "label", "file_path")
    missing = [k for k in required if not mapping.get(k)]
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Scene index has incomplete mapping for {scene_id}: missing {missing}",
        )

    raw_file_path = mapping["file_path"]
    if not isinstance(raw_file_path, str) or not raw_file_path:
        raise HTTPException(
            status_code=500,
            detail=f"Scene index has invalid file_path for {scene_id}: must be a non-empty string",
        )
    normalized = raw_file_path.replace("\\", "/")
    pp = PurePosixPath(normalized)
    if not pp.parts or pp.parts[0] != "game" or not str(pp).endswith(".rpy"):
        raise HTTPException(
            status_code=500,
            detail=f"Scene index has invalid file_path for {scene_id}: must be a .rpy file under game/",
        )

    rpy_path = project_dir.joinpath(*pp.parts)
    try:
        resolved = rpy_path.resolve()
        game_root = (project_dir / "game").resolve()
        resolved.relative_to(game_root)
    except ValueError:
        raise HTTPException(
            status_code=500,
            detail=f"Scene index has invalid file_path for {scene_id}: must stay under game/",
        )

    if not rpy_path.exists():
        raise HTTPException(status_code=404, detail="Scene script file not found")

    try:
        content = rpy_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot read scene script: {exc}")

    script = SceneScript(
        scene_id=scene_id,
        chapter_id=mapping.get("chapter_id", ""),
        label=mapping.get("label", ""),
        content=content,
        file_path=raw_file_path,
    )
    return script.model_dump(mode="json")


@router.post("/api/projects/{project_name}/prototype/multi-chapter/activate")
async def api_activate_multi_chapter_prototype(project_name: str):
    """Activate a previously generated multi-chapter prototype as the runtime entry."""
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    settings = get_settings()
    pm = ProjectManager(settings)
    service = PrototypeGenerationService(pm=pm, provider=None)

    try:
        result = service.activate_multi_chapter_prototype(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return result


@router.get("/api/projects/{project_name}/prototype/status")
async def api_prototype_status(project_name: str):
    """Return whether the project has a generated prototype and its readiness."""
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    settings = get_settings()
    pm = ProjectManager(settings)
    service = PrototypeGenerationService(pm=pm, provider=None)

    try:
        status = service.get_prototype_runtime_status(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return status


@router.get("/api/projects/{project_name}/prototype/pipeline-status")
async def api_prototype_pipeline_status(project_name: str):
    """Return the unified prototype pipeline stage derived from project state."""
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    settings = get_settings()
    pm = ProjectManager(settings)
    service = PrototypeGenerationService(pm=pm, provider=None)
    try:
        proto_status = service.get_prototype_runtime_status(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    has_manifest = proto_status.get("has_manifest", False)
    if has_manifest:
        has_proto = proto_status["is_buildable"] or proto_status["is_active"]
    else:
        has_proto = _has_prototype(project_name)

    build_status = _read_build_status(project_name)

    runtime_stage: str | None = None
    session_path = project_dir / "meta" / "blueprint_session.json"
    if session_path.exists():
        try:
            session = json.loads(session_path.read_text(encoding="utf-8"))
            runtime_stage = session.get("pipeline_stage")
        except (json.JSONDecodeError, OSError):
            pass

    if runtime_stage == "generating":
        stage = "prototype_generating"
    elif not has_proto:
        stage = "idle"
    elif build_status and build_status.get("status") == "building":
        stage = "prototype_building"
    elif build_status and build_status.get("status") == "failed":
        stage = "prototype_build_failed"
    elif build_status and build_status.get("status") == "success" and build_status.get("previewable"):
        stage = "prototype_preview_ready"
    else:
        stage = "prototype_ready"

    message_map = {
        "idle": "No prototype generated yet",
        "prototype_generating": "Prototype generation in progress",
        "prototype_ready": "Prototype ready, not yet built",
        "prototype_building": "Prototype build in progress",
        "prototype_build_failed": "Prototype build failed",
        "prototype_preview_ready": "Prototype built and previewable",
    }

    if build_status and build_status.get("message"):
        message = build_status["message"]
    else:
        message = message_map.get(stage, "")

    return {
        "stage": stage,
        "has_prototype": has_proto,
        "previewable": build_status.get("previewable", False) if build_status else False,
        "build_status": build_status.get("status", "idle") if build_status else "idle",
        "message": message,
        "has_manifest": proto_status.get("has_manifest"),
        "mode": proto_status.get("mode"),
        "is_active": proto_status.get("is_active"),
        "is_buildable": proto_status.get("is_buildable"),
        "manifest_consistent": proto_status.get("manifest_consistent"),
    }
