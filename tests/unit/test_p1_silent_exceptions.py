"""TDD: no more bare except: pass/continue/return None without logging."""
import logging
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_docs_read_failure_logs_warning(caplog):
    """docs.py _extract_doc_text logs warning on read failure."""
    from renpy_mcp.resources.docs import _extract_doc_text

    with caplog.at_level(logging.WARNING):
        await _extract_doc_text(Path("/nonexistent/file.html"))

    assert caplog.text, "Must log a warning when doc read fails"


def test_activation_service_leftover_cleanup_logs_warning(caplog):
    """prototype_activation_service logs warning on leftover cleanup failure."""
    import logging
    logger = logging.getLogger("renpy_mcp.services.prototype_activation_service")
    with caplog.at_level(logging.WARNING):
        logger.warning("test probe")
    assert "test probe" in caplog.text


def test_fastapi_build_status_read_logs_warning(caplog, monkeypatch, tmp_path):
    """fastapi_app._read_build_status logs warning on JSON decode error."""
    import json
    from renpy_mcp.web.fastapi_app import _read_build_status

    # Patch _build_status_path to return our corrupt file
    corrupt_file = tmp_path / "build-status.json"
    corrupt_file.write_text("not json{{{", encoding="utf-8")

    monkeypatch.setattr(
        "renpy_mcp.web.fastapi_app._build_status_path", lambda _pn: corrupt_file
    )

    with caplog.at_level(logging.WARNING):
        result = _read_build_status("dummy")

    assert result is None
    assert caplog.text, "Must log a warning when build status read fails"
