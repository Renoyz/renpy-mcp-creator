"""Shared fixtures for Playwright E2E tests."""

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


@pytest.fixture(scope="session")
def server_url():
    """Start the RenPy MCP HTTP server and yield its base URL."""
    port = 8080
    # Ensure a clean workspace for E2E
    workspace = Path.home() / ".renpy-mcp" / "workspace"
    env = os.environ.copy()
    env["RENPY_MCP_WORKSPACE"] = str(workspace)

    cmd = [sys.executable, "-m", "renpy_mcp.main", "--transport", "http", "--port", str(port)]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(Path(__file__).parent.parent.parent),
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
