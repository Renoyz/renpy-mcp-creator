"""Script, asset, and legacy analysis routes."""

import json
import logging
import re
import struct
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from ...config import RenPyConfig, resolve_project_dir
from ..fastapi_app import get_config
from ..server import _parse_script_blocks

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/graph")
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
            logger.warning(
                "Failed to read script file %s",
                rpy_file.name,
                exc_info=True,
            )
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


@router.get("/api/status")
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
            logger.warning("Failed to parse bridge status", exc_info=True)
            pass
    return {"connected": False}


@router.get("/api/labels")
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
            logger.warning(
                "Failed to parse labels from %s",
                rpy_file.name,
                exc_info=True,
            )
            continue
    return {"labels": labels}


@router.get("/api/script/files")
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
            logger.warning(
                "Failed to list script file %s",
                rpy_file.name,
                exc_info=True,
            )
            continue
    return {"files": files}


@router.get("/api/script/parse")
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


@router.get("/api/characters")
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
            logger.warning(
                "Failed to parse characters from %s",
                rpy_file.name,
                exc_info=True,
            )
            continue
    return {"characters": characters}


@router.post("/api/script/save")
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


@router.get("/api/assets")
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
            logger.warning(
                "Failed to parse asset references from %s",
                rpy_file.name,
                exc_info=True,
            )
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
                logger.warning(
                    "Failed to parse screen dimensions from %s",
                    cfg,
                    exc_info=True,
                )
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
                logger.warning(
                    "Failed to read image dimensions for %s",
                    f.name,
                    exc_info=True,
                )
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


@router.get("/api/asset-usage")
async def api_asset_usage(name: str = Query(...), config: RenPyConfig = Depends(get_config)):
    if not config.project_path:
        raise HTTPException(status_code=400, detail="No project set")

    game_dir = config.project_path / "game"
    results = []
    name_lower = name.strip().lower()
    for rpy_file in sorted(game_dir.rglob("*.rpy")):
        try:
            rel = str(rpy_file.relative_to(game_dir)).replace("\\", "/")
            if rel.startswith("tl/") or rel.startswith("_mcp"):
                continue
            for i, line in enumerate(rpy_file.read_text(encoding="utf-8").splitlines()):
                if name_lower in line.lower():
                    results.append({"file": rel, "line": i + 1, "text": line.strip()})
        except Exception:
            logger.warning(
                "Failed to search asset usage in %s",
                rpy_file.name,
                exc_info=True,
            )
            continue
    return {"name": name, "usages": results}


@router.get("/api/projects/{project_name}/asset-file/{file_path:path}")
async def api_project_asset_file(project_name: str, file_path: str):
    from urllib.parse import unquote

    project_dir = resolve_project_dir(project_name)
    if not project_dir:
        raise HTTPException(status_code=404, detail="Project not found")

    game_dir = project_dir / "game"
    decoded = unquote(file_path)
    filepath = game_dir / decoded
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
