"""Preview and build routes."""

import json
import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from ...config import get_settings, resolve_project_dir
from ...models import BuildRequest, BuildResult
from ...services.build_manager import BuildManager
from ...services.project_manager import ProjectManager
from ...services.prototype_generation_service import PrototypeGenerationService
from .. import fastapi_app as _fa
from ..fastapi_app import (
    _read_build_status,
    _resolve_current_project_name,
    _resolve_preview_build_dir,
    _store_previewable_build_result,
    _write_build_status,
    _build_status_path,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/projects/{project_name}/prototype/build")
async def api_build_project_prototype(request: Request, project_name: str):
    """Build a project that has a generated prototype."""
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

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
        raise HTTPException(
            status_code=400,
            detail="No prototype scenes found. Generate a prototype first.",
        )

    script_paths = {s.get("file_path") for s in proto_scenes if s.get("file_path")}
    for rel_path in script_paths:
        if not (project_dir / rel_path).exists():
            raise HTTPException(
                status_code=400,
                detail=f"Prototype script not found: {rel_path}",
            )

    main_script = project_dir / "game" / "script.rpy"
    if not main_script.exists():
        raise HTTPException(
            status_code=400,
            detail="Main script (game/script.rpy) not found",
        )
    if "# PROTOTYPE START (managed)" not in main_script.read_text(encoding="utf-8"):
        raise HTTPException(
            status_code=400,
            detail="Main script is not wired to a prototype",
        )

    try:
        manifest = pm.read_prototype_manifest(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if manifest is not None:
        if manifest.mode not in ("single_chapter", "multi_chapter"):
            raise HTTPException(
                status_code=400,
                detail="No active prototype mode. Activate a prototype first.",
            )
        if manifest.entry_file and not (project_dir / manifest.entry_file).exists():
            raise HTTPException(
                status_code=400,
                detail=f"Prototype entry file missing: {manifest.entry_file}",
            )
        service = PrototypeGenerationService(pm=pm, provider=None)
        wired_label = service._read_managed_entry_label(project_name)
        if wired_label != manifest.entry_label:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Active prototype entry is inconsistent with manifest. "
                    f"Wired label: {wired_label}, manifest expects: {manifest.entry_label}"
                ),
            )

    target = "web"

    if os.environ.get("RENPY_MCP_MOCK_BUILD"):
        build_dir = project_dir.parent / f"{project_name}-dists" / f"{project_name}-web"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "index.html").write_text("<html><body>mock preview</body></html>", encoding="utf-8")
        _store_previewable_build_result(project_name, build_dir)
        _write_build_status(
            project_name, "success",
            f"Prototype built to {build_dir}", build_dir, target=target,
        )
        status_path = _build_status_path(project_name)
        if status_path.exists():
            data = json.loads(status_path.read_text(encoding="utf-8"))
            data["kind"] = "prototype"
            status_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return BuildResult(
            project_name=project_name,
            target=target,
            success=True,
            output_path=build_dir,
        ).model_dump(mode="json")

    manager = BuildManager(settings)
    result = await manager.build(BuildRequest(project_name=project_name, target=target))
    if result.success:
        _store_previewable_build_result(project_name, result.output_path)
        _write_build_status(
            project_name,
            "success",
            f"Prototype built to {result.output_path}" if result.output_path else "Prototype build succeeded",
            result.output_path,
            target=target,
        )
    else:
        _fa._last_build_results.pop(project_name, None)
        _write_build_status(
            project_name,
            "failed",
            result.error or "Prototype build failed",
            None,
            target=target,
        )
    status_path = _build_status_path(project_name)
    if status_path.exists():
        data = json.loads(status_path.read_text(encoding="utf-8"))
        data["kind"] = "prototype"
        status_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return result.model_dump(mode="json")


@router.post("/api/projects/build")
async def api_build_project(request: Request):
    body = await request.json()
    name = _resolve_current_project_name(request, body)
    target = body.get("target", "web")
    project_dir = resolve_project_dir(name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    if os.environ.get("RENPY_MCP_MOCK_BUILD"):
        build_dir = project_dir.parent / f"{name}-dists" / f"{name}-web"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "index.html").write_text("<html><body>mock preview</body></html>", encoding="utf-8")
        _store_previewable_build_result(name, build_dir)
        _write_build_status(name, "success", f"Built to {build_dir}", build_dir, target=target)
        return BuildResult(
            project_name=name,
            target=target,
            success=True,
            output_path=build_dir,
        ).model_dump(mode="json")

    manager = BuildManager(get_settings())
    result = await manager.build(BuildRequest(project_name=name, target=target))
    if result.success:
        _store_previewable_build_result(name, result.output_path)
        _write_build_status(
            name,
            "success",
            f"Built to {result.output_path}" if result.output_path else "Build succeeded",
            result.output_path,
            target=target,
        )
    else:
        _fa._last_build_results.pop(name, None)
        _write_build_status(
            name,
            "failed",
            result.error or "Build failed",
            None,
            target=target,
        )
    return result.model_dump(mode="json")


