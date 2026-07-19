"""Preview server lifecycle: app shutdown must not orphan preview subprocesses.

Covers two guarantees:
1. FastAPI shutdown stops every server tracked by the shared PreviewManager.
2. The HTTP routes and the MCP preview tools use the SAME shared manager,
   so the shutdown hook covers previews started through either entry point.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import renpy_mcp.web.fastapi_app as fa
from renpy_mcp.config import RenPyConfig, get_settings
from renpy_mcp.services.preview_manager import get_shared_preview_manager


class _SpyManager:
    def __init__(self) -> None:
        self.stop_all_calls = 0

    async def stop_all(self) -> None:
        self.stop_all_calls += 1


def test_app_shutdown_stops_shared_preview_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "workspace", tmp_path)
    fa.set_config(RenPyConfig(sdk_path=Path("."), project_path=tmp_path))

    spy = _SpyManager()
    monkeypatch.setattr(fa, "_preview_manager", spy)

    app = fa.create_app()
    with TestClient(app):
        pass

    assert spy.stop_all_calls == 1


def test_fastapi_preview_manager_is_the_shared_instance() -> None:
    assert fa._preview_manager is get_shared_preview_manager()


class _FakeMcp:
    def __init__(self) -> None:
        self._tool_manager = type("TM", (), {"_tools": {}})()
        self.tools: dict = {}

    def tool(self):
        def deco(fn):
            self.tools[fn.__name__] = fn
            return fn

        return deco


async def test_register_preview_tools_uses_shared_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from renpy_mcp.tools import preview as tools_preview

    stopped: list[str] = []

    class _FakeManager:
        async def stop(self, project_name: str) -> bool:
            stopped.append(project_name)
            return True

    fake = _FakeManager()
    monkeypatch.setattr(
        tools_preview, "get_shared_preview_manager", lambda: fake, raising=False
    )

    mcp = _FakeMcp()
    tools_preview.register_preview_tools(mcp, config=None, runner=None)  # type: ignore[arg-type]

    await mcp.tools["stop_web_preview"]("proj_x")

    assert stopped == ["proj_x"]
