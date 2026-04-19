"""FastAPI application for unified-design Dashboard and API."""

import json
import os
import re
import struct
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from collections.abc import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.sessions import SessionMiddleware

from ..config import RenPyConfig, _current_project_path, get_settings, resolve_project_dir
from ..blueprint.models import (
    FlowEdge,
    FlowNode,
    ProjectBlueprint,
    ProjectMeta,
    SceneScript,
)
from ..models import BuildRequest, BuildResult
from ..services.build_manager import BuildManager
from ..services.preview_manager import PreviewManager
from ..services.project_manager import ProjectManager
from .server import _parse_script_blocks

STATIC_DIR = Path(__file__).parent / "static"
DASHBOARD_DIR = Path(__file__).parent.parent.parent.parent / "dashboard" / "dist"

_preview_manager = PreviewManager()
_last_build_results: dict[str, Path] = {}

# Injected config (set during bootstrap)
_app_config: RenPyConfig | None = None
_bridge_lock = threading.Lock()


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


def _send_bridge_command(config: RenPyConfig, cmd: dict, timeout: float = 5.0) -> dict:
    """Send a command via file-based IPC and wait for response."""
    if not config.project_path:
        return {"success": False, "error": "No project set"}

    with _bridge_lock:
        mcp_dir = config.project_path / "game" / "_mcp"
        mcp_dir.mkdir(exist_ok=True)
        status_file = mcp_dir / "status.json"
        start = time.time()
        expected_action = cmd.get("action", "")

        tmp = mcp_dir / "cmd.json.tmp"
        cmd_file = mcp_dir / "cmd.json"
        tmp.write_text(json.dumps(cmd, ensure_ascii=False), encoding="utf-8")
        if cmd_file.exists():
            cmd_file.unlink()
        tmp.rename(cmd_file)

        while time.time() - start < timeout:
            if status_file.exists():
                try:
                    data = json.loads(status_file.read_text(encoding="utf-8"))
                    if data.get("time", 0) >= start and data.get("action") == expected_action:
                        return data
                except (json.JSONDecodeError, OSError):
                    pass
            time.sleep(0.2)
        return {"success": False, "error": "Timeout waiting for game response"}


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


def _previewable_output_path(path: Path | None) -> Path | None:
    """Return a previewable web directory if the build output can be served."""
    if path is None:
        return None

    candidate = Path(path)
    if candidate.is_dir() and (candidate / "index.html").exists():
        return candidate
    return None


def _store_previewable_build_result(project_name: str, output_path: Path | None) -> None:
    """Persist only previewable build outputs and clear stale entries otherwise."""
    preview_path = _previewable_output_path(output_path)
    if preview_path is not None:
        _last_build_results[project_name] = preview_path
    else:
        _last_build_results.pop(project_name, None)


def _build_status_path(project_name: str) -> Path:
    """Return the path to the project's persisted build status file."""
    settings = get_settings()
    return settings.workspace / project_name / "logs" / "build-status.json"