@router.post("/api/projects/{project_name}/build")
async def api_build_project_scoped(request: Request, project_name: str):
    """Build a specific project (project-scoped, not session-scoped)."""
    body = await request.json()
    target = body.get("target", "web")
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    if os.environ.get("RENPY_MCP_MOCK_BUILD"):
        build_dir = project_dir.parent / f"{project_name}-dists" / f"{project_name}-web"
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "index.html").write_text("<html><body>mock preview</body></html>", encoding="utf-8")
        _store_previewable_build_result(project_name, build_dir)
        _write_build_status(project_name, "success", f"Built to {build_dir}", build_dir, target=target)
        return BuildResult(
            project_name=project_name,
            target=target,
            success=True,
            output_path=build_dir,
        ).model_dump(mode="json")

    manager = BuildManager(get_settings())
    result = await manager.build(BuildRequest(project_name=project_name, target=target))
    if result.success:
        _store_previewable_build_result(project_name, result.output_path)
        _write_build_status(
            project_name,
            "success",
            f"Built to {result.output_path}" if result.output_path else "Build succeeded",
            result.output_path,
            target=target,
        )
    else:
        _fa._last_build_results.pop(project_name, None)
        _write_build_status(
            project_name,
            "failed",
            result.error or "Build failed",
            None,
            target=target,
        )
    return result.model_dump(mode="json")


@router.get("/api/projects/build/status")
async def api_build_status(request: Request):
    name = _resolve_current_project_name(request)
    status = _read_build_status(name)
    if status is None:
        return {"status": "idle", "message": "", "output_path": None, "previewable": False, "target": None, "updated_at": None}
    return {
        "status": status.get("status", "idle"),
        "message": status.get("message", ""),
        "output_path": status.get("output_path"),
        "previewable": status.get("previewable", False),
        "target": status.get("target"),
        "updated_at": status.get("updated_at"),
    }


@router.post("/api/projects/preview")
async def api_preview_project(request: Request):
    body = await request.json()
    name = _resolve_current_project_name(request, body)
    project_dir = resolve_project_dir(name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    build_dir = _resolve_preview_build_dir(name)
    if build_dir is None:
        raise HTTPException(status_code=404, detail="No successful build available. Run build first.")
    build_dir = Path(build_dir)
    if not build_dir.exists() or not (build_dir / "index.html").exists():
        raise HTTPException(status_code=404, detail="No web build found. Run build first.")
    try:
        server = await _fa._preview_manager.start(name, build_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Preview failed: {exc}")
    return {"success": True, "url": server.url, "port": server.port}


@router.post("/api/projects/preview/stop")
async def api_stop_preview(request: Request):
    body = await request.json()
    name = _resolve_current_project_name(request, body)
    stopped = await _fa._preview_manager.stop(name)
    return {"success": stopped, "project": name}


@router.get("/api/projects/preview/status")
async def api_preview_status(request: Request):
    name = _resolve_current_project_name(request)
    status = _fa._preview_manager.status(name)
    return status


# ---------------------------------------------------------------------------
# Project-scoped build status and preview
# ---------------------------------------------------------------------------


@router.get("/api/projects/{project_name}/build/status")
async def api_project_build_status(project_name: str):
    """Return build status for a specific project."""
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    status = _read_build_status(project_name)
    if status is None:
        return {"status": "idle", "message": "", "output_path": None, "previewable": False, "target": None, "updated_at": None}
    return {
        "status": status.get("status", "idle"),
        "message": status.get("message", ""),
        "output_path": status.get("output_path"),
        "previewable": status.get("previewable", False),
        "target": status.get("target"),
        "updated_at": status.get("updated_at"),
    }


@router.post("/api/projects/{project_name}/preview")
async def api_project_preview(project_name: str):
    """Start preview for a specific project."""
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    build_dir = _resolve_preview_build_dir(project_name)
    if build_dir is None:
        raise HTTPException(status_code=404, detail="No successful build available. Run build first.")
    build_dir = Path(build_dir)
    if not build_dir.exists() or not (build_dir / "index.html").exists():
        raise HTTPException(status_code=404, detail="No web build found. Run build first.")
    try:
        server = await _fa._preview_manager.start(project_name, build_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Preview failed: {exc}")
    return {"success": True, "url": server.url, "port": server.port}


@router.get("/api/projects/{project_name}/preview/status")
async def api_project_preview_status(project_name: str):
    """Return preview runtime status for a specific project."""
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    status = _fa._preview_manager.status(project_name)
    return status
