"""Playwright E2E: User creates a project by clicking "新建项目" on the UI."""

import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page, expect

REPO_ROOT = Path(__file__).parent.parent.parent


def _find_free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> bool:
    import socket

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


def start_server(workspace: Path) -> tuple[str, subprocess.Popen]:
    """Start the backend HTTP server for E2E tests."""
    port = _find_free_port()
    env = os.environ.copy()
    env["RENPY_MCP_WORKSPACE"] = str(workspace)
    env["RENPY_MCP_MOCK_BUILD"] = "1"

    cmd = [sys.executable, "-m", "renpy_mcp.main", "--transport", "http", "--port", str(port)]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        cwd=str(REPO_ROOT),
    )

    url = f"http://127.0.0.1:{port}"
    if not _wait_for_port("127.0.0.1", port, timeout=30.0):
        proc.terminate()
        proc.kill()
        raise RuntimeError(f"Backend did not start on {url}")

    deadline = time.time() + 10.0
    while time.time() < deadline:
        try:
            if httpx.get(f"{url}/api/status", timeout=2.0).status_code == 200:
                return url, proc
        except Exception:
            pass
        time.sleep(0.5)

    proc.terminate()
    proc.kill()
    raise RuntimeError(f"Backend did not become ready on {url}")


@pytest.fixture
def server_url(e2e_workspace: Path):
    url, proc = start_server(e2e_workspace)
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_user_creates_project_by_clicking_new_project_button(
    page: Page,
    server_url: str,
    e2e_workspace: Path,
) -> None:
    """A human user opens the project list, clicks the '新建项目' button,
    fills the dialog, submits, and lands on the new project's workspace.
    """
    project_name = f"ui_create_{int(time.time())}"
    screenshots: list[Path] = []

    def _snap(name: str) -> None:
        p = e2e_workspace / f"_screenshot_{name}.png"
        page.screenshot(path=str(p), full_page=True)
        screenshots.append(p)

    # Open project list page
    page.goto(f"{server_url}/dashboard/projects")
    expect(page.locator("h1")).to_be_visible(timeout=30000)
    _snap("01_project_list")

    # Click the "新建项目" button (top-right corner, identified by data-testid)
    new_project_btn = page.locator("[data-testid='new-project-cta']")
    expect(new_project_btn).to_be_visible(timeout=10000)
    new_project_btn.click()
    _snap("02_dialog_opened")

    # The create-project dialog should appear
    dialog = page.locator("[data-testid='create-project-dialog']")
    expect(dialog).to_be_visible(timeout=10000)

    # Fill the project name input
    name_input = page.locator("[data-testid='create-project-name-input']")
    expect(name_input).to_be_visible(timeout=5000)
    name_input.fill(project_name)
    _snap("03_name_filled")

    # Click the submit button
    submit_btn = page.locator("[data-testid='create-project-submit']")
    expect(submit_btn).to_be_visible(timeout=5000)
    expect(submit_btn).to_be_enabled(timeout=5000)
    submit_btn.click()

    # Should navigate to the new project's workspace
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)
    _snap("04_workspace_loaded")

    # Verify the project exists on disk
    project_meta = e2e_workspace / project_name / "meta"
    assert project_meta.exists(), f"Project directory should be created at {project_meta}"

    # Print screenshot paths for inspection
    print("\n=== Screenshots ===")
    for s in screenshots:
        print(f"  {s}")
