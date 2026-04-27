"""Playwright E2E: Intake chat with malformed LLM JSON auto-repairs and flows to freeze."""

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


def start_malformed_mock_llm_server(workspace: Path) -> tuple[str, subprocess.Popen]:
    """Start a mock LLM backend that returns JSON with trailing commas."""
    port = _find_free_port()
    env = os.environ.copy()
    env["RENPY_MCP_WORKSPACE"] = str(workspace)
    env["RENPY_MCP_MOCK_BUILD"] = "1"
    env["RENPY_MCP_MOCK_LLM"] = "1"
    env["RENPY_MCP_MOCK_LLM_MALFORMED_JSON"] = "1"

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
        raise RuntimeError(f"Mock LLM backend did not start on {url}")

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
    raise RuntimeError(f"Mock LLM backend did not become ready on {url}")


@pytest.fixture
def malformed_mock_llm_server_url(e2e_workspace: Path):
    url, proc = start_malformed_mock_llm_server(e2e_workspace)
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_intake_malformed_json_auto_repair_promotes_to_brief_review(
    page: Page,
    malformed_mock_llm_server_url: str,
    e2e_workspace: Path,
) -> None:
    """Malformed mock LLM JSON should be auto-repaired into a promotable Brief draft."""
    server_url = malformed_mock_llm_server_url
    project_name = f"pw_repair_{int(time.time())}"

    # --- Step 1: Create project by clicking "新建项目" on the UI ---
    page.goto(f"{server_url}/dashboard/projects")
    expect(page.locator("h1")).to_be_visible(timeout=30000)

    # Click "新建项目" button (top-right)
    create_btn = page.locator("button", has_text="新建项目")
    expect(create_btn).to_be_visible(timeout=10000)
    create_btn.click()

    # Dialog should appear
    dialog = page.locator("[data-testid='create-project-dialog']")
    expect(dialog).to_be_visible(timeout=10000)

    # Fill project name
    name_input = page.locator("[data-testid='create-project-name-input']")
    expect(name_input).to_be_visible(timeout=5000)
    name_input.fill(project_name)

    # Click submit
    submit_btn = page.locator("[data-testid='create-project-submit']")
    expect(submit_btn).to_be_visible(timeout=5000)
    submit_btn.click()

    # Wait for workspace to load (project name as h1)
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # --- Step 2: Open chat and start intake ---
    chat_panel = page.locator("[data-testid='chat-panel-docked']")
    chat_drawer = page.locator("[data-testid='chat-drawer']")
    if chat_panel.count() > 0:
        expect(chat_panel).to_be_visible(timeout=10000)
        chat = chat_panel
    else:
        expect(chat_drawer).to_be_visible(timeout=10000)
        chat = chat_drawer

    page.locator("[title='Connected']").wait_for(state="visible", timeout=15000)

    # Turn 0: start intake
    page.locator("textarea").fill("start_refinement_intake")
    page.locator("button >> svg").last.click()
    expect(chat.locator("text=Project Brief")).to_be_visible(timeout=15000)

    # Turn 1: collecting
    page.locator("textarea").fill("3章，西方玄幻，屠龙勇士")
    page.locator("button >> svg").last.click()

    # Must NOT show JSON parse error
    expect(chat.locator("text=Blueprint generation failed")).to_have_count(0, timeout=10000)
    expect(chat.locator("text=JSON parse error")).to_have_count(0, timeout=10000)

    # Should show brief draft ready message after backend repairs malformed mock JSON.
    expect(chat.locator("text=Enter Brief Review").first).to_be_visible(timeout=15000)

    # --- Step 3: Enter Brief Review ---
    intake_tab = page.get_by_role("button", name="Intake", exact=True)
    expect(intake_tab).to_be_visible(timeout=5000)
    intake_tab.click()

    enter_brief_btn = page.locator("button", has_text="Enter Brief Review")
    expect(enter_brief_btn).to_be_visible(timeout=10000)
    enter_brief_btn.click()

    # Wait for Brief tab content
    expect(page.locator("text=Core Premise")).to_be_visible(timeout=10000)

    # Verify repaired brief was persisted on disk.
    brief_path = e2e_workspace / project_name / "meta" / "project_brief.json"
    assert brief_path.exists(), "project_brief.json should exist after brief promotion"
