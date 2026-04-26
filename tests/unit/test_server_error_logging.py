"""TDD: verify server.py logs warnings on I/O failures."""
import json
import logging
import time
from pathlib import Path

import pytest


class FakeConfig:
    project_path = Path("/tmp/fake_project")


def test_graph_logs_warning_on_script_read_failure(caplog, monkeypatch, tmp_path):
    """When script read fails during graph building, logger.warning is emitted."""
    from renpy_mcp.web.server import _Handler

    handler = _Handler.__new__(_Handler)
    handler.config = type("C", (), {"project_path": tmp_path})()

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    (game_dir / "test.rpy").write_text("label start:\n    return\n")

    original_read_text = Path.read_text

    def failing_read_text(self, *args, **kwargs):
        if str(self).endswith(".rpy"):
            raise OSError("disk full")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr("pathlib.Path.read_text", failing_read_text)
    monkeypatch.setattr(handler, "_json_response", lambda *a, **kw: None)

    with caplog.at_level(logging.WARNING):
        handler._api_graph()

    assert any("Failed to read script" in r.message for r in caplog.records), (
        "Expected warning for script read failure"
    )


def test_status_logs_warning_on_json_decode_error(caplog, monkeypatch, tmp_path):
    """When bridge status.json is corrupt, logger.warning is emitted."""
    from renpy_mcp.web.server import _Handler

    handler = _Handler.__new__(_Handler)
    handler.config = type("C", (), {"project_path": tmp_path})()

    status_dir = tmp_path / "game" / "_mcp"
    status_dir.mkdir(parents=True)
    (status_dir / "status.json").write_text("not json{{{", encoding="utf-8")

    monkeypatch.setattr(handler, "_json_response", lambda *a, **kw: None)

    with caplog.at_level(logging.WARNING):
        handler._api_status()

    assert any("status" in r.message.lower() for r in caplog.records), (
        "Expected warning for corrupt status.json"
    )


def test_tracking_clear_logs_warning_on_unlink_failure(caplog, monkeypatch, tmp_path):
    """When tracking data unlink fails, logger.warning is emitted."""
    from renpy_mcp.web.server import _Handler

    handler = _Handler.__new__(_Handler)
    handler.config = type("C", (), {"project_path": tmp_path})()

    data_file = tmp_path / "game" / "_mcp" / "tracking_data.json"
    data_file.parent.mkdir(parents=True)
    data_file.write_text("{}")

    original_unlink = Path.unlink

    def failing_unlink(self, *args, **kwargs):
        if "tracking_data.json" in str(self):
            raise OSError("permission denied")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr("pathlib.Path.unlink", failing_unlink)
    monkeypatch.setattr(handler, "_send_bridge_command", lambda *a, **kw: {"success": True})
    monkeypatch.setattr(handler, "_json_response", lambda *a, **kw: None)

    with caplog.at_level(logging.WARNING):
        handler._api_tracking_clear()

    assert any("tracking" in r.message.lower() for r in caplog.records), (
        "Expected warning for tracking unlink failure"
    )


def test_tracking_data_logs_warning_on_parse_failure(caplog, tmp_path):
    """When saved tracking data cannot be parsed, warning is emitted and a response is returned."""
    from renpy_mcp.web.server import _Handler

    handler = _Handler.__new__(_Handler)
    handler.config = type("C", (), {"project_path": tmp_path})()

    mcp_dir = tmp_path / "game" / "_mcp"
    mcp_dir.mkdir(parents=True)
    status_file = mcp_dir / "status.json"
    status_file.write_text("{}", encoding="utf-8")

    # Force stale status so the handler uses the offline tracking file path.
    import os
    os.utime(status_file, (0, 0))

    tracking_file = mcp_dir / "tracking_data.json"
    tracking_file.write_text("{bad json", encoding="utf-8")

    monkeypatched_payload = {}

    def fake_json_response(data, status: int = 200):
        monkeypatched_payload["data"] = data
        monkeypatched_payload["status"] = status

    import types
    handler._json_response = types.MethodType(
        lambda self, data, status=200: fake_json_response(data, status),
        handler,
    )

    with caplog.at_level(logging.WARNING):
        handler._api_tracking_data()

    assert "data" in monkeypatched_payload
    assert any("Failed to read saved tracking data" in rec.message for rec in caplog.records), (
        "Expected warning for invalid tracking data JSON"
    )
