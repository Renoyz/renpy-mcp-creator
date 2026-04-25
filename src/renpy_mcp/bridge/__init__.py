"""Bridge client for file-based IPC with a running Ren'Py game."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class BridgeClient:
    """Send commands to a running Ren'Py game via file-based IPC.

    Writes cmd.json atomically into game/_mcp/ and polls status.json
    for the response.  Supports both async (live.py) and sync (server.py)
    callers.
    """

    def __init__(
        self,
        project_path: Path,
        write_lock: threading.Lock | None = None,
    ) -> None:
        self._mcp_dir = project_path / "game" / "_mcp"
        self._write_lock = write_lock or threading.Lock()

    # ---- command file writing ------------------------------------------------

    def _write_command(self, cmd: dict) -> Path:
        """Atomically write *cmd* to the bridge command file."""
        self._mcp_dir.mkdir(parents=True, exist_ok=True)
        cmd_file = self._mcp_dir / "cmd.json"
        tmp = self._mcp_dir / "cmd.json.tmp"
        tmp.write_text(json.dumps(cmd, ensure_ascii=False), encoding="utf-8")
        tmp.replace(cmd_file)
        return cmd_file

    # ---- async interface (primary) -------------------------------------------

    async def send_command(self, cmd: dict, timeout: float = 5.0) -> dict:
        """Send a command and poll for the status response."""
        status_file = self._mcp_dir / "status.json"
        start = time.time()
        expected_action = cmd.get("action", "")

        with self._write_lock:
            self._write_command(cmd)

        while time.time() - start < timeout:
            if status_file.exists():
                try:
                    data = json.loads(
                        status_file.read_text(encoding="utf-8")
                    )
                    if (
                        data.get("time", 0) >= start
                        and data.get("action") == expected_action
                    ):
                        return data
                except (json.JSONDecodeError, OSError):
                    logger.warning(
                        "Bridge status file read/decode failed",
                        exc_info=True,
                    )
            await asyncio.sleep(0.2)

        return {
            "success": False,
            "error": "Timeout waiting for game response. Is the game running?",
        }

    # ---- sync interface (for threaded callers) -------------------------------

    def send_command_sync(self, cmd: dict, timeout: float = 5.0) -> dict:
        """Synchronous wrapper for threaded HTTP handlers."""
        status_file = self._mcp_dir / "status.json"
        start = time.time()
        expected_action = cmd.get("action", "")

        with self._write_lock:
            self._write_command(cmd)

        while time.time() - start < timeout:
            if status_file.exists():
                try:
                    data = json.loads(
                        status_file.read_text(encoding="utf-8")
                    )
                    if (
                        data.get("time", 0) >= start
                        and data.get("action") == expected_action
                    ):
                        return data
                except (json.JSONDecodeError, OSError):
                    logger.warning(
                        "Bridge status file read/decode failed",
                        exc_info=True,
                    )
            time.sleep(0.2)

        return {
            "success": False,
            "error": "Timeout waiting for game response. Is the game running?",
        }
