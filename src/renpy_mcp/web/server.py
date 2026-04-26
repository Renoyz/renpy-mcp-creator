"""Lightweight HTTP server for visual UI features (story map, dashboard, etc.)."""

import ast
import base64
import json
import logging
import re
import socket
import threading
import time
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from ..bridge import BridgeClient
from ..config import RenPyConfig

STATIC_DIR = Path(__file__).parent / "static"
logger = logging.getLogger(__name__)

# Singleton server instance
_server: HTTPServer | None = None
_server_port: int = 0
_server_lock = threading.Lock()
_bridge_write_lock = threading.Lock()
_bridge_client: BridgeClient | None = None


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Handler(SimpleHTTPRequestHandler):
    """HTTP handler with API endpoints and static file serving."""

    config: RenPyConfig  # set via class factory

    def log_message(self, format, *args):
        pass  # suppress logs

    def do_GET(self):
        if self.path == "/":
            self._redirect("/dashboard")
        elif self.path == "/story-map":
            self._serve_static("story_map.html", "text/html")
        elif self.path == "/dashboard":
            self._serve_static("dashboard.html", "text/html")
        elif self.path == "/script-editor":
            self._serve_static("script_editor.html", "text/html")
        elif self.path == "/api/graph":
            self._api_graph()
        elif self.path == "/api/status":
            self._api_status()
        elif self.path == "/api/state":
            self._api_state()
        elif self.path == "/api/screenshot":
            self._api_screenshot()
        elif self.path == "/api/labels":
            self._api_labels()
        elif self.path == "/api/script/files":
            self._api_script_files()
        elif self.path.startswith("/api/script/parse?"):
            self._api_script_parse()
        elif self.path == "/api/characters":
            self._api_characters()
        elif self.path == "/heatmap":
            self._serve_static("heatmap.html", "text/html")
        elif self.path == "/assets":
            self._serve_static("asset_manager.html", "text/html")
        elif self.path == "/api/tracking/data":
            self._api_tracking_data()
        elif self.path == "/api/assets":
            self._api_assets()
        elif self.path.startswith("/api/asset-usage?"):
            self._api_asset_usage()
        elif self.path.startswith("/api/asset-file/"):
            self._api_asset_file()
        elif self.path.startswith("/static/"):
            name = self.path[len("/static/"):]
            self._serve_static(name)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if self.path == "/api/jump":
            self._api_jump()
        elif self.path == "/api/eval":
            self._api_eval()
        elif self.path == "/api/notify":
            self._api_notify()
        elif self.path == "/api/variable":
            self._api_set_variable()
        elif self.path == "/api/script/save":
            self._api_script_save()
        elif self.path == "/api/tracking/start":
            self._api_tracking_start()
        elif self.path == "/api/tracking/stop":
            self._api_tracking_stop()
        elif self.path == "/api/tracking/clear":
            self._api_tracking_clear()
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def _redirect(self, location: str):
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.end_headers()

    def _json_response(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, filename: str, content_type: str | None = None):
        filepath = STATIC_DIR / filename
        if not filepath.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = filepath.read_bytes()
        if content_type is None:
            ext = filepath.suffix.lower()
            content_type = {
                ".html": "text/html",
                ".js": "application/javascript",
                ".css": "text/css",
                ".json": "application/json",
            }.get(ext, "application/octet-stream")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # ---- API endpoints ----

    def _api_graph(self):
        config = self.config
        if not config.project_path:
            self._json_response({"error": "No project set"}, 400)
            return

        game_dir = config.project_path / "game"
        label_re = re.compile(r'^label\s+(\w+)(?:\s*\(.*\))?\s*:')

        # Parse scripts
        scripts: dict[str, list[str]] = {}
        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            try:
                rel = str(rpy_file.relative_to(game_dir))
                if rel.startswith("tl") or rel.startswith("_mcp") or rel == "testcases.rpy":
                    continue
                scripts[rel] = rpy_file.read_text(encoding="utf-8").splitlines()
            except Exception:
                logger.warning("Failed to read script: %s", rpy_file, exc_info=True)
                continue

        # Extract labels
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

            # Second pass: connections and content
            current_label = None
            in_menu = False
            menu_indent = 0
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
                        target = stripped[5:].strip()
                        labels[current_label]["jumps_to"].append(target)
                    elif stripped.startswith("call "):
                        target = stripped[5:].strip().split()[0]
                        labels[current_label]["jumps_to"].append(f"call:{target}")
                    elif stripped == "return":
                        labels[current_label]["has_return"] = True
                    elif stripped.startswith("menu"):
                        labels[current_label]["has_menu"] = True
                        in_menu = True
                        menu_indent = len(line) - len(line.lstrip())
                    elif in_menu and stripped.endswith('":') and '"' in stripped:
                        # Menu choice text
                        choice_match = re.search(r'"([^"]*)"', stripped)
                        if choice_match:
                            labels[current_label]["menu_choices"].append(choice_match.group(1))
                    elif dialogue_re.match(line):
                        labels[current_label]["dialogue_count"] += 1

        # Build called_by
        for label_name, info in labels.items():
            for target in info["jumps_to"]:
                clean = target.replace("call:", "")
                if clean in labels:
                    labels[clean]["called_by"].append(label_name)

        # Build nodes and edges for D3
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

        self._json_response({"nodes": nodes, "edges": edges})

    def _api_status(self):
        config = self.config
        if not config.project_path:
            self._json_response({"connected": False, "error": "No project set"})
            return

        status_file = config.project_path / "game" / "_mcp" / "status.json"
        if status_file.exists():
            try:
                data = json.loads(status_file.read_text(encoding="utf-8"))
                age = time.time() - data.get("time", 0)
                self._json_response({"connected": age < 5, "age": age})
                return
            except Exception:
                logger.warning("Failed to read bridge status", exc_info=True)
        self._json_response({"connected": False})

    def _api_jump(self):
        body = self._read_json_body()
        if body is None:
            return
        label = body.get("label", "")
        if not label:
            self._json_response({"error": "Missing 'label'"}, 400)
            return
        result = self._send_bridge_command({"action": "jump", "label": label})
        self._json_response(result)

    # ---- Bridge IPC helper ----

    def _get_bridge_client(self) -> BridgeClient:
        global _bridge_client
        if _bridge_client is None:
            _bridge_client = BridgeClient(
                self.config.project_path,
                write_lock=_bridge_write_lock,
            )
        return _bridge_client

    def _send_bridge_command(self, cmd: dict, timeout: float = 5.0) -> dict:
        """Send a command via file-based IPC and wait for response."""
        if not self.config.project_path:
            return {"success": False, "error": "No project set"}
        return self._get_bridge_client().send_command_sync(cmd, timeout)

    # ---- Dashboard API endpoints ----

    def _api_state(self):
        result = self._send_bridge_command({"action": "get_state"})
        self._json_response(result)

    def _api_screenshot(self):
        result = self._send_bridge_command({"action": "screenshot"}, timeout=10.0)
        if result.get("success"):
            screenshot_path = Path(result.get("path", ""))
            if screenshot_path.exists():
                data = screenshot_path.read_bytes()
                encoded = base64.b64encode(data).decode("ascii")
                self._json_response({"success": True, "image": encoded})
                return
        self._json_response({"success": False, "error": result.get("error", "Screenshot failed")})

    def _api_eval(self):
        body = self._read_json_body()
        if body is None:
            return
        expression = body.get("expression", "")
        if not expression:
            self._json_response({"error": "Missing 'expression'"}, 400)
            return
        result = self._send_bridge_command({"action": "eval", "expression": expression})
        self._json_response(result)

    def _api_notify(self):
        body = self._read_json_body()
        if body is None:
            return
        message = body.get("message", "")
        if not message:
            self._json_response({"error": "Missing 'message'"}, 400)
            return
        result = self._send_bridge_command({"action": "notify", "message": message})
        self._json_response(result)

    def _api_set_variable(self):
        body = self._read_json_body()
        if body is None:
            return
        name = body.get("name", "")
        value = body.get("value", "")
        if not name:
            self._json_response({"error": "Missing 'name'"}, 400)
            return
        if not name.isidentifier():
            self._json_response({"error": f"Invalid variable name: {name}"}, 400)
            return
        result = self._send_bridge_command({
            "action": "set_variable", "name": name, "value": value,
        })
        self._json_response(result)

    def _api_labels(self):
        """Return a list of all label names for the jump dropdown."""
        config = self.config
        if not config.project_path:
            self._json_response({"error": "No project set"}, 400)
            return
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
                logger.warning("Failed to parse labels from: %s", rpy_file, exc_info=True)
                continue
        self._json_response({"labels": labels})

    # ---- Script Editor API ----

    def _api_script_files(self):
        """List .rpy files in the project (excluding tl/, _mcp, testcases)."""
        config = self.config
        if not config.project_path:
            self._json_response({"error": "No project set"}, 400)
            return
        game_dir = config.project_path / "game"
        files = []
        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            try:
                rel = str(rpy_file.relative_to(game_dir)).replace("\\", "/")
                if rel.startswith("tl/") or rel.startswith("_mcp") or rel == "testcases.rpy":
                    continue
                files.append(rel)
            except Exception:
                logger.warning("Failed to list rpy file: %s", rpy_file, exc_info=True)
                continue
        self._json_response({"files": files})

    def _api_script_parse(self):
        """Parse a .rpy file into structured blocks."""
        config = self.config
        if not config.project_path:
            self._json_response({"error": "No project set"}, 400)
            return

        # Extract file param from query string
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        file_rel = qs.get("file", [""])[0]
        if not file_rel:
            self._json_response({"error": "Missing 'file' parameter"}, 400)
            return

        game_dir = config.project_path / "game"
        filepath = game_dir / file_rel
        # Security: ensure path is within game_dir
        try:
            filepath.resolve().relative_to(game_dir.resolve())
        except ValueError:
            self._json_response({"error": "Invalid file path"}, 400)
            return

        if not filepath.exists():
            self._json_response({"error": f"File not found: {file_rel}"}, 404)
            return

        try:
            text = filepath.read_text(encoding="utf-8-sig")
            lines = text.splitlines()
        except Exception as e:
            self._json_response({"error": str(e)}, 500)
            return

        blocks = _parse_script_blocks(lines)
        self._json_response({"file": file_rel, "line_count": len(lines), "blocks": blocks})

    def _api_characters(self):
        """Return character definitions for the editor dropdowns."""
        config = self.config
        if not config.project_path:
            self._json_response({"error": "No project set"}, 400)
            return
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
                logger.warning("Failed to extract characters from: %s", rpy_file, exc_info=True)
                continue
        self._json_response({"characters": characters})

    def _api_script_save(self):
        """Save edits to a .rpy file. Accepts line-level replacements."""
        body = self._read_json_body()
        if body is None:
            return

        file_rel = body.get("file", "")
        edits = body.get("edits", [])
        if not file_rel or not edits:
            self._json_response({"error": "Missing 'file' or 'edits'"}, 400)
            return

        config = self.config
        if not config.project_path:
            self._json_response({"error": "No project set"}, 400)
            return

        game_dir = config.project_path / "game"
        filepath = game_dir / file_rel
        try:
            filepath.resolve().relative_to(game_dir.resolve())
        except ValueError:
            self._json_response({"error": "Invalid file path"}, 400)
            return

        if not filepath.exists():
            self._json_response({"error": f"File not found: {file_rel}"}, 404)
            return

        try:
            lines = filepath.read_text(encoding="utf-8-sig").splitlines()
        except Exception as e:
            self._json_response({"error": str(e)}, 500)
            return

        # Apply edits in reverse order (to preserve line numbers)
        # Each edit: {line_start: int, line_end: int, new_lines: [str]}
        sorted_edits = sorted(edits, key=lambda e: e["line_start"], reverse=True)
        for edit in sorted_edits:
            start = edit["line_start"] - 1  # Convert to 0-based
            end = edit["line_end"]  # exclusive (1-based end = exclusive in 0-based)
            new_lines = edit.get("new_lines", [])
            lines[start:end] = new_lines

        # Write back
        filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Re-parse for updated view
        blocks = _parse_script_blocks(lines)
        self._json_response({"success": True, "blocks": blocks, "line_count": len(lines)})

    # ---- Heatmap / Tracking API ----

    def _api_tracking_data(self):
        """Get tracking data and merge with graph for heatmap overlay."""
        # Quick-check: skip bridge command if no game is connected
        config = self.config
        if config.project_path:
            status_file = config.project_path / "game" / "_mcp" / "status.json"
            try:
                age = time.time() - status_file.stat().st_mtime
                if age > 5:
                    raise FileNotFoundError("stale")
            except (FileNotFoundError, OSError):
                # Bridge not connected - skip the 5s timeout
                data_file = config.project_path / "game" / "_mcp" / "tracking_data.json"
                if data_file.exists():
                    try:
                        saved = json.loads(data_file.read_text(encoding="utf-8"))
                        self._json_response(saved)
                        return
                    except Exception:
                        logger.warning("Failed to read saved tracking data", exc_info=True)
                self._json_response({"active": False, "sessions": [], "stats": {}})
                return
        result = self._send_bridge_command({"action": "get_tracking"})
        if not result.get("success"):
            # Return empty data if bridge not connected (allow offline analysis)
            # Check for saved tracking data
            config = self.config
            if config.project_path:
                data_file = config.project_path / "game" / "_mcp" / "tracking_data.json"
                if data_file.exists():
                    try:
                        saved = json.loads(data_file.read_text(encoding="utf-8"))
                        self._json_response(saved)
                        return
                    except Exception:
                        logger.warning("Failed to read saved tracking data (fallback)", exc_info=True)
            self._json_response({"active": False, "sessions": [], "stats": {}})
            return

        sessions = result.get("sessions", [])
        # Compute aggregate stats
        label_visits: dict[str, int] = {}
        label_time: dict[str, float] = {}
        transitions: dict[str, int] = {}  # "from->to" counts

        for session in sessions:
            events = session.get("events", [])
            for idx, ev in enumerate(events):
                if ev.get("type") == "label":
                    label = ev["label"]
                    label_visits[label] = label_visits.get(label, 0) + 1

                    # Track time spent (to next event or session end)
                    if idx + 1 < len(events):
                        duration = events[idx + 1]["time"] - ev["time"]
                    elif "end_time" in session:
                        duration = session["end_time"] - ev["time"]
                    else:
                        duration = 0
                    label_time[label] = label_time.get(label, 0) + duration

                    # Track transitions
                    if idx > 0 and events[idx - 1].get("type") == "label":
                        prev = events[idx - 1]["label"]
                        key = f"{prev}->{label}"
                        transitions[key] = transitions.get(key, 0) + 1

        stats = {
            "label_visits": label_visits,
            "label_time": {k: round(v, 1) for k, v in label_time.items()},
            "transitions": transitions,
            "session_count": len(sessions),
        }

        # Save tracking data for offline access
        config = self.config
        if config.project_path:
            data_file = config.project_path / "game" / "_mcp" / "tracking_data.json"
            try:
                save_data = {"active": result.get("active", False), "sessions": sessions, "stats": stats}
                data_file.write_text(json.dumps(save_data, ensure_ascii=False), encoding="utf-8")
            except Exception:
                logger.warning("Failed to save tracking data", exc_info=True)

        self._json_response({
            "active": result.get("active", False),
            "sessions": sessions,
            "stats": stats,
        })

    def _api_tracking_start(self):
        result = self._send_bridge_command({"action": "start_tracking"})
        self._json_response(result)

    def _api_tracking_stop(self):
        result = self._send_bridge_command({"action": "stop_tracking"})
        self._json_response(result)

    def _api_tracking_clear(self):
        result = self._send_bridge_command({"action": "clear_tracking"})
        # Also clear saved file
        config = self.config
        if config.project_path:
            data_file = config.project_path / "game" / "_mcp" / "tracking_data.json"
            if data_file.exists():
                try:
                    data_file.unlink()
                except Exception:
                    logger.warning("Failed to remove tracking data file", exc_info=True)
        self._json_response(result)

    # ---- Asset Manager API ----

    _IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif"}
    _AUDIO_EXTS = {".opus", ".ogg", ".mp3", ".wav", ".flac", ".aac"}
    _VIDEO_EXTS = {".webm", ".mp4", ".avi", ".ogv", ".mkv"}
    _ALL_EXTS = _IMAGE_EXTS | _AUDIO_EXTS | _VIDEO_EXTS

    def _api_assets(self):
        """List all assets with metadata, dimensions, and usage status."""
        config = self.config
        if not config.project_path:
            self._json_response({"error": "No project set"}, 400)
            return

        game_dir = config.project_path / "game"

        # Collect references from scripts
        refs = set()
        ref_locations: dict[str, list[str]] = {}
        patterns = [
            re.compile(r'^\s*(?:scene|show|hide)\s+(.+?)(?:\s+(?:with|at|behind|onlayer|as|zorder)\s|$|:)'),
            re.compile(r'^\s*(?:play|queue)\s+(?:music|sound|audio|voice)\s+["\']([^"\']+)["\']'),
            re.compile(r'["\']([^"\']*\.(?:png|jpg|jpeg|webp|gif|opus|ogg|mp3|wav|webm|mp4))["\']'),
        ]
        for rpy_file in game_dir.rglob("*.rpy"):
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
                logger.warning("Failed to extract references from: %s", rpy_file, exc_info=True)
                continue

        # Get screen resolution
        screen_w, screen_h = 1280, 720
        for cfg in ["gui.rpy", "options.rpy"]:
            p = game_dir / cfg
            if p.exists():
                try:
                    t = p.read_text(encoding="utf-8")
                    wm = re.search(r'config\.screen_width\s*=\s*(\d+)', t)
                    hm = re.search(r'config\.screen_height\s*=\s*(\d+)', t)
                    if wm: screen_w = int(wm.group(1))
                    if hm: screen_h = int(hm.group(1))
                except Exception:
                    pass

        # Collect assets
        import struct
        assets = []
        for f in sorted(game_dir.rglob("*")):
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            if ext not in self._ALL_EXTS:
                continue
            rel = str(f.relative_to(game_dir)).replace("\\", "/")
            if rel.startswith(("cache/", "tl/", "saves/", "_mcp")):
                continue

            category = "image" if ext in self._IMAGE_EXTS else "audio" if ext in self._AUDIO_EXTS else "video"
            name = f.stem.lower()
            size_kb = round(f.stat().st_size / 1024, 1)

            # Check usage
            is_gui = rel.startswith("gui/")
            is_used = is_gui or any(
                name in r or r in name or rel.lower() in r or f.name.lower() in r
                for r in refs if len(r) > 2
            )

            # Usage locations
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

            # Get dimensions for images
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
        self._json_response({"summary": summary, "assets": assets})

    def _api_asset_usage(self):
        """Get detailed usage locations for an asset."""
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        name = qs.get("name", [""])[0].lower()
        if not name:
            self._json_response({"error": "Missing 'name'"}, 400)
            return

        config = self.config
        if not config.project_path:
            self._json_response({"error": "No project set"}, 400)
            return

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
                logger.warning("Failed to search name in: %s", rpy_file, exc_info=True)
                continue
        self._json_response({"name": name, "locations": locations[:50]})

    def _api_asset_file(self):
        """Serve an asset file (image/audio) for preview in the browser."""
        config = self.config
        if not config.project_path:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return

        # Extract path after /api/asset-file/
        file_rel = self.path[len("/api/asset-file/"):]
        from urllib.parse import unquote
        file_rel = unquote(file_rel)

        game_dir = config.project_path / "game"
        filepath = game_dir / file_rel
        try:
            filepath.resolve().relative_to(game_dir.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return

        if not filepath.exists() or not filepath.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

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
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> dict | None:
        """Read and parse JSON request body."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(length)) if length else {}
        except (json.JSONDecodeError, ValueError):
            self._json_response({"error": "Invalid JSON"}, 400)
            return None


def _parse_script_blocks(lines: list[str]) -> list[dict]:
    """Parse .rpy lines into structured blocks for the visual editor."""
    blocks = []
    label_re = re.compile(r'^label\s+(\w+)(?:\s*\(.*\))?\s*:')
    define_re = re.compile(r'^\s*define\s+(\w+)\s*=\s*(.*)')
    default_re = re.compile(r'^\s*default\s+(\w+)\s*=\s*(.*)')
    dialogue_re = re.compile(r'^(\s+)(\w+)\s+"(.*)"')
    narration_re = re.compile(r'^(\s+)"(.*)"')
    scene_re = re.compile(r'^(\s+)(scene|show|hide)\s+(.*)')
    with_re = re.compile(r'^(\s+)with\s+(.*)')
    jump_re = re.compile(r'^(\s+)jump\s+(\w+)')
    call_re = re.compile(r'^(\s+)call\s+(\w+)')
    menu_re = re.compile(r'^(\s+)menu\s*:')
    return_re = re.compile(r'^(\s+)return')
    python_re = re.compile(r'^(\s+)\$\s+(.*)')
    if_re = re.compile(r'^(\s+)(if|elif|else)\s*(.*?)\s*:?\s*$')
    play_re = re.compile(r'^(\s+)(play|stop|queue)\s+(music|sound|audio|voice)\s*(.*)')
    comment_re = re.compile(r'^(\s*)#\s*(.*)')
    choice_re = re.compile(r'^(\s+)"(.*)"\s*:')

    i = 0
    n = len(lines)
    current_label = None

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Skip blank lines
        if not stripped:
            i += 1
            continue

        # Top-level comment
        cm = comment_re.match(line)
        if cm and not line.startswith("    "):
            blocks.append({
                "type": "comment", "line_start": i + 1, "line_end": i + 1,
                "text": cm.group(2), "raw": [line],
            })
            i += 1
            continue

        # Define
        dm = define_re.match(line)
        if dm:
            blocks.append({
                "type": "define", "line_start": i + 1, "line_end": i + 1,
                "name": dm.group(1), "value": dm.group(2).strip(), "raw": [line],
            })
            i += 1
            continue

        # Default
        dfm = default_re.match(line)
        if dfm:
            blocks.append({
                "type": "default", "line_start": i + 1, "line_end": i + 1,
                "name": dfm.group(1), "value": dfm.group(2).strip(), "raw": [line],
            })
            i += 1
            continue

        # Label
        lm = label_re.match(stripped)
        if lm:
            current_label = lm.group(1)
            blocks.append({
                "type": "label", "line_start": i + 1, "line_end": i + 1,
                "name": current_label, "raw": [line],
            })
            i += 1
            continue

        # Menu block (collect the whole menu)
        mm = menu_re.match(line)
        if mm:
            menu_start = i
            menu_indent = len(mm.group(1))
            choices = []
            prompt = ""
            i += 1
            while i < n:
                ml = lines[i]
                ms = ml.strip()
                if not ms:
                    i += 1
                    continue
                ml_indent = len(ml) - len(ml.lstrip())
                if ml_indent <= menu_indent and ms:
                    break
                # Check for choice
                cm2 = choice_re.match(ml)
                if cm2:
                    choice_indent = len(cm2.group(1))
                    choice_text = cm2.group(2)
                    choice_body = []
                    i += 1
                    while i < n:
                        cl = lines[i]
                        cs = cl.strip()
                        if not cs:
                            i += 1
                            continue
                        cl_indent = len(cl) - len(cl.lstrip())
                        if cl_indent <= choice_indent:
                            break
                        choice_body.append(cs)
                        i += 1
                    choices.append({"text": choice_text, "body": choice_body})
                else:
                    # Narration prompt before choices
                    nm2 = narration_re.match(ml)
                    if nm2:
                        prompt = nm2.group(2)
                    # Could also be dialogue prompt
                    dm2 = dialogue_re.match(ml)
                    if dm2:
                        prompt = f'{dm2.group(2)} "{dm2.group(3)}"'
                    i += 1
            raw = lines[menu_start:i]
            blocks.append({
                "type": "menu", "line_start": menu_start + 1, "line_end": i,
                "prompt": prompt, "choices": choices, "raw": raw,
            })
            continue

        # Condition block (if/elif/else)
        im = if_re.match(line)
        if im and line.startswith("    "):
            cond_start = i
            cond_indent = len(im.group(1))
            i += 1
            # Consume the body + elif/else
            while i < n:
                cl = lines[i]
                cs = cl.strip()
                if not cs:
                    i += 1
                    continue
                cl_indent = len(cl) - len(cl.lstrip())
                if cl_indent <= cond_indent:
                    # Check if elif/else continuation
                    cim = if_re.match(cl)
                    if cim and cim.group(2) in ("elif", "else") and len(cim.group(1)) == cond_indent:
                        i += 1
                        continue
                    break
                i += 1
            raw = lines[cond_start:i]
            blocks.append({
                "type": "condition", "line_start": cond_start + 1, "line_end": i,
                "condition": im.group(3).rstrip(":").strip(),
                "keyword": im.group(2),
                "raw": raw,
            })
            continue

        # Dialogue
        dlm = dialogue_re.match(line)
        if dlm:
            blocks.append({
                "type": "dialogue", "line_start": i + 1, "line_end": i + 1,
                "character": dlm.group(2), "text": dlm.group(3), "raw": [line],
            })
            i += 1
            continue

        # Narration
        nm = narration_re.match(line)
        if nm and not stripped.endswith(":"):
            blocks.append({
                "type": "narration", "line_start": i + 1, "line_end": i + 1,
                "text": nm.group(2), "raw": [line],
            })
            i += 1
            continue

        # Scene/Show/Hide
        sm = scene_re.match(line)
        if sm:
            # Check for following "with" line
            end = i
            if i + 1 < n and with_re.match(lines[i + 1]):
                end = i + 1
            raw = lines[i:end + 1]
            with_trans = ""
            if end > i:
                wm = with_re.match(lines[end])
                if wm:
                    with_trans = wm.group(2).strip()
            blocks.append({
                "type": sm.group(2), "line_start": i + 1, "line_end": end + 1,
                "target": sm.group(3).strip(),
                "transition": with_trans,
                "raw": raw,
            })
            i = end + 1
            continue

        # Play/Stop/Queue music/sound
        pm = play_re.match(line)
        if pm:
            blocks.append({
                "type": "audio", "line_start": i + 1, "line_end": i + 1,
                "action": pm.group(2), "channel": pm.group(3),
                "target": pm.group(4).strip(), "raw": [line],
            })
            i += 1
            continue

        # Jump
        jm = jump_re.match(line)
        if jm:
            blocks.append({
                "type": "jump", "line_start": i + 1, "line_end": i + 1,
                "target": jm.group(2), "raw": [line],
            })
            i += 1
            continue

        # Call
        clm = call_re.match(line)
        if clm:
            blocks.append({
                "type": "call", "line_start": i + 1, "line_end": i + 1,
                "target": clm.group(2), "raw": [line],
            })
            i += 1
            continue

        # Return
        rm = return_re.match(line)
        if rm:
            blocks.append({
                "type": "return", "line_start": i + 1, "line_end": i + 1,
                "raw": [line],
            })
            i += 1
            continue

        # Python line
        pym = python_re.match(line)
        if pym:
            blocks.append({
                "type": "python", "line_start": i + 1, "line_end": i + 1,
                "code": pym.group(2), "raw": [line],
            })
            i += 1
            continue

        # Inline comment
        if stripped.startswith("#"):
            blocks.append({
                "type": "comment", "line_start": i + 1, "line_end": i + 1,
                "text": stripped[1:].strip(), "raw": [line],
            })
            i += 1
            continue

        # Fallback: unknown
        blocks.append({
            "type": "other", "line_start": i + 1, "line_end": i + 1,
            "text": stripped, "raw": [line],
        })
        i += 1

    return blocks


def _make_handler(config: RenPyConfig):
    """Create a handler class bound to a specific config."""
    handler = type("BoundHandler", (_Handler,), {"config": config})
    return handler


def start_server(config: RenPyConfig) -> int:
    """Start the web server (if not already running) and return the port."""
    global _server, _server_port

    with _server_lock:
        if _server is not None:
            return _server_port

        port = _find_free_port()
        handler = _make_handler(config)
        server = HTTPServer(("127.0.0.1", port), handler)

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        _server = server
        _server_port = port
        return port


def start_web(config: RenPyConfig, path: str = "/story-map") -> str:
    """Start server and return the URL."""
    port = start_server(config)
    return f"http://127.0.0.1:{port}{path}"
