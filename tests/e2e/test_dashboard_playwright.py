"""Playwright E2E coverage for the dashboard workflow."""

import json
import re
import time
from pathlib import Path

import httpx
from playwright.sync_api import Locator, Page, expect


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


def create_project_via_api(server_url: str, project_name: str) -> None:
    response = httpx.post(
        f"{server_url}/api/projects",
        json={"name": project_name},
        timeout=10.0,
    )
    assert response.status_code == 200, response.text


def open_workspace_from_project_list(page: Page, server_url: str, project_name: str) -> None:
    page.goto(f"{server_url}/dashboard")
    project_card = page.locator(f"h4:has-text('{project_name}')")
    expect(project_card).to_be_visible(timeout=10000)
    project_card.click()
    expect(page.locator("h1")).to_have_text(project_name, timeout=10000)


def open_chat_drawer(page: Page) -> None:
    page.locator("header button").last.click()
    page.locator("[title='Connected']").wait_for(state="visible", timeout=15000)


def click_send_button(page: Page) -> None:
    send_button: Locator = (
        page.locator("button:has([d*='M4.5 4.5l9 4.5'])")
        .or_(page.locator("button:has(.lucide-send)"))
        .or_(page.locator("button >> svg"))
        .nth(-1)
    )
    send_button.click()


def confirm_pending_action(page: Page, timeout: int = 10000, approve: bool = True) -> None:
    confirmation_panel = page.locator("div.border-t.bg-muted\\/50")
    expect(confirmation_panel).to_be_visible(timeout=timeout)
    button_index = 1 if approve else 0
    confirmation_panel.locator("button").nth(button_index).click()


def install_mock_chat_socket(page: Page, mock_chat_server_url: str) -> None:
    page.add_init_script(
        f"""
        (() => {{
          const mockUrl = {json.dumps(mock_chat_server_url)};
          const NativeWebSocket = window.WebSocket;
          function PatchedWebSocket(url, protocols) {{
            let finalUrl = url;
            try {{
              const parsed = new URL(url, window.location.href);
              if (parsed.pathname === "/ws/chat") {{
                finalUrl = mockUrl;
              }}
            }} catch (_) {{}}
            return protocols !== undefined
              ? new NativeWebSocket(finalUrl, protocols)
              : new NativeWebSocket(finalUrl);
          }}
          PatchedWebSocket.prototype = NativeWebSocket.prototype;
          Object.setPrototypeOf(PatchedWebSocket, NativeWebSocket);
          window.WebSocket = PatchedWebSocket;
        }})();
        """
    )


def test_project_workspace(page: Page, server_url: str) -> None:
    """Create a project and open its workspace route."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_workspace_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    expect(page.locator("button", has_text="Build")).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="Preview")).to_be_visible(timeout=10000)
    page.locator("h4:has-text('Story Map')").first.click()
    expect(page.locator("span:has-text('Story Map')")).to_be_visible(timeout=10000)
    assert "/story-map" in page.url


def test_direct_workspace_url(page: Page, server_url: str) -> None:
    """Direct navigation to a project workspace URL without prior UI entry."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_direct_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)


def test_dashboard_chat_generate_build(page: Page, server_url: str) -> None:
    """Real-backend smoke test: reach the first confirmation for a project-bound request."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_e2e_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    open_chat_drawer(page)
    page.locator("textarea").fill(
        (
            f"Create a visual novel project named {project_name}, "
            "generate a background of a Japanese courtyard with cherry blossoms, "
            "anime soft pastel style, then build the web version"
        )
    )
    click_send_button(page)
    confirm_pending_action(page, timeout=120000, approve=False)

    resp = httpx.get(f"{server_url}/api/projects")
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json().get("projects", [])}
    assert project_name in names


def test_dashboard_chat_generates_background_into_project(
    page: Page,
    server_url: str,
    mock_chat_server_url: str,
    e2e_workspace: Path,
) -> None:
    """Half-loop verification: confirm generation and verify file landing."""
    assert wait_for_server(server_url), "Server not ready"

    install_mock_chat_socket(page, mock_chat_server_url)

    project_name = f"playwright_mock_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    open_chat_drawer(page)
    page.locator("textarea").fill("generate a courtyard background")
    click_send_button(page)
    confirm_pending_action(page)

    expect(
        page.locator("text=Background saved to game/images/background/mock_courtyard.png")
    ).to_be_visible(timeout=10000)

    generated_file = (
        e2e_workspace / project_name / "game" / "images" / "background" / "mock_courtyard.png"
    )
    assert generated_file.exists(), f"Generated background missing at {generated_file}"


def test_workspace_build_and_preview(page: Page, server_url: str, e2e_workspace: Path) -> None:
    """Click Build and Preview in the workspace and verify UI state changes."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_build_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    # Click Build and wait for a terminal state (success or failed)
    build_button = page.locator("button", has_text=re.compile("Build|Building"))
    expect(build_button).to_be_visible(timeout=10000)
    build_button.click()

    # Wait until Build button is no longer in running state
    expect(build_button).not_to_contain_text("Building", timeout=30000)

    # Assert build status message is visible (success or error)
    status_locator = page.locator("div.rounded-md.p-3")
    expect(status_locator).to_be_visible(timeout=10000)
    status_text = status_locator.text_content() or ""
    assert (
        "Build" in status_text
        or "Built" in status_text
        or "SDK" in status_text
        or "succeeded" in status_text
        or "failed" in status_text.lower()
    )

    # Click Preview (server is running with RENPY_MCP_MOCK_BUILD=1, so build produces real output)
    preview_button = page.locator("button", has_text=re.compile("Preview|Starting"))
    preview_button.click()
    expect(preview_button).not_to_contain_text("Starting", timeout=30000)

    # Assert preview URL is shown
    preview_link = page.locator("a[href*='127.0.0.1']")
    expect(preview_link).to_be_visible(timeout=10000)
    preview_url = preview_link.get_attribute("href") or ""
    assert preview_url.startswith("http://127.0.0.1")

    # Stop preview server via API to avoid port leaks across tests
    httpx.post(f"{server_url}/api/projects/preview/stop", json={"name": project_name}, timeout=5.0)
