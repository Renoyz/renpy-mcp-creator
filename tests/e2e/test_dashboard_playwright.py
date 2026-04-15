"""Playwright E2E: Dashboard chat -> generate background -> build web."""

import json
import time
from pathlib import Path

import httpx
from playwright.sync_api import Page, expect


def wait_for_server(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{url}/api/status", timeout=2.0).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def test_dashboard_chat_generate_build(page: Page, server_url: str) -> None:
    """End-to-end test through Dashboard UI."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_e2e_{int(time.time())}"

    # ------------------------------------------------------------------
    # 1. Open Dashboard
    # ------------------------------------------------------------------
    page.goto(f"{server_url}/dashboard")
    expect(page.locator("text=项目列表")).to_be_visible(timeout=10000)

    # ------------------------------------------------------------------
    # 2. Create project
    # ------------------------------------------------------------------
    page.locator("button:has-text('新建项目')").click()
    page.locator("div:has-text('项目名称') >> input").fill(project_name)
    page.locator("button:has-text('创建')").click()
    expect(page.locator(f"h4:has-text('{project_name}')")).to_be_visible(timeout=10000)

    # ------------------------------------------------------------------
    # 3. Open AI chat drawer
    # ------------------------------------------------------------------
    page.locator("button:has-text('AI 助手')").click()
    # Wait for green connection dot (title="Connected")
    page.locator("[title='Connected']").wait_for(state="visible", timeout=15000)

    # ------------------------------------------------------------------
    # 4. Send natural-language request
    # ------------------------------------------------------------------
    prompt = (
        f"Create a visual novel project named {project_name}, "
        "generate a background of a Japanese courtyard with cherry blossoms, "
        "anime soft pastel style, then build the web version"
    )
    page.locator("textarea[placeholder='输入消息...']").fill(prompt)
    page.locator("button:has([d*='M4.5 4.5l9 4.5'])") \
        .or_(page.locator("button:has(.lucide-send)")) \
        .or_(page.locator("button >> svg")) \
        .nth(-1).click()

    # ------------------------------------------------------------------
    # 5. Handle confirmations (generate_background + build_project)
    # ------------------------------------------------------------------
    for _ in range(2):
        # Wait for confirmation panel
        confirm_btn = page.locator("button:has-text('确认')")
        expect(confirm_btn).to_be_visible(timeout=120000)
        confirm_btn.click()
        # Small pause to let the backend process
        page.wait_for_timeout(500)

    # ------------------------------------------------------------------
    # 6. Wait for build success in chat stream
    # ------------------------------------------------------------------
    # We look for a tool_result or assistant message containing "success"
    success_locator = page.locator("text=success").or_(page.locator("text=成功"))
    expect(success_locator).to_be_visible(timeout=120000)

    # ------------------------------------------------------------------
    # 7. Verify build artifacts via REST API
    # ------------------------------------------------------------------
    build_dir = (
        Path.home()
        / ".renpy-mcp"
        / "workspace"
        / f"{project_name}-dists"
        / f"{project_name}-web"
    )
    assert (build_dir / "index.html").exists(), f"Build output missing at {build_dir}"

    # Also verify via API that the project exists
    resp = httpx.get(f"{server_url}/api/projects")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json().get("projects", [])}
    assert project_name in names
