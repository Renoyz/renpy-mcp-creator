"""Preview and screenshot tools."""

import asyncio
import base64
import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import json

from ..config import RenPyConfig, get_settings
from ..models import BuildRequest
from ..renpy_runner import RenPyRunner
from ..services.build_manager import BuildManager
from ..services.preview_manager import PreviewManager
from ..services.project_manager import ProjectManager

_executor = ThreadPoolExecutor(max_workers=1)

# Max dimension for AI-friendly screenshots (keeps aspect ratio)
_MAX_SCREENSHOT_DIM = 320


def _resize_screenshot(data: bytes, max_dim: int = _MAX_SCREENSHOT_DIM) -> tuple[bytes, str]:
    """Resize screenshot and convert to JPEG for AI-friendly size.

    Returns (image_bytes, mime_type).
    """
    from PIL import Image
    import io

    img = Image.open(io.BytesIO(data))
    img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60)
    return buf.getvalue(), "image/jpeg"


# Injected RenPy script: captures screenshot then quits automatically
_CAPTURE_SCRIPT = """\
init python:
    import os as _mcp_os

    if _mcp_os.environ.get("RENPY_MCP_CAPTURE") == "1":
        _mcp_capture_done = False

        def _mcp_screenshot_callback(*args, **kwargs):
            global _mcp_capture_done
            if _mcp_capture_done:
                return

            import renpy
            iface = renpy.game.interface
            if not getattr(iface, 'surftree', None):
                return

            _mcp_capture_done = True
            target = _mcp_os.path.join(
                renpy.config.gamedir, "_mcp_screenshots", "capture.png"
            )
            _mcp_os.makedirs(_mcp_os.path.dirname(target), exist_ok=True)
            try:
                iface.save_screenshot(target)
                renpy.quit(save=False)
            except Exception:
                _mcp_capture_done = False

        config.interact_callbacks.append(_mcp_screenshot_callback)
"""


