"""Execute RenPy CLI commands."""

import asyncio
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .config import RenPyConfig

_executor = ThreadPoolExecutor(max_workers=2)

# On Windows, prevent child processes from inheriting console/handles
_SUBPROCESS_FLAGS: dict = {}
if sys.platform == "win32":
    _SUBPROCESS_FLAGS["creationflags"] = (
        subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    )


class RenPyRunner:
    """Wrapper for executing RenPy CLI commands."""

    def __init__(self, config: RenPyConfig):
        self.config = config

    def _run_sync(
        self,
        *args: str,
        project_path: Path | None = None,
        timeout: float = 60.0,
    ) -> subprocess.CompletedProcess[str]:
        """Run a RenPy CLI command synchronously (called from thread pool)."""
        project = project_path or self.config.project_path
        if not project:
            raise ValueError("No project path configured. Set project_path first.")

        cmd = [str(self.config.renpy_exe), str(project), *args]

        # Use clean environment to avoid MCP stdio interference
        env = os.environ.copy()

        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env=env,
            **_SUBPROCESS_FLAGS,
        )

        return subprocess.CompletedProcess(
            args=cmd,
            returncode=result.returncode,
            stdout=result.stdout.decode("utf-8", errors="replace"),
            stderr=result.stderr.decode("utf-8", errors="replace"),
        )

    async def run_command(
        self,
        *args: str,
        project_path: Path | None = None,
        timeout: float = 60.0,
    ) -> subprocess.CompletedProcess[str]:
        """Run a RenPy CLI command asynchronously via thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            lambda: self._run_sync(*args, project_path=project_path, timeout=timeout),
        )

    async def lint(self, project_path: Path | None = None) -> str:
        """Run RenPy lint on a project."""
        result = await self.run_command("lint", project_path=project_path)
        return result.stdout + result.stderr

    async def compile(self, project_path: Path | None = None) -> str:
        """Compile RenPy scripts."""
        result = await self.run_command("compile", project_path=project_path)
        return result.stdout + result.stderr

    async def json_dump(self, project_path: Path | None = None) -> Path:
        """Dump project metadata to JSON.

        Uses lint command combined with --json-dump to avoid opening
        a display window.
        """
        project = project_path or self.config.project_path
        if not project:
            raise ValueError("No project path configured.")
        output_file = project / "game" / "dump.json"
        await self.run_command(
            "--json-dump", str(output_file), "lint",
            project_path=project,
        )
        return output_file

    async def run_test(
        self,
        testcase: str | None = None,
        project_path: Path | None = None,
        timeout: float = 120.0,
    ) -> str:
        """Run RenPy test cases."""
        args = ["test"]
        if testcase:
            args.append(testcase)
        result = await self.run_command(*args, project_path=project_path, timeout=timeout)
        return result.stdout + result.stderr

    async def launch(
        self,
        warp_to: str | None = None,
        project_path: Path | None = None,
    ) -> str:
        """Launch the game, optionally warping to a specific line.

        Args:
            warp_to: Warp spec like "script.rpy:42".
        """
        args: list[str] = []
        if warp_to:
            args.extend(["--warp", warp_to])
        result = await self.run_command(*args, project_path=project_path, timeout=120.0)
        return result.stdout + result.stderr
