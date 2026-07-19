"""Build-status path redaction tests.

Persisted metadata and API payloads must not leak absolute local filesystem
paths (AGENTS.md rule). ``_redact_local_paths`` currently strips the workspace
prefix; it must also strip the configured Ren'Py SDK path, which build error
messages embed (e.g. ``build_manager`` "under {sdk_path}" / launch errors).
"""

from __future__ import annotations

from pathlib import Path

import pytest

import renpy_mcp.web.fastapi_app as fa
from renpy_mcp.config import RenPyConfig, get_settings


@pytest.fixture
def redaction_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    workspace = tmp_path / "workspace"
    sdk_dir = tmp_path / "sdk" / "renpy-8.3.4-sdk"
    workspace.mkdir()
    sdk_dir.mkdir(parents=True)

    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", workspace)
    fa.set_config(RenPyConfig(sdk_path=sdk_dir, project_path=workspace))
    return {"workspace": workspace, "sdk_dir": sdk_dir}


def test_redact_local_paths_strips_sdk_path(redaction_env: dict[str, Path]) -> None:
    sdk_dir = redaction_env["sdk_dir"]
    message = f'Build failed: "..." under {sdk_dir}; also see {sdk_dir.as_posix()}/renpy.exe'

    redacted = fa._redact_local_paths(message)

    assert str(sdk_dir) not in redacted
    assert sdk_dir.as_posix() not in redacted
    assert "<sdk>" in redacted


def test_redact_local_paths_still_strips_workspace(redaction_env: dict[str, Path]) -> None:
    workspace = redaction_env["workspace"]
    log_file = workspace / "proj" / "logs" / "build.log"
    message = f"Failed to write {log_file} ({log_file.as_posix()})"

    redacted = fa._redact_local_paths(message)

    assert str(workspace) not in redacted
    assert workspace.as_posix() not in redacted
    assert "<workspace>" in redacted
