"""Shared fixtures for Playwright E2E tests."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


REPO_ROOT = Path(__file__).parent.parent.parent


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            try:
                sock.connect((host, port))
                return True
            except OSError:
                time.sleep(0.2)
    return False


@pytest.fixture(scope="session")
def e2e_workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Provide an isolated workspace for E2E runs."""
    return tmp_path_factory.mktemp("renpy-mcp-e2e-workspace")


@pytest.fixture(scope="session")
def server_url(e2e_workspace: Path):
    """Start the RenPy MCP HTTP server and yield its base URL."""
    port = _find_free_port()
    env = os.environ.copy()
    env["RENPY_MCP_WORKSPACE"] = str(e2e_workspace)
    env["RENPY_MCP_MOCK_BUILD"] = "1"

    cmd = [sys.executable, "-m", "renpy_mcp.main", "--transport", "http", "--port", str(port)]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(REPO_ROOT),
    )

    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    ready = False
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{url}/api/status", timeout=2.0)
            if resp.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        time.sleep(0.5)

    if not ready:
        proc.terminate()
        proc.kill()
        raise RuntimeError(f"Server did not start on {url}")

    yield url

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


@pytest.fixture(scope="session")
def mock_chat_server_url(e2e_workspace: Path) -> str:
    """Start a deterministic mock chat WebSocket server for E2E tests."""
    host = "127.0.0.1"
    port = _find_free_port()
    env = os.environ.copy()
    env["RENPY_MCP_WORKSPACE"] = str(e2e_workspace)
    env["MOCK_WS_HOST"] = host
    env["MOCK_WS_PORT"] = str(port)

    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "mock_ws_server.py")]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(REPO_ROOT),
    )

    if not _wait_for_port(host, port):
        proc.terminate()
        proc.kill()
        raise RuntimeError(f"Mock WebSocket server did not start on ws://{host}:{port}")

    yield f"ws://{host}:{port}"

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
