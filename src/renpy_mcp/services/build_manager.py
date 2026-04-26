"""Handles building Ren'Py projects into deployable targets."""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import Settings
from ..models import BuildRequest, BuildResult

logger = logging.getLogger(__name__)


class BuildManager:
    """Coordinate build jobs using the configured Ren'Py toolchain."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def build(self, request: BuildRequest) -> BuildResult:
        """Execute a build request."""
        project_dir = self.settings.workspace / request.project_name
        if not project_dir.exists():
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=False,
                error=f"Project '{request.project_name}' not found in {self.settings.workspace}",
            )

        toolchain = self._resolve_toolchain()
        if toolchain is None:
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=False,
                error=self._toolchain_error(),
            )

        return await toolchain.build(project_dir, request)

    def _resolve_toolchain(self) -> Optional["LocalRenpyToolchain"]:
        """Return an available toolchain implementation."""
        if self.settings.renpy_sdk_path:
            local = LocalRenpyToolchain(self.settings.renpy_sdk_path)
            if local.available:
                return local
        return None

    def _toolchain_error(self) -> str:
        """Return a helpful message when no toolchain is available."""
        base = "No usable Ren'Py SDK found."
        if self.settings.renpy_sdk_path:
            return f"{base} Checked {self.settings.renpy_sdk_path}, but could not locate 'renpy.sh'."
        return f"{base} Set the RENPY_SDK_PATH environment variable to an extracted Ren'Py SDK."


class LocalRenpyToolchain:
    """Use a locally installed Ren'Py SDK to build projects."""

    def __init__(self, sdk_path: Path) -> None:
        self.sdk_path = sdk_path
        self.executable = self._find_executable()
        self.web_support_available = (self.sdk_path / "web").exists()

    @property
    def available(self) -> bool:
        return self.executable is not None

    async def build(self, project_dir: Path, request: BuildRequest) -> BuildResult:
        if not self.available:
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=False,
                error=f"Ren'Py executable not found under {self.sdk_path}",
            )

        if request.target != "web":
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=False,
                error=f"Unsupported build target '{request.target}'. Only 'web' is currently implemented.",
            )

        if not self.web_support_available:
            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=False,
                error=(
                    "Ren'Py Web support is not installed. "
                    "Open the Ren'Py launcher and download web support, "
                    "or place the 'web' directory inside the SDK path."
                ),
            )

        build_dest = project_dir.parent / f"{project_dir.name}-dists"
        log_dir = project_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        log_file = log_dir / f"build-{request.target}-{timestamp}.log"

        env = self._build_env()
        destination = str(build_dest.resolve())
        command = self._build_command(project_dir, destination, request.force_rebuild)

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(self.sdk_path),
            env=env,
        )

        await self._stream_log(process, log_file)

        returncode = await process.wait()
        success = returncode == 0

        if success:
            project_name = project_dir.name
            web_zip = build_dest / f"{project_name}-web.zip"
            zip_files = list(build_dest.glob("*-web.zip"))
            if zip_files:
                web_zip = zip_files[0]

            output_path = None

            if web_zip.exists():
                web_dir = build_dest / f"{project_name}-web"

                if web_dir.exists():
                    shutil.rmtree(web_dir)

                try:
                    with zipfile.ZipFile(web_zip, "r") as zip_ref:
                        zip_ref.extractall(web_dir)

                    if await self._create_web_player(web_dir, project_name):
                        game_zip = web_dir / "game.zip"
                        with zipfile.ZipFile(game_zip, "w", zipfile.ZIP_DEFLATED) as zf:
                            exclude_files = {
                                "index.html",
                                "index.html.symbols",
                                "manifest.json",
                                "renpy-pre.js",
                                "renpy.data",
                                "renpy.js",
                                "renpy.wasm",
                                "service-worker.js",
                                "web-icon.png",
                                "web-presplash.jpg",
                            }

                            for file_path in web_dir.rglob("*"):
                                if file_path.is_file() and file_path.name not in exclude_files:
                                    if file_path == game_zip:
                                        continue
                                    arcname = file_path.relative_to(web_dir)
                                    zf.write(file_path, arcname)
                        output_path = web_dir
                    else:
                        output_path = web_dir
                except Exception:
                    output_path = web_zip
            else:
                web_dir = build_dest / f"{project_name}-web"
                if web_dir.exists():
                    output_path = web_dir

            return BuildResult(
                project_name=request.project_name,
                target=request.target,
                success=True,
                output_path=output_path,
                log_path=log_file,
            )

        error_message = f"Ren'Py exited with status {returncode}"
        if log_file.exists():
            error_message += f". See log at {log_file}"
        # Surface Ren'Py compiler errors (e.g. duplicate labels) so they
        # aren't buried behind a misleading "Invalid window" symptom.
        errors_txt = project_dir / "errors.txt"
        if errors_txt.exists():
            try:
                error_lines = await asyncio.to_thread(
                    lambda: errors_txt.read_text(encoding="utf-8").strip().splitlines()
                )
                # Include the first 20 lines — enough to show the root cause
                preview = "\n".join(error_lines[:20])
                if len(error_lines) > 20:
                    preview += f"\n... ({len(error_lines) - 20} more lines)"
                error_message += f"\nRen'Py errors.txt:\n{preview}"
            except Exception:
                logger.warning("Failed to read errors.txt for project %s", request.project_name, exc_info=True)
        return BuildResult(
            project_name=request.project_name,
            target=request.target,
            success=False,
            log_path=log_file,
            error=error_message,
        )

    def _find_executable(self) -> Optional[Path]:
        if platform.system() == "Darwin":
            for app_name in ["renpy.app", "Ren'Py.app"]:
                bundle = self.sdk_path / app_name / "Contents" / "MacOS" / "renpy"
                if bundle.exists():
                    return bundle.resolve()

        is_windows = platform.system() == "Windows"
        candidates = [
            self.sdk_path / "renpy.exe",
            self.sdk_path / "renpy.sh",
            self.sdk_path / "renpy",
        ] if is_windows else [
            self.sdk_path / "renpy.sh",
            self.sdk_path / "renpy.exe",
            self.sdk_path / "renpy",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return None

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        # Use direct assignment to override any parent-process values.
        # setdefault would silently keep an inherited value that breaks headless build.
        env["SDL_VIDEODRIVER"] = "dummy"
        env["SDL_AUDIODRIVER"] = "dummy"
        env["RENPY_FORCE_SOFTWARE"] = "1"
        env["RENPY_DISABLE_UPDATE"] = "1"
        env["RENPY_DISABLE_JOYSTICK"] = "1"
        # Prevent Ren'Py from attempting to open a window even on compile errors.
        # Without this, a duplicate-label or other parse error can trigger
        # pygame.display.set_mode() which fails headless on Windows pythonw.exe.
        env["RENPY_NO_DISPLAY"] = "1"
        return env

    async def _create_web_player(self, web_dir: Path, project_name: str) -> bool:
        """Copy web runtime files from SDK and create a proper web player."""
        web_runtime = self.sdk_path / "web"
        if not web_runtime.exists():
            return False

        for item in web_runtime.iterdir():
            if item.name == "index.html":
                html_content = await asyncio.to_thread(
                    lambda: item.read_text(encoding="utf-8")
                )
                html_content = html_content.replace("%%TITLE%%", project_name)
                await asyncio.to_thread(
                    lambda: (web_dir / "index.html").write_text(html_content, encoding="utf-8")
                )
            elif item.name not in {"hash.txt"}:
                dest = web_dir / item.name
                if item.is_file():
                    shutil.copy2(item, dest)
                elif item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)

        return True

    def _build_command(
        self, project_dir: Path, destination: str, force_rebuild: bool
    ) -> list[str]:
        launcher_path = self.sdk_path / "launcher"
        command = [str(self.executable), str(launcher_path.resolve()), "distribute"]
        command.extend(["--package", "web"])
        command.extend(["--destination", str(destination)])
        command.append(str(project_dir.resolve()))
        return command

    async def _stream_log(
        self,
        process: asyncio.subprocess.Process,
        log_file: Path,
    ) -> None:
        if process.stdout is None:
            return

        with log_file.open("wb") as log_handle:
            while True:
                chunk = await process.stdout.readline()
                if not chunk:
                    break
                log_handle.write(chunk)
                log_handle.flush()
