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


def test_dashboard_chat_generate_build(
    page: Page,
    server_url: str,
    mock_chat_server_url: str,
) -> None:
    """UI smoke test: a project-bound chat request reaches confirmation and can be cancelled."""
    assert wait_for_server(server_url), "Server not ready"
    install_mock_chat_socket(page, mock_chat_server_url)

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
    confirm_pending_action(page, timeout=10000, approve=False)

    expect(page.locator("text=Mock generation cancelled.")).to_be_visible(timeout=10000)


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

    expect(page.locator("img[alt='Generated asset']")).to_be_visible(timeout=10000)
    expect(page.locator("text=Background generated")).to_be_visible(timeout=10000)
    img_src = page.locator("img[alt='Generated asset']").get_attribute("src")
    assert "/api/projects/" in img_src
    assert project_name in img_src
    expect(page.locator("text=tool start")).to_have_count(0)
    expect(page.locator("text=tool result")).to_have_count(0)

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

    # Stop preview server via the browser session so the current-project cookie is included.
    stop_result = page.evaluate(
        """
        async () => {
          const response = await fetch("/api/projects/preview/stop", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({})
          });
          return { ok: response.ok, payload: await response.json() };
        }
        """
    )
    assert stop_result["ok"] is True


def test_workspace_build_status_survives_refresh(page: Page, server_url: str) -> None:
    """Build success status and preview availability should survive page refresh."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_refresh_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    build_button = page.locator("button", has_text=re.compile("Build|Building"))
    expect(build_button).to_be_visible(timeout=10000)
    build_button.click()

    expect(build_button).not_to_contain_text("Building", timeout=30000)
    status_locator = page.locator("div.rounded-md.p-3")
    expect(status_locator).to_be_visible(timeout=10000)
    status_text = status_locator.text_content() or ""
    assert "Build" in status_text or "Built" in status_text or "succeeded" in status_text
    assert "Preview available" in status_text

    # Refresh page
    page.reload()
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Build status message should still appear
    refreshed_status = page.locator("div.rounded-md.p-3")
    expect(refreshed_status).to_be_visible(timeout=10000)
    refreshed_text = refreshed_status.text_content() or ""
    assert "Build" in refreshed_text or "Built" in refreshed_text or "succeeded" in refreshed_text
    assert "Preview available" in refreshed_text

    # Preview should still work after refresh
    preview_button = page.locator("button", has_text=re.compile("Preview|Starting"))
    preview_button.click()
    expect(preview_button).not_to_contain_text("Starting", timeout=30000)
    preview_link = page.locator("a[href*='127.0.0.1']")
    expect(preview_link).to_be_visible(timeout=10000)
    preview_url = preview_link.get_attribute("href") or ""
    assert preview_url.startswith("http://127.0.0.1")

    # Stop preview server to avoid port leaks
    httpx.post(f"{server_url}/api/projects/preview/stop", json={"name": project_name}, timeout=5.0)


def test_chat_history_survives_refresh(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Chat history including image messages should be restored after page refresh."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_chat_hist_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    # Seed persisted chat history directly on disk
    history = {
        "messages": [
            {"role": "user", "content": "generate a courtyard background"},
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Sure, here is the background."}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_1",
                        "content": json.dumps(
                            {
                                "success": True,
                                "image_type": "background",
                                "relative_files": ["game/images/background/courtyard.png"],
                                "preview_urls": [
                                    f"/api/projects/{project_name}/asset-file/images/background/courtyard.png"
                                ],
                                "primary_preview_url": f"/api/projects/{project_name}/asset-file/images/background/courtyard.png",
                            }
                        ),
                        "success": True,
                    }
                ],
            },
            {
                "role": "assistant",
                "content": [{"type": "text", "text": "Done!"}],
            },
        ]
    }
    logs_dir = e2e_workspace / project_name / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "chat-history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")

    # Create a dummy image so the asset-file route returns 200
    image_dir = e2e_workspace / project_name / "game" / "images" / "background"
    image_dir.mkdir(parents=True, exist_ok=True)
    (image_dir / "courtyard.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    open_workspace_from_project_list(page, server_url, project_name)

    # Ensure ProjectContext has loaded the current project before opening drawer
    page.wait_for_selector(f"header span:text-is('{project_name}')", timeout=15000)

    open_chat_drawer(page)

    # Wait for history to be rendered (fetch may complete after drawer opens)
    expect(page.locator("text=generate a courtyard background")).to_be_visible(timeout=10000)
    expect(page.locator("text=Sure, here is the background.")).to_be_visible(timeout=10000)
    expect(page.locator("text=Done!")).to_be_visible(timeout=10000)

    # Verify image restored
    img = page.locator("img[alt='Generated asset']")
    expect(img).to_be_visible(timeout=10000)
    img_src = img.get_attribute("src") or ""
    assert project_name in img_src

    # Refresh and verify again
    page.reload()
    open_chat_drawer(page)
    expect(page.locator("text=generate a courtyard background")).to_be_visible(timeout=10000)
    expect(page.locator("text=Done!")).to_be_visible(timeout=10000)
    expect(img).to_be_visible(timeout=10000)


def test_chat_history_does_not_leak_on_project_switch(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Switching projects must not briefly show the previous project's history or be overwritten by a stale response."""
    assert wait_for_server(server_url), "Server not ready"

    project_a = f"switch_a_{int(time.time())}"
    project_b = f"switch_b_{int(time.time())}"
    for name in (project_a, project_b):
        create_project_via_api(server_url, name)
        logs_dir = e2e_workspace / name / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "chat-history.json").write_text(
            json.dumps({"messages": [{"role": "user", "content": f"msg_for_{name}"}]}),
            encoding="utf-8",
        )

    pending_routes: list = []

    def _handle_route(route, request):
        url = request.url
        if f"/api/projects/{project_a}/chat/history" in url:
            # Hold the request open to simulate a slow in-flight response
            pending_routes.append(route)
        elif f"/api/projects/{project_b}/chat/history" in url:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"messages": [{"role": "user", "content": f"msg_for_{project_b}"}]}),
            )
        else:
            route.continue_()

    page.route("**/api/projects/*/chat/history", _handle_route)

    # Open project A workspace and chat drawer (triggers a held request)
    open_workspace_from_project_list(page, server_url, project_a)
    page.wait_for_selector(f"header span:text-is('{project_a}')", timeout=15000)
    open_chat_drawer(page)

    # Immediately switch to project B before the held response arrives
    page.goto(f"{server_url}/dashboard/projects/{project_b}")
    page.wait_for_selector(f"header span:text-is('{project_b}')", timeout=15000)
    open_chat_drawer(page)

    # Project B's fast history should appear
    expect(page.locator(f"text=msg_for_{project_b}")).to_be_visible(timeout=10000)

    # Project A's message must not be visible (even though its request is still in-flight)
    expect(page.locator(f"text=msg_for_{project_a}")).to_have_count(0, timeout=5000)

    # Now release the held request for project A and let it "arrive"
    for r in pending_routes:
        r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"messages": [{"role": "user", "content": f"msg_for_{project_a}"}]}),
        )

    # After the stale response arrives, project A's message must still not appear
    page.wait_for_timeout(500)
    expect(page.locator(f"text=msg_for_{project_b}")).to_be_visible(timeout=5000)
    expect(page.locator(f"text=msg_for_{project_a}")).to_have_count(0, timeout=5000)