def register_preview_tools(mcp, config: RenPyConfig, runner: RenPyRunner):
    """Register preview/screenshot MCP tools."""
    settings = get_settings()
    build_manager = BuildManager(settings)
    preview_manager = PreviewManager()
    project_manager = ProjectManager(settings)

    # Remove legacy build_project from project.py and replace with BuildManager-based version
    try:
        mcp._tool_manager._tools.pop("build_project", None)
    except Exception:
        pass

    @mcp.tool()
    async def build_project(project_name: str, target: str = "web", force_rebuild: bool = False) -> str:
        """Run the build pipeline for a project.

        Compiles a Ren'Py project into a playable web game. All asset management
        (copying images to correct locations) happens automatically.

        Args:
            project_name: Name of the project to build.
            target: Build target ("web" for browser).
            force_rebuild: Clean build from scratch (default: False).
        """
        request = BuildRequest(
            project_name=project_name, target=target, force_rebuild=force_rebuild
        )
        result = await build_manager.build(request)
        return json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False)

    @mcp.tool()
    async def start_web_preview(project_name: str) -> str:
        """Serve the generated web build from a local HTTP server.

        Args:
            project_name: Name of the project.
        """
        build_dir = (
            settings.workspace / f"{project_name}-dists" / f"{project_name}-web"
        )
        if not build_dir.exists():
            return json.dumps(
                {
                    "success": False,
                    "error": f"No web build found for project '{project_name}'. Run build_project first.",
                },
                indent=2,
                ensure_ascii=False,
            )
        if not (build_dir / "index.html").exists():
            return json.dumps(
                {
                    "success": False,
                    "error": f"Web build at {build_dir} is missing index.html. Ensure the build completed successfully.",
                },
                indent=2,
                ensure_ascii=False,
            )

        server = await preview_manager.start(project_name, build_dir)
        return json.dumps(
            {
                "success": True,
                "project": project_name,
                "url": server.url,
                "port": server.port,
            },
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def stop_web_preview(project_name: str) -> str:
        """Stop the local preview server.

        Args:
            project_name: Name of the project.
        """
        stopped = await preview_manager.stop(project_name)
        return json.dumps(
            {"project": project_name, "stopped": stopped},
            indent=2,
            ensure_ascii=False,
        )

    @mcp.tool()
    async def screenshot_scene(
        warp_to: str,
        wait_seconds: float = 10.0,
    ) -> list[dict]:
        """Take a screenshot by warping to a specific script location.

        Launches the game headlessly, warps to the specified line, captures
        a screenshot, then auto-quits. Returns the image for AI inspection.

        Args:
            warp_to: Location to warp to, e.g. "script.rpy:42".
                     Use list_warp_targets to find valid targets.
            wait_seconds: Max seconds to wait for screenshot capture.

        Returns:
            Image content (viewable by AI) or error message.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return [{"type": "text", "text": "Error: No project set. Use set_project first."}]

        game_dir = config.project_path / "game"
        screenshot_dir = game_dir / "_mcp_screenshots"
        screenshot_file = screenshot_dir / "capture.png"
        mcp_script = game_dir / "_mcp_capture.rpy"

        try:
            # Clean previous captures
            if screenshot_dir.exists():
                shutil.rmtree(screenshot_dir, ignore_errors=True)
            screenshot_dir.mkdir(exist_ok=True)

            # Inject capture script
            mcp_script.write_text(_CAPTURE_SCRIPT, encoding="utf-8")

            env = os.environ.copy()
            env["RENPY_MCP_CAPTURE"] = "1"

            cmd = [
                str(config.renpy_exe),
                str(config.project_path),
                "--warp", warp_to,
            ]

            def _run_capture():
                return subprocess.run(
                    cmd,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=wait_seconds,
                    env=env,
                )

            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(_executor, _run_capture)
                stderr = result.stderr
            except subprocess.TimeoutExpired:
                stderr = b""

            if screenshot_file.exists():
                data, mime = _resize_screenshot(screenshot_file.read_bytes())
                encoded = base64.b64encode(data).decode("ascii")
                return [
                    {"type": "text", "text": f"Screenshot captured at {warp_to}"},
                    {
                        "type": "image",
                        "data": encoded,
                        "mimeType": mime,
                    },
                ]
            else:
                error_detail = ""
                if stderr:
                    error_detail = stderr.decode("utf-8", errors="replace")[:500]
                return [{
                    "type": "text",
                    "text": (
                        f"Error: Screenshot not captured for '{warp_to}'.\n"
                        f"The warp target may be invalid or the scene may not render.\n"
                        f"Use list_warp_targets to find valid targets.\n"
                        f"{error_detail}"
                    ),
                }]

        finally:
            if mcp_script.exists():
                mcp_script.unlink()
            # Also clean up compiled version
            rpyc = mcp_script.with_suffix(".rpyc")
            if rpyc.exists():
                rpyc.unlink()
            if screenshot_dir.exists():
                shutil.rmtree(screenshot_dir, ignore_errors=True)

    @mcp.tool()
    async def list_warp_targets() -> str:
        """List available warp targets (labels and scene locations) in the project.

        Returns file:line locations that can be used with screenshot_scene.
        Also shows scene/show statements for visual preview targets.

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        labels = []
        scenes = []

        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            try:
                lines = rpy_file.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue

            rel_path = rpy_file.relative_to(game_dir)
            label_re = re.compile(r'^label\s+(\w+)(?:\s*\(.*\))?\s*:')
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                lm = label_re.match(stripped)
                if lm:
                    label_name = lm.group(1)
                    if not label_name.startswith("_"):
                        labels.append(f"{rel_path}:{i}  # label {label_name}")
                elif stripped.startswith("scene ") and not stripped.startswith("scene black"):
                    scene_name = stripped.split()[1] if len(stripped.split()) > 1 else "?"
                    scenes.append(f"{rel_path}:{i}  # scene {scene_name}")

        parts = []
        if labels:
            parts.append("=== Labels ===\n" + "\n".join(labels))
        if scenes:
            parts.append("=== Scenes ===\n" + "\n".join(scenes))
        return "\n\n".join(parts) if parts else "No warp targets found."

    @mcp.tool()
    async def scene_preview_gallery(max_scenes: int = 10) -> str:
        """Generate a gallery of screenshots from multiple scenes.

        Warps to each scene location and captures a screenshot, creating
        a visual overview of the game's scenes. Returns file paths to
        captured images.

        Args:
            max_scenes: Maximum number of scenes to capture (default 10).

        Requires set_project to be called first.
        """
        if not config.project_path:
            return "Error: No project set. Use set_project first."

        game_dir = config.project_path / "game"
        gallery_dir = game_dir / "_mcp_gallery"
        if gallery_dir.exists():
            shutil.rmtree(gallery_dir, ignore_errors=True)
        gallery_dir.mkdir(exist_ok=True)

        # Find warp targets (scenes and labels)
        targets = []
        for rpy_file in sorted(game_dir.rglob("*.rpy")):
            if rpy_file.name.startswith("_mcp"):
                continue
            try:
                lines = rpy_file.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            rel_path = rpy_file.relative_to(game_dir)
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("scene ") and not stripped.startswith("scene black"):
                    targets.append({
                        "warp": f"{rel_path}:{i}",
                        "description": stripped,
                    })
                    if len(targets) >= max_scenes:
                        break
            if len(targets) >= max_scenes:
                break

        if not targets:
            return "No scene statements found to capture."

        # Capture script that saves to gallery dir
        capture_script = '''\
init python:
    import os as _mcp_os

    if _mcp_os.environ.get("RENPY_MCP_GALLERY") == "1":
        _mcp_gallery_done = False

        def _mcp_gallery_callback(*args, **kwargs):
            global _mcp_gallery_done
            if _mcp_gallery_done:
                return

            import renpy
            iface = renpy.game.interface
            if not getattr(iface, 'surftree', None):
                return

            _mcp_gallery_done = True
            idx = _mcp_os.environ.get("RENPY_MCP_GALLERY_IDX", "0")
            target = _mcp_os.path.join(
                renpy.config.gamedir, "_mcp_gallery", "scene_{}.png".format(idx)
            )
            _mcp_os.makedirs(_mcp_os.path.dirname(target), exist_ok=True)
            try:
                iface.save_screenshot(target)
                renpy.quit(save=False)
            except Exception:
                _mcp_gallery_done = False

        config.interact_callbacks.append(_mcp_gallery_callback)
'''
        mcp_script = game_dir / "_mcp_gallery_capture.rpy"
        results = []

        try:
            mcp_script.write_text(capture_script, encoding="utf-8")

            for idx, target in enumerate(targets):
                env = os.environ.copy()
                env["RENPY_MCP_GALLERY"] = "1"
                env["RENPY_MCP_GALLERY_IDX"] = str(idx)

                cmd = [
                    str(config.renpy_exe),
                    str(config.project_path),
                    "--warp", target["warp"],
                ]

                def _run(cmd=cmd, env=env):
                    return subprocess.run(
                        cmd,
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        timeout=15.0,
                        env=env,
                    )

                loop = asyncio.get_event_loop()
                try:
                    await loop.run_in_executor(_executor, _run)
                except subprocess.TimeoutExpired:
                    pass

                img_path = gallery_dir / f"scene_{idx}.png"
                results.append({
                    "index": idx,
                    "warp_target": target["warp"],
                    "scene": target["description"],
                    "captured": img_path.exists(),
                    "path": str(img_path) if img_path.exists() else None,
                })

        finally:
            if mcp_script.exists():
                mcp_script.unlink()
            rpyc = mcp_script.with_suffix(".rpyc")
            if rpyc.exists():
                rpyc.unlink()

        captured = sum(1 for r in results if r["captured"])
        import json
        return json.dumps({
            "gallery_dir": str(gallery_dir),
            "captured": captured,
            "total": len(results),
            "scenes": results,
        }, indent=2, ensure_ascii=False)