def _write_build_status(
    project_name: str,
    status: str,
    message: str,
    output_path: Path | None,
    target: str = "web",
) -> None:
    """Persist build status to disk."""
    status_file = _build_status_path(project_name)
    status_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": status,
        "message": message,
        "output_path": str(output_path) if output_path else None,
        "previewable": _previewable_output_path(output_path) is not None,
        "target": target,
        "updated_at": datetime.utcnow().isoformat(),
    }
    status_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_build_status(project_name: str) -> dict | None:
    """Read persisted build status if it exists."""
    status_file = _build_status_path(project_name)
    if not status_file.exists():
        return None
    try:
        return json.loads(status_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _resolve_preview_build_dir(project_name: str) -> Path | None:
    """Resolve the previewable build directory from memory cache or persisted status."""
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

        # Generate an ephemeral secret for this process lifetime.
        # WARNING: Sessions will not persist across server restarts.
        secret_key = secrets.token_urlsafe(32)
    app.add_middleware(SessionMiddleware, secret_key=secret_key)

    # ---- Page routes ----

    @app.get("/")
    async def root():
        return RedirectResponse(url="/dashboard")

    @app.get("/dashboard")
    async def dashboard():
        return FileResponse(DASHBOARD_DIR / "index.html")

    @app.get("/dashboard/{path:path}")
    async def dashboard_fallback(path: str):
        """SPA fallback for React Router deep links."""
        dashboard_root = DASHBOARD_DIR.resolve()
        candidate = (dashboard_root / path).resolve()
        try:
            candidate.relative_to(dashboard_root)
        except ValueError:
            raise HTTPException(status_code=404, detail="Not found")

        if candidate.exists() and candidate.is_file():
            return FileResponse(candidate)

        # If the path looks like a static asset request but the file is missing, 404
        STATIC_EXTS = {
            ".js", ".css", ".svg", ".png", ".jpg", ".jpeg",
            ".webp", ".gif", ".ico", ".map", ".woff", ".woff2",
            ".ttf", ".eot", ".json", ".xml", ".pdf", ".zip",
        }
        if candidate.suffix.lower() in STATIC_EXTS:
            raise HTTPException(status_code=404, detail="Not found")

        return FileResponse(dashboard_root / "index.html")

    @app.get("/story-map")
    async def story_map():
        return FileResponse(STATIC_DIR / "story_map.html")

    @app.get("/script-editor")
    async def script_editor():
        return FileResponse(STATIC_DIR / "script_editor.html")

    @app.get("/heatmap")
    async def heatmap():
        return FileResponse(STATIC_DIR / "heatmap.html")

    @app.get("/assets")
    async def assets_page():
        return FileResponse(STATIC_DIR / "asset_manager.html")

    # ---- API routes ----

    @app.get("/api/projects")
    async def api_projects():
        settings = get_settings()
        project_manager = ProjectManager(settings)
        result = project_manager.list_projects()
        projects = [p.model_dump(mode="json") for p in result.projects]
        return {"projects": projects, "errors": result.errors}

    @app.post("/api/projects")
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

    @app.get("/api/projects/current")
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

    @app.post("/api/projects/select")
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

    @app.get("/api/projects/{project_name}/meta")
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

    @app.put("/api/projects/{project_name}/meta")
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
        # Round-trip through JSON so enum/datetime fields are properly parsed
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

    @app.get("/api/projects/{project_name}/blueprint")
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

    @app.put("/api/projects/{project_name}/blueprint")
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
        pm.write_blueprint(project_name, blueprint)
        return {"success": True}

    @app.get("/api/projects/{project_name}/scenes")
    async def api_project_scenes(project_name: str):
        project_dir = resolve_project_dir(project_name)
        if not project_dir:
            raise HTTPException(status_code=404, detail="Project not found")
        settings = get_settings()
        pm = ProjectManager(settings)

        # Prefer prototype scenes from index when available
        index = pm.read_project_index(project_name)
        if index and isinstance(index.get("scenes"), dict):
            prototype_scenes = [
                s for s in index["scenes"].values()
                if isinstance(s, dict) and s.get("source") == "prototype"
            ]
            if prototype_scenes:
                # Build chapter name lookup from blueprint if available
                chapter_names: dict[str, str] = {}
                try:
                    blueprint = pm.read_blueprint(project_name)
                    if blueprint:
                        for ch in blueprint.chapters:
                            chapter_names[ch.id] = ch.name
                except ValueError:
                    pass

                from collections import defaultdict
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
                                "characters": [],
                                "backgrounds": [],
                                "music": None,
                                "choices": None,
                                "ending_name": None,
                                "status": "pending",
                                "type": "normal",
                                "is_ending": None,
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

    @app.get("/api/projects/{project_name}/storymap")
    async def api_project_storymap(project_name: str):
        project_dir = resolve_project_dir(project_name)
        if not project_dir:
            raise HTTPException(status_code=404, detail="Project not found")
        settings = get_settings()
        pm = ProjectManager(settings)

        # Prefer prototype scenes from index when available
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

        # Fallback to blueprint
        try:
            blueprint = pm.read_blueprint(project_name)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        if blueprint is None:
            raise HTTPException(status_code=404, detail="Blueprint not found")

        nodes: list[FlowNode] = []
        edges: list[FlowEdge] = []

        # Build a lookup for scene_id -> chapter_id
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
                if scene.choices:
                    for choice in scene.choices:
                        if choice.next_scene_id not in scene_to_chapter:
                            continue
                        target_ch_id = scene_to_chapter[choice.next_scene_id]
                        edges.append(
                            FlowEdge(
                                from_chapter_id=ch.id,
                                from_scene_id=scene.id,
                                to_chapter_id=target_ch_id,
                                to_scene_id=choice.next_scene_id,
                                type="branch",
                                label=choice.text,
                            )
                        )
                prev_scene = scene

        return {
            "nodes": [n.model_dump(mode="json") for n in nodes],
            "edges": [e.model_dump(mode="json") for e in edges],
        }

    @app.get("/api/projects/{project_name}/scenes/{scene_id}/script")
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
            raise HTTPException(
                status_code=500, detail=f"Scene index is corrupt: {exc}"
            )
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail=f"Cannot read scene index: {exc}"
            )

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

        from pathlib import PurePosixPath

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
            raise HTTPException(
                status_code=500, detail=f"Cannot read scene script: {exc}"
            )

        script = SceneScript(
            scene_id=scene_id,
            chapter_id=mapping.get("chapter_id", ""),
            label=mapping.get("label", ""),
            content=content,
            file_path=raw_file_path,
        )
        return script.model_dump(mode="json")

    @app.post("/api/projects/build")
    async def api_build_project(request: Request):
        body = await request.json()
        name = _resolve_current_project_name(request, body)
        target = body.get("target", "web")
        project_dir = resolve_project_dir(name)
        if not project_dir:
            raise HTTPException(status_code=404, detail="Project not found")

        # Test-only mock path: create a fake build result directly
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
            _last_build_results.pop(name, None)
            _write_build_status(
                name,
                "failed",
                result.error or "Build failed",
                None,
                target=target,
            )
        return result.model_dump(mode="json")

    @app.get("/api/projects/build/status")
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

    @app.get("/api/projects/{project_name}/chat/history")
    async def api_chat_history(request: Request, project_name: str):
        from .chat_ws import _read_chat_history
        name = _resolve_current_project_name(request, {"name": project_name})
        messages = _read_chat_history(name)
        return {"messages": messages}

    @app.get("/api/projects/{project_name}/blueprint-session")
    async def api_blueprint_session(project_name: str):
        from .chat_ws import _load_runtime_session
        project_dir = resolve_project_dir(project_name)
        if not project_dir:
            raise HTTPException(status_code=404, detail="Project not found")
        session = _load_runtime_session(project_name)
        if session is None:
            return {"pipeline_stage": "idle", "awaiting_confirmation": False}
        return session

    @app.post("/api/projects/preview")
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
        server = await _preview_manager.start(name, build_dir)
        return {"success": True, "url": server.url, "port": server.port}

    @app.post("/api/projects/preview/stop")
    async def api_stop_preview(request: Request):
        body = await request.json()
        name = _resolve_current_project_name(request, body)
        stopped = await _preview_manager.stop(name)
        return {"success": stopped, "project": name}

    @app.get("/api/graph")
    async def api_graph(config: RenPyConfig = Depends(get_config)):
        if not config.project_path:
            raise HTTPException(status_code=400, detail="No project set")

        game_dir = config.project_path / "game"
        label_re = re.compile(r'^label\s+(\w+)(?:\s*\(.*\))?\s*:')

        scripts: dict[str, list[str]] = {}
        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            try:
                rel = str(rpy_file.relative_to(game_dir))
                if rel.startswith("tl") or rel.startswith("_mcp") or rel == "testcases.rpy":
                    continue
                scripts[rel] = rpy_file.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue

        labels: dict[str, dict] = {}
        for filepath, lines in scripts.items():
            for i, line in enumerate(lines):
                m = label_re.match(line.strip())
                if m:
                    name = m.group(1)
                    if name.startswith("_"):
                        continue
                    labels[name] = {
                        "file": filepath,
                        "line": i + 1,
                        "jumps_to": [],
                        "called_by": [],
                        "has_return": False,
                        "has_menu": False,
                        "menu_choices": [],
                        "dialogue_count": 0,
                    }

            current_label = None
            in_menu = False
            dialogue_re = re.compile(r'^\s+(?:\w+\s+)?"[^"]*"')

            for i, line in enumerate(lines):
                stripped = line.strip()
                m = label_re.match(stripped)
                if m:
                    name = m.group(1)
                    if not name.startswith("_"):
                        current_label = name
                        in_menu = False

                if current_label and current_label in labels:
                    if stripped.startswith("jump "):
                        labels[current_label]["jumps_to"].append(stripped[5:].strip())
                    elif stripped.startswith("call "):
                        labels[current_label]["jumps_to"].append(f"call:{stripped[5:].strip().split()[0]}")
                    elif stripped == "return":
                        labels[current_label]["has_return"] = True
                    elif stripped.startswith("menu"):
                        labels[current_label]["has_menu"] = True
                        in_menu = True
                    elif in_menu and stripped.endswith('":') and '"' in stripped:
                        choice_match = re.search(r'"([^"]*)"', stripped)
                        if choice_match:
                            labels[current_label]["menu_choices"].append(choice_match.group(1))
                    elif dialogue_re.match(line):
                        labels[current_label]["dialogue_count"] += 1

        for label_name, info in labels.items():
            for target in info["jumps_to"]:
                clean = target.replace("call:", "")
                if clean in labels:
                    labels[clean]["called_by"].append(label_name)

        nodes = []
        edges = []
        for name, info in labels.items():
            node_type = "start" if name == "start" else "normal"
            if not info["jumps_to"] and not info["has_return"]:
                if not info["called_by"] and name != "start":
                    node_type = "orphan"
                else:
                    node_type = "dead_end"
            elif info["has_return"] and not info["jumps_to"]:
                node_type = "end"

            nodes.append({
                "id": name,
                "type": node_type,
                "file": info["file"],
                "line": info["line"],
                "has_menu": info["has_menu"],
                "menu_choices": info["menu_choices"],
                "dialogue_count": info["dialogue_count"],
                "has_return": info["has_return"],
            })

            for target in info["jumps_to"]:
                is_call = target.startswith("call:")
                clean = target.replace("call:", "")
                if clean in labels:
                    edges.append({
                        "source": name,
                        "target": clean,
                        "type": "call" if is_call else "jump",
                    })

        return {"nodes": nodes, "edges": edges}

    @app.get("/api/status")
    async def api_status(config: RenPyConfig = Depends(get_config)):
        if not config.project_path:
            return {"connected": False, "error": "No project set"}

        status_file = config.project_path / "game" / "_mcp" / "status.json"
        if status_file.exists():
            try:
                data = json.loads(status_file.read_text(encoding="utf-8"))
                age = time.time() - data.get("time", 0)
                return {"connected": age < 5, "age": age}
            except Exception:
                pass
        return {"connected": False}

    @app.get("/api/labels")
    async def api_labels(config: RenPyConfig = Depends(get_config)):
        if not config.project_path:
            raise HTTPException(status_code=400, detail="No project set")

        game_dir = config.project_path / "game"
        label_re = re.compile(r'^label\s+(\w+)(?:\s*\(.*\))?\s*:')
        labels = []
        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            try:
                rel = str(rpy_file.relative_to(game_dir))
                if rel.startswith("tl") or rel.startswith("_mcp") or rel == "testcases.rpy":
                    continue
                for line in rpy_file.read_text(encoding="utf-8").splitlines():
                    m = label_re.match(line.strip())
                    if m and not m.group(1).startswith("_"):
                        labels.append(m.group(1))
            except Exception:
                continue
        return {"labels": labels}

    @app.get("/api/script/files")
    async def api_script_files(config: RenPyConfig = Depends(get_config)):
        if not config.project_path:
            raise HTTPException(status_code=400, detail="No project set")

        game_dir = config.project_path / "game"
        files = []
        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            try:
                rel = str(rpy_file.relative_to(game_dir)).replace("\\", "/")
                if rel.startswith("tl/") or rel.startswith("_mcp") or rel == "testcases.rpy":
                    continue
                files.append(rel)
            except Exception:
                continue
        return {"files": files}

    @app.get("/api/script/parse")
    async def api_script_parse(file: str = Query(...), config: RenPyConfig = Depends(get_config)):
        if not config.project_path:
            raise HTTPException(status_code=400, detail="No project set")

        game_dir = config.project_path / "game"
        filepath = game_dir / file
        try:
            filepath.resolve().relative_to(game_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid file path")

        if not filepath.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {file}")

        try:
            text = filepath.read_text(encoding="utf-8-sig")
            lines = text.splitlines()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        blocks = _parse_script_blocks(lines)
        return {"file": file, "line_count": len(lines), "blocks": blocks}

    @app.get("/api/characters")
    async def api_characters(config: RenPyConfig = Depends(get_config)):
        if not config.project_path:
            raise HTTPException(status_code=400, detail="No project set")

        game_dir = config.project_path / "game"
        char_re = re.compile(
            r'^\s*define\s+(\w+)\s*=\s*Character\s*\(\s*(?:_\()?\s*["\']([^"\']*)["\']'
        )
        characters = []
        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            try:
                rel = str(rpy_file.relative_to(game_dir)).replace("\\", "/")
                if rel.startswith("tl/") or rel.startswith("_mcp"):
                    continue
                for line in rpy_file.read_text(encoding="utf-8").splitlines():
                    m = char_re.match(line)
                    if m:
                        characters.append({"id": m.group(1), "name": m.group(2)})
            except Exception:
                continue
        return {"characters": characters}

    @app.post("/api/script/save")
    async def api_script_save(request: Request, config: RenPyConfig = Depends(get_config)):
        body = await request.json()
        file_rel = body.get("file", "")
        edits = body.get("edits", [])
        if not file_rel or not edits:
            raise HTTPException(status_code=400, detail="Missing 'file' or 'edits'")

        if not config.project_path:
            raise HTTPException(status_code=400, detail="No project set")

        game_dir = config.project_path / "game"
        filepath = game_dir / file_rel
        try:
            filepath.resolve().relative_to(game_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid file path")

        if not filepath.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {file_rel}")

        try:
            lines = filepath.read_text(encoding="utf-8-sig").splitlines()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        sorted_edits = sorted(edits, key=lambda e: e["line_start"], reverse=True)
        for edit in sorted_edits:
            start = edit["line_start"] - 1
            end = edit["line_end"]
            new_lines = edit.get("new_lines", [])
            lines[start:end] = new_lines

        filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")
        blocks = _parse_script_blocks(lines)
        return {"success": True, "blocks": blocks, "line_count": len(lines)}

    @app.get("/api/assets")
    async def api_assets(config: RenPyConfig = Depends(get_config)):
        if not config.project_path:
            raise HTTPException(status_code=400, detail="No project set")

        game_dir = config.project_path / "game"
        refs = set()
        ref_locations: dict[str, list[str]] = {}
        patterns = [
            re.compile(r'^\s*(?:scene|show|hide)\s+(.+?)(?:\s+(?:with|at|behind|onlayer|as|zorder)\s|$|:)'),
            re.compile(r'^\s*(?:play|queue)\s+(?:music|sound|audio|voice)\s+["\']([^"\']+)["\']'),
            re.compile(r'["\']([^"\']*\.(?:png|jpg|jpeg|webp|gif|opus|ogg|mp3|wav|webm|mp4))["\']'),
        ]
        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            if rpy_file.name.startswith("_mcp"):
                continue
            try:
                rel = str(rpy_file.relative_to(game_dir)).replace("\\", "/")
                for i, line in enumerate(rpy_file.read_text(encoding="utf-8").splitlines()):
                    if line.strip().startswith("#"):
                        continue
                    for pat in patterns:
                        for m in pat.finditer(line):
                            ref = m.group(1).strip().lower()
                            refs.add(ref)
                            refs.add(ref.replace("/", " "))
                            loc = f"{rel}:{i+1}"
                            ref_locations.setdefault(ref, []).append(loc)
            except Exception:
                continue

        screen_w, screen_h = 1280, 720
        for cfg in ["gui.rpy", "options.rpy"]:
            p = game_dir / cfg
            if p.exists():
                try:
                    t = p.read_text(encoding="utf-8")
                    wm = re.search(r'config\.screen_width\s*=\s*(\d+)', t)
                    hm = re.search(r'config\.screen_height\s*=\s*(\d+)', t)
                    if wm:
                        screen_w = int(wm.group(1))
                    if hm:
                        screen_h = int(hm.group(1))
                except Exception:
                    pass

        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif"}
        AUDIO_EXTS = {".opus", ".ogg", ".mp3", ".wav", ".flac", ".aac"}
        VIDEO_EXTS = {".webm", ".mp4", ".avi", ".ogv", ".mkv"}
        ALL_EXTS = IMAGE_EXTS | AUDIO_EXTS | VIDEO_EXTS

        assets = []
        for f in sorted(game_dir.rglob("*")):
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            if ext not in ALL_EXTS:
                continue
            rel = str(f.relative_to(game_dir)).replace("\\", "/")
            if rel.startswith(("cache/", "tl/", "saves/", "_mcp")):
                continue

            category = "image" if ext in IMAGE_EXTS else "audio" if ext in AUDIO_EXTS else "video"
            name = f.stem.lower()
            size_kb = round(f.stat().st_size / 1024, 1)

            is_gui = rel.startswith("gui/")
            is_used = is_gui or any(
                name in r or r in name or rel.lower() in r or f.name.lower() in r
                for r in refs if len(r) > 2
            )

            usage = []
            for r in refs:
                if name in r or r in name or rel.lower() == r:
                    usage.extend(ref_locations.get(r, []))

            entry = {
                "path": rel,
                "name": f.stem,
                "ext": ext,
                "category": category,
                "size_kb": size_kb,
                "is_used": is_used,
                "is_gui": is_gui,
                "usage": list(set(usage))[:10],
            }

            if category == "image":
                try:
                    with open(f, "rb") as fh:
                        header = fh.read(32)
                        w, h = None, None
                        if header[:8] == b'\x89PNG\r\n\x1a\n' and len(header) >= 24:
                            w = struct.unpack('>I', header[16:20])[0]
                            h = struct.unpack('>I', header[20:24])[0]
                        elif header[:4] == b'RIFF' and header[8:12] == b'WEBP' and header[12:16] == b'VP8 ' and len(header) >= 30:
                            w = struct.unpack('<H', header[26:28])[0] & 0x3FFF
                            h = struct.unpack('<H', header[28:30])[0] & 0x3FFF
                        if w and h:
                            entry["width"] = w
                            entry["height"] = h
                            if w > screen_w * 2 or h > screen_h * 2:
                                entry["size_warning"] = "oversized"
                except Exception:
                    pass

            assets.append(entry)

        summary = {
            "total": len(assets),
            "images": sum(1 for a in assets if a["category"] == "image"),
            "audio": sum(1 for a in assets if a["category"] == "audio"),
            "video": sum(1 for a in assets if a["category"] == "video"),
            "unused": sum(1 for a in assets if not a["is_used"] and not a["is_gui"]),
            "total_size_kb": round(sum(a["size_kb"] for a in assets), 1),
            "screen_resolution": f"{screen_w}x{screen_h}",
        }
        return {"summary": summary, "assets": assets}

    @app.get("/api/asset-usage")
    async def api_asset_usage(name: str = Query(...), config: RenPyConfig = Depends(get_config)):
        if not config.project_path:
            raise HTTPException(status_code=400, detail="No project set")

        game_dir = config.project_path / "game"
        locations = []
        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            if rpy_file.name.startswith("_mcp"):
                continue
            try:
                rel = str(rpy_file.relative_to(game_dir)).replace("\\", "/")
                for i, line in enumerate(rpy_file.read_text(encoding="utf-8").splitlines()):
                    if name in line.lower():
                        locations.append({"file": rel, "line": i + 1, "text": line.strip()[:120]})
            except Exception:
                continue
        return {"name": name, "locations": locations[:50]}

    @app.get("/api/projects/{project_name}/asset-file/{file_path:path}")
    async def api_project_asset_file(project_name: str, file_path: str):
        project_dir = resolve_project_dir(project_name)
        if not project_dir:
            raise HTTPException(status_code=404, detail="Project not found")

        file_rel = unquote(file_path)
        game_dir = project_dir / "game"
        filepath = game_dir / file_rel
        try:
            filepath.resolve().relative_to(game_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Forbidden")

        if not filepath.exists() or not filepath.is_file():
            raise HTTPException(status_code=404, detail="Not found")

        ext = filepath.suffix.lower()
        mime_types = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
            ".avif": "image/avif",
            ".opus": "audio/opus", ".ogg": "audio/ogg", ".mp3": "audio/mpeg",
            ".wav": "audio/wav", ".flac": "audio/flac", ".aac": "audio/aac",
            ".webm": "video/webm", ".mp4": "video/mp4",
        }
        content_type = mime_types.get(ext, "application/octet-stream")
        data = filepath.read_bytes()
        return Response(content=data, media_type=content_type, headers={"Cache-Control": "public, max-age=300"})

    # Dashboard static assets (React build output)
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")

    # Chat WebSocket
    from .chat_ws import router as chat_router
    app.include_router(chat_router)

    # Static files fallback
    # Mount MCP SSE endpoint so Dashboard/CLI can connect via HTTP
    from ..server import mcp
    app.mount("/mcp", mcp.sse_app())

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app
