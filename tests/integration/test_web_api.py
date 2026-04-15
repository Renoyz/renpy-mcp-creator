"""Integration tests for web server API endpoints."""

import json
from pathlib import Path

import pytest

from renpy_mcp.config import RenPyConfig
from renpy_mcp.web.server import start_server, _find_free_port, _make_handler


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a minimal Ren'Py project structure."""
    project_dir = tmp_path / "web_test_vn"
    game_dir = project_dir / "game"
    game_dir.mkdir(parents=True)
    (game_dir / "script.rpy").write_text(
        'label start:\n    scene bg room\n    "Hello."\n    return\n',
        encoding="utf-8",
    )
    return project_dir


@pytest.fixture
def test_config(temp_project: Path) -> RenPyConfig:
    """Provide a config pointing to the temp project."""
    return RenPyConfig(sdk_path=Path("."), project_path=temp_project)


def test_find_free_port():
    """_find_free_port should return an available TCP port."""
    port = _find_free_port()
    assert isinstance(port, int)
    assert 1024 <= port <= 65535


def test_handler_factory(test_config: RenPyConfig):
    """_make_handler should bind config to the HTTP handler class."""
    handler = _make_handler(test_config)
    assert handler.config is test_config


class TestWebServerLifecycle:
    """Tests for server start/stop."""

    def test_start_server_returns_port(self, test_config: RenPyConfig):
        """start_server should return a valid port and be idempotent."""
        import renpy_mcp.web.server as web_server

        # Reset singleton to ensure fresh start
        web_server._server = None
        web_server._server_port = 0

        port1 = start_server(test_config)
        assert isinstance(port1, int)
        assert port1 > 0

        port2 = start_server(test_config)
        assert port2 == port1

        # Clean up
        if web_server._server:
            web_server._server.shutdown()
            web_server._server = None


class TestWebApiEndpoints:
    """Tests for actual HTTP responses."""

    @pytest.fixture
    def server_port(self, test_config: RenPyConfig):
        """Start the server once for the class."""
        import renpy_mcp.web.server as web_server

        web_server._server = None
        web_server._server_port = 0
        port = start_server(test_config)
        yield port
        if web_server._server:
            web_server._server.shutdown()
            web_server._server = None

    def test_api_graph(self, server_port: int, temp_project: Path):
        """GET /api/graph should return nodes and edges."""
        import urllib.request

        url = f"http://127.0.0.1:{server_port}/api/graph"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "nodes" in data
            assert "edges" in data
            assert any(n["id"] == "start" for n in data["nodes"])

    def test_api_status_no_bridge(self, server_port: int):
        """GET /api/status should report disconnected when bridge is absent."""
        import urllib.request

        url = f"http://127.0.0.1:{server_port}/api/status"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("connected") is False

    def test_api_labels(self, server_port: int):
        """GET /api/labels should return label list."""
        import urllib.request

        url = f"http://127.0.0.1:{server_port}/api/labels"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "labels" in data
            assert "start" in data["labels"]

    def test_api_script_files(self, server_port: int):
        """GET /api/script/files should list .rpy files."""
        import urllib.request

        url = f"http://127.0.0.1:{server_port}/api/script/files"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert "files" in data
            assert "script.rpy" in data["files"]
