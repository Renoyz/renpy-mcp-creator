"""FastAPI application for unified-design Dashboard and API.

After the P2-2 router extraction, this module retains only:

* Module-level shared state (config, preview manager, build cache)
* Shared helper functions used by multiple routers
* The ``create_app()`` factory that assembles middleware, routers, and mounts
"""

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from collections.abc import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from ..config import RenPyConfig, _current_project_path, get_settings, resolve_project_dir
from ..services.preview_manager import PreviewManager

STATIC_DIR = Path(__file__).parent / "static"
DASHBOARD_DIR = Path(__file__).parent.parent.parent.parent / "dashboard" / "dist"

_preview_manager = PreviewManager()
_last_build_results: dict[str, Path] = {}
_last_build_results_lock = threading.Lock()
logger = logging.getLogger(__name__)

# Injected config (set during bootstrap)
_app_config: RenPyConfig | None = None


def set_config(config: RenPyConfig) -> None:
    global _app_config
    _app_config = config


def _get_base_config() -> RenPyConfig:
    if _app_config is None:
        raise RuntimeError("FastAPI config not set")
    return _app_config


async def get_config(request: Request) -> AsyncGenerator[RenPyConfig, None]:
    config = _get_base_config()
    session_name = request.session.get("current_project_name")
    token = None
    if session_name:
        project_dir = resolve_project_dir(session_name)
        if project_dir:
            token = _current_project_path.set(project_dir)
    try:
        yield config
    finally:
        if token is not None:
            _current_project_path.reset(token)


def _resolve_current_project_name(request: Request, body: dict | None = None) -> str:
    """Resolve the current session project and reject mismatched explicit names."""
    body = body or {}
    requested_name = (body.get("name") or "").strip()
    session_name = (request.session.get("current_project_name") or "").strip()

    if not session_name:
        raise HTTPException(status_code=400, detail="No current project selected")

    if requested_name and requested_name != session_name:
        raise HTTPException(
            status_code=400,
            detail="Requested project does not match the current project",
        )

    return session_name


def _sanitize_sprite_plan_for_api(sprite_plan: list[Any] | None) -> list[dict]:
    """Strip internal fields from sprite_plan items before API exposure."""
    if not sprite_plan:
        return []
    result: list[dict] = []
    for item in sprite_plan:
        if isinstance(item, dict):
            cleaned = dict(item)
            for internal_key in (
                "sprite_check_path",
                "staging_path",
                "raw_path",
                "transparent_path",
                "normalized_path",
            ):
                cleaned.pop(internal_key, None)
            result.append(cleaned)
    return result


# ---------------------------------------------------------------------------
# Build status helpers (shared across routers)
# ---------------------------------------------------------------------------

def _previewable_output_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    if (path / "index.html").exists():
        return path
    return None


def _store_previewable_build_result(project_name: str, output_path: Path | None) -> None:
    resolved = _previewable_output_path(output_path)
    with _last_build_results_lock:
        if resolved is not None:
            _last_build_results[project_name] = resolved
        else:
            _last_build_results.pop(project_name, None)


def _clear_cached_build_result(project_name: str) -> None:
    with _last_build_results_lock:
        _last_build_results.pop(project_name, None)


def _build_status_path(project_name: str) -> Path:
    settings = get_settings()
    return settings.workspace / project_name / "logs" / "build-status.json"


def _write_build_status(
    project_name: str,
    status: str,
    message: str,
    output_path: Path | None,
    *,
    target: str | None = None,
) -> None:
    status_path = _build_status_path(project_name)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "status": status,
        "message": message,
        "output_path": str(output_path) if output_path else None,
        "previewable": _previewable_output_path(output_path) is not None,
        "target": target,
        "updated_at": datetime.utcnow().isoformat(),
    }
    status_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_build_status(project_name: str) -> dict | None:
    status_path = _build_status_path(project_name)
    if not status_path.exists():
        return None
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _resolve_preview_build_dir(project_name: str) -> Path | None:
    """Resolve the previewable build directory from memory cache or persisted status."""
    with _last_build_results_lock:
        cached = _last_build_results.get(project_name)
    if cached is not None:
        return Path(cached)
    persisted = _read_build_status(project_name)
    if persisted and persisted.get("previewable") and persisted.get("output_path"):
        return Path(persisted["output_path"])
    return None


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(title="RenPy MCP Unified Server")
    settings = get_settings()
    secret_key = settings.session_secret or os.environ.get("SESSION_SECRET")
    if not secret_key:
        import secrets

        secret_key = secrets.token_urlsafe(32)
    app.add_middleware(SessionMiddleware, secret_key=secret_key)

    # Include routers
    from .routers.pages import router as pages_router
    from .routers.projects import router as projects_router
    from .routers.refinement import router as refinement_router
    from .routers.generation import router as generation_router
    from .routers.preview_build import router as preview_build_router
    from .routers.scripts_assets import router as scripts_assets_router

    app.include_router(pages_router)
    app.include_router(projects_router)
    app.include_router(refinement_router)
    app.include_router(generation_router)
    app.include_router(preview_build_router)
    app.include_router(scripts_assets_router)

    # Dashboard static assets (React build output)
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")

    # Chat WebSocket
    from .chat_ws import router as chat_router
    app.include_router(chat_router)

    # Mount MCP SSE endpoint so Dashboard/CLI can connect via HTTP
    from ..server import mcp
    app.mount("/mcp", mcp.sse_app())

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app
