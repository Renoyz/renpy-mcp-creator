"""Project CRUD routes + blueprint get/put + chat history + session."""

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from ...blueprint.models import ProjectBlueprint, ProjectMeta
from ...config import get_settings, resolve_project_dir
from ...services.project_manager import ProjectManager
from ..fastapi_app import _resolve_current_project_name

router = APIRouter()


@router.get("/api/projects")
async def api_projects():
    settings = get_settings()
    project_manager = ProjectManager(settings)
    result = project_manager.list_projects()
    projects = [p.model_dump(mode="json") for p in result.projects]
    return {"projects": projects, "errors": result.errors}


@router.post("/api/projects")
async def api_projects_create(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    template = body.get("template")
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")

    settings = get_settings()
    project_manager = ProjectManager(settings)
    template_name = template or settings.default_template
    project_dir = project_manager.ensure_project_dir(name)
    template_path = project_manager.find_template(template_name)
    project_manager.copy_template(project_dir, template_path)

    return {
        "success": True,
        "name": name,
        "path": str(project_dir),
        "template": template_name,
    }


@router.get("/api/projects/current")
async def api_projects_current(request: Request):
    session_name = request.session.get("current_project_name")
    if not session_name:
        return {"current_project": None}
    project_dir = resolve_project_dir(session_name)
    if not project_dir:
        return {"current_project": None}
    return {
        "current_project": {
            "name": project_dir.name,
            "path": str(project_dir),
        }
    }


@router.post("/api/projects/select")
async def api_projects_select(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required")
    project_dir = resolve_project_dir(name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    request.session["current_project_name"] = name
    return {
        "success": True,
        "current_project": {
            "name": project_dir.name,
            "path": str(project_dir),
        },
    }


@router.get("/api/projects/{project_name}/meta")
async def api_project_meta(project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    settings = get_settings()
    pm = ProjectManager(settings)
    try:
        meta = pm.read_project_meta(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if meta is None:
        meta = ProjectMeta(name=project_name, path=project_dir)
    return meta.model_dump(mode="json")


@router.put("/api/projects/{project_name}/meta")
async def api_project_meta_put(request: Request, project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid project meta: malformed JSON ({exc})"
        )
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail="Invalid project meta: body must be a JSON object"
        )
    settings = get_settings()
    pm = ProjectManager(settings)
    try:
        existing = pm.read_project_meta(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if existing is None:
        existing = ProjectMeta(name=project_name, path=project_dir)
    allowed = {k for k in ProjectMeta.model_fields if k not in ("path", "name")}
    unknown = [k for k in body if k not in allowed and k not in ("path", "name")]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid project meta: unsupported fields {unknown}",
        )
    updates = {k: v for k, v in body.items() if k in allowed}
    existing_dict = json.loads(existing.model_dump_json(by_alias=False))
    existing_dict.update(updates)
    existing_dict["name"] = project_name
    existing_dict["path"] = str(project_dir)
    try:
        updated = ProjectMeta.model_validate(existing_dict)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid project meta: {exc}")
    pm.write_project_meta(project_name, updated)
    return {"success": True}


@router.get("/api/projects/{project_name}/blueprint")
async def api_project_blueprint(project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    settings = get_settings()
    pm = ProjectManager(settings)
    try:
        blueprint = pm.read_blueprint(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if blueprint is None:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    return blueprint.model_dump(mode="json")


@router.put("/api/projects/{project_name}/blueprint")
async def api_project_blueprint_put(request: Request, project_name: str):
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid blueprint: malformed JSON ({exc})"
        )
    try:
        blueprint = ProjectBlueprint.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid blueprint: {exc}")
    settings = get_settings()
    pm = ProjectManager(settings)
    try:
        brief = pm.read_project_brief(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        outline = pm.read_chapter_outline(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if brief is not None or outline is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Manual blueprint updates are blocked for refinement-managed projects. "
                "Use /api/projects/{name}/blueprint/freeze after confirming Project Brief "
                "and Chapter Outline."
            ),
        )
    pm.write_blueprint(project_name, blueprint)
    return {"success": True}


# ---------------------------------------------------------------------------
# Chat / session read-only endpoints
# ---------------------------------------------------------------------------


@router.get("/api/projects/{project_name}/chat/history")
async def api_chat_history(request: Request, project_name: str):
    from ..chat_ws import _read_chat_history

    name = _resolve_current_project_name(request, {"name": project_name})
    messages = _read_chat_history(name)
    return {"messages": messages}


@router.get("/api/projects/{project_name}/blueprint-session")
async def api_blueprint_session(project_name: str):
    from ..chat_ws import _load_runtime_session

    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    session = _load_runtime_session(project_name)
    if session is None:
        return {"pipeline_stage": "idle", "awaiting_confirmation": False}
    return session
