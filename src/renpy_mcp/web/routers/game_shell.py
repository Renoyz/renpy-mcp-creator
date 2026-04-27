"""Project-scoped Game Shell routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from ...blueprint.models import GameShellConfig
from ...config import get_settings, resolve_project_dir
from ...services.game_shell_render_service import GameShellRenderService
from ...services.project_manager import ProjectManager

router = APIRouter()


def _service(project_name: str) -> GameShellRenderService:
    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")
    return GameShellRenderService(ProjectManager(get_settings()))


@router.get("/api/projects/{project_name}/game-shell")
async def api_get_game_shell(project_name: str):
    service = _service(project_name)
    try:
        config = service.read_or_derive_config(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return config.model_dump(mode="json")


@router.put("/api/projects/{project_name}/game-shell")
async def api_put_game_shell(request: Request, project_name: str):
    service = _service(project_name)
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Game Shell JSON: {exc}")
    try:
        config = GameShellConfig.model_validate(body)
        saved = service.save_config(project_name, config)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return saved.model_dump(mode="json")


@router.post("/api/projects/{project_name}/game-shell/derive")
async def api_derive_game_shell(project_name: str):
    service = _service(project_name)
    try:
        config = service.derive_and_save_config(project_name)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return config.model_dump(mode="json")


@router.post("/api/projects/{project_name}/game-shell/render-preview")
async def api_render_game_shell_preview(request: Request, project_name: str):
    service = _service(project_name)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = None
    try:
        config = GameShellConfig.model_validate(body) if isinstance(body, dict) and body else None
        preview = service.render_preview(project_name, config)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return preview.model_dump(mode="json")


@router.post("/api/projects/{project_name}/game-shell/reset-defaults")
async def api_reset_game_shell(project_name: str):
    service = _service(project_name)
    try:
        config = service.derive_and_save_config(project_name)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return config.model_dump(mode="json")
