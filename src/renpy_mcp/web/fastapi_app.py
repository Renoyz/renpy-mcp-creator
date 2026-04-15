"""FastAPI application for unified-design Dashboard and API."""

import json
import re
import struct
import threading
import time
from pathlib import Path
from urllib.parse import unquote

from collections.abc import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from ..config import RenPyConfig, _current_project_path, get_settings, resolve_project_dir
from ..services.project_manager import ProjectManager
from .server import _parse_script_blocks

STATIC_DIR = Path(__file__).parent / "static"
DASHBOARD_DIR = Path(__file__).parent.parent.parent.parent / "dashboard" / "dist"

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


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(title="RenPy MCP Unified Server")
    app.add_middleware(
        SessionMiddleware, secret_key="renpy-mcp-dev-secret-change-in-production"
    )

    # ---- Page routes ----

    @app.get("/")
    async def root():
        return RedirectResponse(url="/dashboard")

    @app.get("/dashboard")
    async def dashboard():
        return FileResponse(DASHBOARD_DIR / "index.html")

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
        projects = [p.model_dump(mode="json") for p in project_manager.list_projects()]
        return {"projects": projects}

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

    @app.get("/api/asset-file/{file_path:path}")
    async def api_asset_file(file_path: str, config: RenPyConfig = Depends(get_config)):
        if not config.project_path:
            raise HTTPException(status_code=400, detail="No project set")

        file_rel = unquote(file_path)
        game_dir = config.project_path / "game"
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
