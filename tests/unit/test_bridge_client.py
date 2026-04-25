"""Tests for unified BridgeClient — file-based IPC to the running Ren'Py game."""

import asyncio
import json
from pathlib import Path

import pytest

from renpy_mcp.bridge import BridgeClient


class TestBridgeClientAtomicWrite:
    """BridgeClient must atomically write command files using replace(),
    never unlink() followed by rename()."""

    def test_command_write_uses_replace_not_unlink_rename(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Atomic write must not unlink the target before writing."""
        client = BridgeClient(tmp_path)
        cmd = {"action": "jump", "label": "start"}

        unlinked_files: list[str] = []
        original_unlink = Path.unlink

        def _track_unlink(self):
            unlinked_files.append(str(self))
            return original_unlink(self)

        monkeypatch.setattr(Path, "unlink", _track_unlink)

        client._write_command(cmd)

        assert len(unlinked_files) == 0, (
            f"BridgeClient._write_command must not unlink() cmd.json, "
            f"use replace() instead. Unlinked: {unlinked_files}"
        )


class TestBridgeClientAsyncSendCommand:
    """Async send_command must write cmd.json, poll status.json, and return result."""

    @pytest.mark.asyncio
    async def test_send_command_returns_status_response(self, tmp_path: Path):
        client = BridgeClient(tmp_path)
        mcp_dir = tmp_path / "game" / "_mcp"
        mcp_dir.mkdir(parents=True)

        # Pre-write a status response that will be found on first poll
        status_file = mcp_dir / "status.json"
        status_file.write_text(json.dumps({
            "success": True,
            "action": "jump",
            "time": 9999999999.0,
        }), encoding="utf-8")

        result = await client.send_command({"action": "jump", "label": "start"})

        assert result["success"] is True
        assert result["action"] == "jump"

        # Verify cmd.json was written atomically
        cmd_file = mcp_dir / "cmd.json"
        assert cmd_file.exists()
        cmd_data = json.loads(cmd_file.read_text(encoding="utf-8"))
        assert cmd_data["action"] == "jump"
        assert cmd_data["label"] == "start"

    @pytest.mark.asyncio
    async def test_send_command_times_out_when_no_status(self, tmp_path: Path):
        client = BridgeClient(tmp_path)

        # No status.json exists — should time out
        result = await client.send_command(
            {"action": "jump", "label": "start"}, timeout=0.1
        )

        assert result["success"] is False
        assert "error" in result
        assert "Timeout" in result["error"]


class TestBridgeClientSyncSendCommand:
    """Sync wrapper must work for threaded callers (server.py)."""

    def test_send_command_sync_writes_command_and_returns_status(
        self, tmp_path: Path
    ):
        client = BridgeClient(tmp_path)
        mcp_dir = tmp_path / "game" / "_mcp"
        mcp_dir.mkdir(parents=True)

        # Pre-write a status response
        status_file = mcp_dir / "status.json"
        status_file.write_text(json.dumps({
            "success": True,
            "action": "get_state",
            "time": 9999999999.0,
        }), encoding="utf-8")

        result = client.send_command_sync({"action": "get_state"})

        assert result["success"] is True
        assert result["action"] == "get_state"
