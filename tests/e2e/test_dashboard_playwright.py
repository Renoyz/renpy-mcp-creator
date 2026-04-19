"""Playwright E2E coverage for the dashboard workflow."""

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import Locator, Page, expect


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


def start_mock_llm_server(workspace: Path) -> tuple[str, subprocess.Popen]:
    """Start a dedicated backend with mock LLM for real WS path tests."""
    port = _find_free_port()
    env = os.environ.copy()
    env["RENPY_MCP_WORKSPACE"] = str(workspace)
    env["RENPY_MCP_MOCK_BUILD"] = "1"
    env["RENPY_MCP_MOCK_LLM"] = "1"

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

    # Also wait for /api/status to return 200
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


def _is_top_level_snapshot_request(url: str) -> bool:
    """Return True for top-level project snapshot endpoints only.

    Matches:
        /api/projects/{name}/meta
        /api/projects/{name}/blueprint
        /api/projects/{name}/scenes
        /api/projects/{name}/storymap

    Does NOT match sub-resources such as:
        /api/projects/{name}/scenes/{id}/script
    """
    return any(url.rstrip("/").endswith(x) for x in ["/meta", "/blueprint", "/scenes", "/storymap"])


def create_project_via_api(server_url: str, project_name: str) -> None:
    response = httpx.post(
        f"{server_url}/api/projects",
        json={"name": project_name},
        timeout=10.0,
    )
    assert response.status_code == 200, response.text


def open_workspace_from_project_list(page: Page, server_url: str, project_name: str) -> None:
    page.goto(f"{server_url}/dashboard")
    project_card = page.locator("[data-testid='project-card']", has_text=project_name)
    expect(project_card).to_be_visible(timeout=10000)
    project_card.click()
    expect(page.locator("h1")).to_have_text(project_name, timeout=10000)


def open_chat_drawer(page: Page) -> None:
    ai_button = page.locator("header button", has_text=re.compile("AI 助手"))
    if ai_button.count() > 0:
        try:
            expect(ai_button).to_be_visible(timeout=500)
            ai_button.click()
        except AssertionError:
            pass  # Desktop dashboard routes: panel already visible, button hidden
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

    # New project without blueprint shows onboarding view
    expect(page.locator("text=项目已创建，开始构建蓝图吧")).to_be_visible(timeout=10000)
    # Onboarding must NOT show editing shell elements
    expect(page.locator("button", has_text="Build")).to_have_count(0, timeout=5000)
    expect(page.locator("button", has_text="Preview")).to_have_count(0, timeout=5000)
    expect(page.locator("[data-testid='workspace-sidebar']")).to_have_count(0, timeout=5000)


def test_direct_workspace_url(page: Page, server_url: str) -> None:
    """Direct navigation to a project workspace URL without prior UI entry."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_direct_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.on("console", lambda msg: print(f"CONSOLE [{msg.type}]: {msg.text}"))
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
    expect(page.locator("text=tool start")).to_be_visible(timeout=10000)
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
    _seed_project_blueprint(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    # Click Build and wait for a terminal state (success or failed)
    build_button = page.locator("button", has_text=re.compile("Build|Building"))
    expect(build_button).to_be_visible(timeout=10000)
    build_button.click()

    # Wait until Build button is no longer in running state
    expect(build_button).not_to_contain_text("Building", timeout=30000)

    # Assert build status message is visible (success or error)
    status_locator = page.locator("[data-testid='build-status']")
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


def test_workspace_build_status_survives_refresh(page: Page, server_url: str, e2e_workspace: Path) -> None:
    """Build success status and preview availability should survive page refresh."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_refresh_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)
    open_workspace_from_project_list(page, server_url, project_name)

    build_button = page.locator("button", has_text=re.compile("Build|Building"))
    expect(build_button).to_be_visible(timeout=10000)
    build_button.click()

    expect(build_button).not_to_contain_text("Building", timeout=30000)
    status_locator = page.locator("[data-testid='build-status']")
    expect(status_locator).to_be_visible(timeout=10000)
    status_text = status_locator.text_content() or ""
    assert "Build" in status_text or "Built" in status_text or "succeeded" in status_text
    assert "Preview available" in status_text

    # Refresh page
    page.reload()
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Build status message should still appear
    refreshed_status = page.locator("[data-testid='build-status']")
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

    # Ensure workspace has loaded before opening drawer
    page.wait_for_selector(f"h1:text-is('{project_name}')", timeout=15000)

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
    page.wait_for_selector(f"h1:text-is('{project_a}')", timeout=15000)
    open_chat_drawer(page)

    # Immediately switch to project B before the held response arrives
    page.goto(f"{server_url}/dashboard/projects/{project_b}")
    page.wait_for_selector(f"h1:text-is('{project_b}')", timeout=15000)
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


def test_project_list_shows_warning_for_corrupt_projects(page: Page, server_url: str) -> None:
    """Dashboard should display both valid project cards and corrupt-project warnings."""
    page.route(
        f"{server_url}/api/projects",
        lambda route, request: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "projects": [
                        {"name": "valid_proj", "path": "/tmp/valid_proj"}
                    ],
                    "errors": [
                        "Project 'corrupt_proj' has corrupt meta/project.json: invalid JSON"
                    ],
                }
            ),
        ),
    )
    page.goto(f"{server_url}/dashboard")
    expect(page.locator("[data-testid='project-card']", has_text="valid_proj")).to_be_visible(timeout=10000)
    expect(page.locator("text=部分项目元数据损坏")).to_be_visible(timeout=10000)
    expect(
        page.locator("text=Project 'corrupt_proj' has corrupt meta/project.json")
    ).to_be_visible(timeout=10000)


def test_project_list_no_empty_state_when_only_errors(page: Page, server_url: str) -> None:
    """When there are only errors and no projects, the misleading empty state must not appear."""
    page.route(
        f"{server_url}/api/projects",
        lambda route, request: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "projects": [],
                    "errors": [
                        "Project 'corrupt_proj' has corrupt meta/project.json: invalid JSON"
                    ],
                }
            ),
        ),
    )
    page.goto(f"{server_url}/dashboard")
    expect(page.locator("text=部分项目元数据损坏")).to_be_visible(timeout=10000)
    expect(page.locator("[data-testid='project-empty-state']")).to_have_count(0, timeout=5000)


def test_project_list_clears_warning_on_fetch_failure(page: Page, server_url: str) -> None:
    """A subsequent fetch failure must not leave a stale corrupt-project warning on screen."""
    get_calls = [0]

    def _handle_route(route, request):
        if request.method == "POST":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"name": "new_proj", "path": "/tmp/new_proj"}
                ),
            )
            return
        # GET /api/projects
        get_calls[0] += 1
        if get_calls[0] == 1:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "projects": [
                            {"name": "valid_proj", "path": "/tmp/valid_proj"}
                        ],
                        "errors": [
                            "Project 'corrupt_proj' has corrupt meta/project.json: invalid JSON"
                        ],
                    }
                ),
            )
        else:
            route.fulfill(
                status=500,
                content_type="text/plain",
                body="Internal Server Error",
            )

    page.route(f"{server_url}/api/projects", _handle_route)
    page.goto(f"{server_url}/dashboard")
    expect(page.locator("text=部分项目元数据损坏")).to_be_visible(timeout=10000)

    # Change mock to return 500 and refresh the page to trigger re-fetch
    page.route(
        f"{server_url}/api/projects",
        lambda route, request: route.fulfill(
            status=500,
            content_type="text/plain",
            body="Internal Server Error",
        ),
    )
    page.reload()

    expect(page.locator("text=Failed to fetch projects")).to_be_visible(timeout=10000)
    expect(page.locator("text=部分项目元数据损坏")).to_have_count(0)
    expect(page.locator("[data-testid='project-card']", has_text="valid_proj")).to_have_count(0, timeout=5000)


def test_project_list_ignores_stale_success_response(page: Page, server_url: str) -> None:
    """A newer successful fetch must not be overwritten by an older successful response that arrives late."""
    pending_gets: list = []
    get_count = [0]

    def _handle_route(route, request):
        if request.method == "POST":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"name": "new_proj", "path": "/tmp/new_proj"}),
            )
            return
        get_count[0] += 1
        if get_count[0] == 1:
            pending_gets.append(route)
        elif get_count[0] == 2:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"projects": [{"name": "new_proj", "path": "/tmp/new_proj"}], "errors": []}
                ),
            )
        else:
            route.continue_()

    page.route(f"{server_url}/api/projects", _handle_route)
    page.goto(f"{server_url}/dashboard")

    # Explicitly wait until the first GET is captured by the route handler.
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if len(pending_gets) == 1:
            break
        page.wait_for_timeout(50)
    assert len(pending_gets) == 1, "First GET /api/projects was not captured in time"

    # Refresh to trigger a second GET while the first one is still held
    page.reload()

    # Wait for the new project to appear from the second (fast) request
    expect(page.locator("[data-testid='project-card']", has_text="new_proj")).to_be_visible(timeout=10000)

    # Release the stale initial GET with old data
    for r in pending_gets:
        r.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"projects": [{"name": "stale_proj", "path": "/tmp/stale_proj"}], "errors": []}
            ),
        )

    expect(page.locator("[data-testid='project-card']", has_text="new_proj")).to_be_visible(timeout=5000)
    expect(page.locator("[data-testid='project-card']", has_text="stale_proj")).to_have_count(0)


def test_project_list_ignores_stale_error_response(page: Page, server_url: str) -> None:
    """A newer successful fetch must not be cleared by an older failed response that arrives late."""
    pending_gets: list = []
    get_count = [0]

    def _handle_route(route, request):
        if request.method == "POST":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"name": "new_proj", "path": "/tmp/new_proj"}),
            )
            return
        get_count[0] += 1
        if get_count[0] == 1:
            pending_gets.append(route)
        elif get_count[0] == 2:
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"projects": [{"name": "new_proj", "path": "/tmp/new_proj"}], "errors": []}
                ),
            )
        else:
            route.continue_()

    page.route(f"{server_url}/api/projects", _handle_route)
    page.goto(f"{server_url}/dashboard")

    # Explicitly wait until the first GET is captured by the route handler.
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if len(pending_gets) == 1:
            break
        page.wait_for_timeout(50)
    assert len(pending_gets) == 1, "First GET /api/projects was not captured in time"

    # Refresh to trigger a second GET while the first one is still held
    page.reload()

    # Wait for the new project to appear from the second (fast) request
    expect(page.locator("[data-testid='project-card']", has_text="new_proj")).to_be_visible(timeout=10000)

    # Release the stale initial GET with a 500 error
    for r in pending_gets:
        r.fulfill(
            status=500,
            content_type="text/plain",
            body="Internal Server Error",
        )

    expect(page.locator("[data-testid='project-card']", has_text="new_proj")).to_be_visible(timeout=5000)
    expect(page.locator("text=Failed to fetch projects")).to_have_count(0)


# ---- Phase 3 workspace API-consumption tests ----

def _seed_project_blueprint(workspace: Path, project_name: str, title: str = "Campus Romance") -> None:
    """Write a minimal blueprint.yaml and index.json for E2E workspace tests."""
    import yaml

    meta_dir = workspace / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)

    blueprint = {
        "title": title,
        "genre": "校园恋爱",
        "worldview": "现代日本高中",
        "themes": ["初恋", "成长"],
        "chapters": [
            {
                "id": "ch1",
                "name": "图书馆相遇",
                "order": 1,
                "scenes": [
                    {"id": "s1-1", "name": "初见", "order": 1},
                    {"id": "s1-2", "name": "借书", "order": 2},
                ],
            },
            {
                "id": "ch2",
                "name": "社团活动",
                "order": 2,
                "scenes": [
                    {"id": "s2-1", "name": "招募", "order": 1},
                ],
            },
        ],
    }
    (meta_dir / "blueprint.yaml").write_text(
        yaml.safe_dump(blueprint, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    game_dir = workspace / project_name / "game"
    game_dir.mkdir(parents=True, exist_ok=True)
    (game_dir / "scene1.rpy").write_text('label start:\n    "Hello scene 1"\n    return\n', encoding="utf-8")
    (game_dir / "scene2.rpy").write_text('label scene2:\n    "Hello scene 2"\n    return\n', encoding="utf-8")

    index = {
        "scenes": {
            "s1-1": {"chapter_id": "ch1", "label": "start", "file_path": "game/scene1.rpy"},
            "s1-2": {"chapter_id": "ch1", "label": "scene2", "file_path": "game/scene2.rpy"},
            "s2-1": {"chapter_id": "ch2", "label": "recruit", "file_path": "game/scene1.rpy"},
        }
    }
    (meta_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")


def test_workspace_shows_blueprint_chapters_and_scenes(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Direct workspace URL should display project name, blueprint title, and chapter/scene list."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_ws_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    # Project name in header
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)
    # Blueprint title
    expect(page.locator("text=Campus Romance")).to_be_visible(timeout=10000)
    # Chapter list in sidebar
    expect(page.locator("button", has_text="图书馆相遇")).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="社团活动")).to_be_visible(timeout=10000)
    # Scene list in sidebar
    expect(page.locator("button", has_text="初见")).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="借书")).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="招募")).to_be_visible(timeout=10000)


def test_workspace_selects_default_scene_and_shows_script(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Workspace should auto-select the first scene and display its script."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_ws_default_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Default tab is Blueprint; switch to Scene tab to view script
    page.locator("button", has_text="场景").click()
    expect(page.locator("text=Hello scene 1")).to_be_visible(timeout=10000)
    # File path should be visible
    expect(page.locator("text=game/scene1.rpy")).to_be_visible(timeout=10000)


def test_workspace_click_scene_switches_script(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Clicking another scene should switch to the Scene tab and show its script."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_ws_click_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Click another scene in sidebar; should auto-switch to Scene tab
    page.locator("button", has_text="借书").click()

    # Scene tab should become active
    expect(page.locator("button", has_text="场景")).to_have_attribute("class", re.compile(r"border-blue-500"), timeout=10000)

    # Script should switch to scene 2 content
    expect(page.locator("text=Hello scene 2")).to_be_visible(timeout=10000)


def test_workspace_shows_error_when_blueprint_missing(
    page: Page, server_url: str
) -> None:
    """Workspace should show onboarding when blueprint is missing, not a white screen."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_ws_nobp_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    # Do NOT write blueprint.yaml

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Onboarding view should be visible for projects without blueprint
    expect(page.locator("text=项目已创建，开始构建蓝图吧")).to_be_visible(timeout=10000)


def test_workspace_no_longer_shows_old_entry_cards(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """The old '3 entry cards' (Story Map, Script Editor, Assets) should not be the main structure."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_ws_nocards_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Old cards should not exist
    expect(page.locator("h4:has-text('Story Map')")).to_have_count(0)
    expect(page.locator("h4:has-text('脚本编辑')")).to_have_count(0)
    expect(page.locator("h4:has-text('资源管理')")).to_have_count(0)


def test_workspace_latest_project_selection_wins(
    page: Page, server_url: str
) -> None:
    """If two selectProject requests race, the latest one must win.

    Scenario:
    1. Open project A workspace -> selectProject("A") is slow (intercepted).
    2. Go back to project list and open project B -> selectProject("B") succeeds.
    3. Release the stale selectProject("A") response.
    4. Without latest-wins guard, currentProject would flip back to A, causing
       the workspace effect to self-heal by issuing a *second* selectProject("B").
    5. With the guard, project B should remain selected with exactly 1 request.
    """
    assert wait_for_server(server_url), "Server not ready"

    project_a = f"playwright_race_a_{int(time.time())}"
    project_b = f"playwright_race_b_{int(time.time())}"
    create_project_via_api(server_url, project_a)
    create_project_via_api(server_url, project_b)

    pending_routes: list = []
    select_counts = {project_a: 0, project_b: 0}

    def handle_select(route, request):
        if request.method != "POST":
            route.continue_()
            return
        body = request.post_data_json
        name = body.get("name", "")
        if name not in select_counts:
            route.continue_()
            return
        select_counts[name] += 1
        if name == project_a:
            pending_routes.append(route)
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "success": True,
                    "current_project": {
                        "name": name,
                        "path": str(Path(f"/workspace/{name}")),
                    },
                }
            ),
        )

    page.route("**/api/projects/select", handle_select)

    # 1. Navigate to project A workspace (selectProject("A") is held)
    page.goto(f"{server_url}/dashboard/projects/{project_a}")
    page.wait_for_timeout(500)

    # 2. Navigate back to project list
    page.goto(f"{server_url}/dashboard/projects")
    expect(page.locator("[data-testid='dashboard-header']")).to_be_visible(timeout=10000)

    # 3. Click project B -> selectProject("B") succeeds immediately
    page.locator("[data-testid='project-card']", has_text=project_b).click()
    expect(page.locator("h1")).to_have_text(project_b, timeout=10000)

    # 4. Release stale selectProject("A") response
    assert len(pending_routes) == 1
    stale_route = pending_routes.pop(0)
    stale_route.fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps(
            {
                "success": True,
                "current_project": {
                    "name": project_a,
                    "path": str(Path(f"/workspace/{project_a}")),
                },
            }
        ),
    )

    # Give stale response time to potentially overwrite state
    page.wait_for_timeout(2000)

    # 5. Assert page still shows B AND no extra self-healing request was issued
    assert page.locator("h1").text_content() == project_b
    assert select_counts[project_b] == 1, (
        f"Expected 1 selectProject for {project_b}, got {select_counts[project_b]}. "
        "Stale response likely overwrote currentProject and triggered self-heal."
    )


def _client_navigate_to_project(page: Page, project_name: str) -> None:
    """Trigger React Router client-side navigation without full page reload."""
    page.evaluate(
        f"""() => {{
            window.history.pushState({{}}, '', '/dashboard/projects/{project_name}');
            window.dispatchEvent(new PopStateEvent('popstate'));
        }}"""
    )


def test_workspace_build_status_does_not_leak_across_project_switch(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Build success / preview available UI from project A must not appear on project B."""
    assert wait_for_server(server_url), "Server not ready"

    project_a = f"playwright_leak_a_{int(time.time())}"
    project_b = f"playwright_leak_b_{int(time.time())}"
    create_project_via_api(server_url, project_a)
    create_project_via_api(server_url, project_b)
    # Project A needs a blueprint to enter editing state where Build is available
    _seed_project_blueprint(e2e_workspace, project_a)

    # --- On project A: trigger build and wait for success ---
    page.goto(f"{server_url}/dashboard/projects/{project_a}")
    expect(page.locator("h1")).to_have_text(project_a, timeout=30000)

    build_button = page.locator("button", has_text=re.compile("Build|Building"))
    expect(build_button).to_be_visible(timeout=10000)
    build_button.click()

    expect(build_button).not_to_contain_text("Building", timeout=30000)
    status = page.locator("[data-testid='build-status']")
    expect(status).to_be_visible(timeout=10000)
    assert "Preview available" in (status.text_content() or "")

    # --- Client-side navigate to project B (no full reload) ---
    _client_navigate_to_project(page, project_b)
    expect(page.locator("h1")).to_have_text(project_b, timeout=30000)

    # Wait for B's onboarding view to finish rendering (loading must end naturally)
    expect(page.locator("text=项目已创建，开始构建蓝图吧")).to_be_visible(timeout=10000)

    # --- Assert A's build artifacts are gone ---
    assert page.locator("[data-testid='build-status']").count() == 0
    assert page.locator("a[href*='127.0.0.1']").count() == 0


def test_workspace_old_load_does_not_prematurely_end_loading(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """A stale workspace snapshot response must not end the spinner before the latest load finishes.

    Scenario:
    1. Open project A workspace -> loadProjectData("A") starts.
    2. Intercept snapshot APIs so A's requests are held.
    3. Client-side navigate to project B -> loadProjectData("B") starts.
    4. Release A's held requests (simulate stale response arriving first).
    5. If the stale response prematurely ends loading, B's workspace would render
       with empty placeholders (spinner disappears too early).
    6. Release B's requests.
    7. Assert B's data is fully rendered.
    """
    assert wait_for_server(server_url), "Server not ready"

    project_a = f"playwright_old_a_{int(time.time())}"
    project_b = f"playwright_old_b_{int(time.time())}"
    create_project_via_api(server_url, project_a)
    create_project_via_api(server_url, project_b)
    _seed_project_blueprint(e2e_workspace, project_a, title="Alpha Title")
    _seed_project_blueprint(e2e_workspace, project_b, title="Beta Title")

    pending_routes: list = []

    def handle_snapshot(route, request):
        url = request.url
        print(f"DEBUG route intercepted: {url}")
        if _is_top_level_snapshot_request(url):
            pending_routes.append(route)
            print(f"DEBUG route held: {url}")
            return
        route.continue_()

    page.route("**/api/projects/**", handle_snapshot)

    # 1. Navigate to A -> snapshot requests are held
    page.goto(f"{server_url}/dashboard/projects/{project_a}")
    # Poll until snapshot requests are captured (docked ChatDrawer increases mount time)
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if len(pending_routes) >= 1:
            break
        page.wait_for_timeout(50)
    a_count = len(pending_routes)
    assert a_count >= 1, f"Expected at least one held snapshot request for A, got {a_count}"

    # 2. Client-side navigate to B -> more snapshot requests are held
    _client_navigate_to_project(page, project_b)
    # Poll until B's snapshot requests appear (docked ChatDrawer increases mount time)
    deadline = time.time() + 5.0
    while time.time() < deadline:
        b_count = len(pending_routes)
        if b_count > a_count:
            break
        page.wait_for_timeout(50)
    b_count = len(pending_routes)
    assert b_count > a_count, f"Expected additional snapshot requests for B, got {b_count}"

    # 3. Release A's stale requests first
    for _ in range(a_count):
        route = pending_routes.pop(0)
        route.continue_()

    # 4. Poll for a few seconds. If the stale response prematurely ended loading,
    #    the empty workspace layout (with placeholders) would appear and stay.
    #    If loading is managed correctly, the spinner stays the whole time.
    for _ in range(6):
        page.wait_for_timeout(500)
        if page.locator("text=暂无蓝图数据").count() > 0:
            assert False, "Stale request prematurely ended loading; workspace rendered before new load completed"

    # 5. Release B's snapshot requests
    while pending_routes:
        route = pending_routes.pop(0)
        route.continue_()

    # B's loadProjectData may issue a late /scenes/{id}/script request.
    # Wait a beat and release any stragglers.
    page.wait_for_timeout(800)
    while pending_routes:
        route = pending_routes.pop(0)
        route.continue_()

    # 6. B should fully load with its own data
    expect(page.locator("h1")).to_have_text(project_b, timeout=30000)
    expect(page.locator("text=Beta Title")).to_be_visible(timeout=10000)


# ---- Phase 3 round 2: new workspace UI migration tests ----


def test_workspace_structure_migrated(page: Page, server_url: str, e2e_workspace: Path) -> None:
    """New workspace must have sidebar, content tabs, and no old card stacks."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_mig_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Left sidebar with chapter navigation
    expect(page.locator("text=章节").first).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="图书馆相遇")).to_be_visible(timeout=10000)

    # Content tabs: Blueprint, Story Map, Scene
    expect(page.locator("button", has_text="蓝图")).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="Story Map")).to_be_visible(timeout=10000)

    # Old card stacks must not exist
    expect(page.locator("h4:has-text('Story Map')")).to_have_count(0)
    expect(page.locator("h4:has-text('脚本编辑')")).to_have_count(0)
    expect(page.locator("h4:has-text('资源管理')")).to_have_count(0)


def test_workspace_default_blueprint_view(page: Page, server_url: str, e2e_workspace: Path) -> None:
    """Default tab should be Blueprint with rich content, not a tiny summary card."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_bp_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Blueprint tab is active by default
    blueprint_tab = page.locator("button", has_text="蓝图")
    expect(blueprint_tab).to_have_attribute("class", re.compile(r"border-blue-500"), timeout=10000)

    # Rich blueprint content visible
    expect(page.locator("text=Campus Romance")).to_be_visible(timeout=10000)
    expect(page.locator("text=项目信息")).to_be_visible(timeout=10000)



def _seed_project_with_branch(workspace: Path, project_name: str) -> None:
    """Write a blueprint with a middle scene that has choices (branch edges)."""
    import yaml

    meta_dir = workspace / project_name / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)

    blueprint = {
        "title": "Branch Project",
        "genre": "校园恋爱",
        "worldview": "现代日本高中",
        "themes": ["初恋", "成长"],
        "chapters": [
            {
                "id": "ch1",
                "name": "第一章",
                "order": 1,
                "scenes": [
                    {"id": "s1-1", "name": "开场", "order": 1},
                    {
                        "id": "s1-2",
                        "name": "选择",
                        "order": 2,
                        "choices": [
                            {"text": "去图书馆", "next_scene_id": "s2-1"},
                            {"text": "去社团", "next_scene_id": "s2-2"},
                        ],
                    },
                    {"id": "s1-3", "name": "告别", "order": 3},
                ],
            },
            {
                "id": "ch2",
                "name": "第二章",
                "order": 2,
                "scenes": [
                    {"id": "s2-1", "name": "图书馆线", "order": 1},
                    {"id": "s2-2", "name": "社团线", "order": 2},
                ],
            },
        ],
    }
    (meta_dir / "blueprint.yaml").write_text(
        yaml.safe_dump(blueprint, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    game_dir = workspace / project_name / "game"
    game_dir.mkdir(parents=True, exist_ok=True)
    (game_dir / "scene1.rpy").write_text('label start:\n    "Hello"\n    return\n', encoding="utf-8")

    index = {
        "scenes": {
            "s1-1": {"chapter_id": "ch1", "label": "start", "file_path": "game/scene1.rpy"},
            "s1-2": {"chapter_id": "ch1", "label": "choice", "file_path": "game/scene1.rpy"},
            "s1-3": {"chapter_id": "ch1", "label": "goodbye", "file_path": "game/scene1.rpy"},
            "s2-1": {"chapter_id": "ch2", "label": "lib", "file_path": "game/scene1.rpy"},
            "s2-2": {"chapter_id": "ch2", "label": "club", "file_path": "game/scene1.rpy"},
        }
    }
    (meta_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")


def test_workspace_switch_to_story_map_tab(page: Page, server_url: str, e2e_workspace: Path) -> None:
    """Clicking Story Map tab should show the story map workspace, not just a summary card."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_sm_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Click Story Map tab
    page.locator("button", has_text="Story Map").click()

    # Story Map tab becomes active
    sm_tab = page.locator("button", has_text="Story Map")
    expect(sm_tab).to_have_attribute("class", re.compile(r"border-blue-500"), timeout=10000)

    # Story Map board is visible in the main content area
    board = page.locator("[data-testid='story-map-board']")
    expect(board).to_be_visible(timeout=10000)

    # Chapter boards are inside the story map board
    expect(board.locator("[data-testid='story-map-chapter']")).to_have_count(2, timeout=10000)
    expect(board.locator("h4", has_text="图书馆相遇")).to_be_visible(timeout=10000)
    expect(board.locator("h4", has_text="社团活动")).to_be_visible(timeout=10000)

    # Scene nodes are inside the story map board (not sidebar buttons)
    # _seed_project_blueprint creates 3 scenes across 2 chapters
    expect(board.locator("[data-testid='story-map-scene-node']")).to_have_count(3, timeout=10000)
    expect(board.locator("[data-testid='story-map-scene-node']", has_text="初见")).to_be_visible(timeout=10000)
    expect(board.locator("[data-testid='story-map-scene-node']", has_text="借书")).to_be_visible(timeout=10000)


def test_workspace_project_switch_keeps_new_ui(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Switching projects must keep the new workspace UI structure intact."""
    assert wait_for_server(server_url), "Server not ready"

    project_a = f"playwright_ui_a_{int(time.time())}"
    project_b = f"playwright_ui_b_{int(time.time())}"
    create_project_via_api(server_url, project_a)
    create_project_via_api(server_url, project_b)
    _seed_project_blueprint(e2e_workspace, project_a, title="Alpha Project")
    _seed_project_blueprint(e2e_workspace, project_b, title="Beta Project")

    # Open project A
    page.goto(f"{server_url}/dashboard/projects/{project_a}")
    expect(page.locator("h1")).to_have_text(project_a, timeout=30000)
    expect(page.locator("text=Alpha Project")).to_be_visible(timeout=10000)

    # Switch to Story Map tab on A
    page.locator("button", has_text="Story Map").click()
    expect(page.locator("button", has_text="Story Map")).to_have_attribute(
        "class", re.compile(r"border-blue-500"), timeout=10000
    )

    # Client-side navigate to B
    _client_navigate_to_project(page, project_b)
    
    # Listen for console errors
    console_logs = []
    page.on("console", lambda msg: console_logs.append(f"{msg.type}: {msg.text}"))
    page.on("pageerror", lambda err: console_logs.append(f"PAGEERROR: {err}"))
    
    expect(page.locator("h1")).to_have_text(project_b, timeout=30000)

    # B should render with Blueprint tab active (reset on project change)
    expect(page.locator("button", has_text="蓝图")).to_have_attribute(
        "class", re.compile(r"border-blue-500"), timeout=10000
    )
    try:
        expect(page.locator("text=Beta Project")).to_be_visible(timeout=10000)
    except AssertionError:
        page.screenshot(path="D:/renpy-mcp-unified-design/debug_beta_project2.png")
        content = page.content()
        with open("D:/renpy-mcp-unified-design/debug_beta_project2.html", "w", encoding="utf-8") as f:
            f.write(content)
        print("CONSOLE LOGS:")
        for log in console_logs[-20:]:
            print(log)
        raise

    # Sidebar should show B's chapters
    expect(page.locator("button", has_text="图书馆相遇")).to_be_visible(timeout=10000)

    # Old card stacks still absent
    expect(page.locator("h4:has-text('Story Map')")).to_have_count(0)


def test_story_map_shows_branch_for_middle_scene(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """A middle scene with choices should show branch flow in the Story Map board."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_branch_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_with_branch(e2e_workspace, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Click Story Map tab
    page.locator("button", has_text="Story Map").click()
    expect(page.locator("button", has_text="Story Map")).to_have_attribute(
        "class", re.compile(r"border-blue-500"), timeout=10000
    )

    # The middle scene "选择" is inside the story map board
    board = page.locator("[data-testid='story-map-board']")
    choice_node = board.locator("[data-testid='story-map-scene-node']", has_text="选择")
    expect(choice_node).to_be_visible(timeout=10000)

    # Branch labels should be visible near the middle scene (not just the last scene)
    expect(board.locator("text=去图书馆")).to_be_visible(timeout=10000)
    expect(board.locator("text=去社团")).to_be_visible(timeout=10000)


def test_sidebar_expansion_resets_on_project_switch(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Switching projects should reset sidebar chapter expansion to default (all expanded)."""
    assert wait_for_server(server_url), "Server not ready"

    project_a = f"playwright_exp_a_{int(time.time())}"
    project_b = f"playwright_exp_b_{int(time.time())}"
    create_project_via_api(server_url, project_a)
    create_project_via_api(server_url, project_b)
    _seed_project_blueprint(e2e_workspace, project_a)
    _seed_project_blueprint(e2e_workspace, project_b)

    # Open project A
    page.goto(f"{server_url}/dashboard/projects/{project_a}")
    expect(page.locator("h1")).to_have_text(project_a, timeout=30000)

    # Verify A's scenes are visible (default expanded)
    expect(page.locator("button", has_text="初见")).to_be_visible(timeout=10000)

    # Collapse chapter 1 in sidebar by clicking its header
    page.locator("button", has_text="图书馆相遇").click()

    # After collapse, the scene buttons inside chapter 1 should not be visible
    expect(page.locator("button", has_text="初见")).not_to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="借书")).not_to_be_visible(timeout=10000)

    # Client-side navigate to project B
    _client_navigate_to_project(page, project_b)
    expect(page.locator("h1")).to_have_text(project_b, timeout=30000)

    # B's chapter 1 scenes should be visible again because expansion reset to default
    expect(page.locator("button", has_text="初见")).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="借书")).to_be_visible(timeout=10000)


def test_workspace_hides_legacy_outer_shell(page: Page, server_url: str) -> None:
    """When inside a project workspace, the old outer navigation shell must be hidden."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_shell_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Old outer nav items must NOT be visible (sidebar is hidden in workspace)
    expect(page.locator("a", has_text="项目")).not_to_be_visible(timeout=5000)
    expect(page.locator("a", has_text="Story Map")).not_to_be_visible(timeout=5000)
    expect(page.locator("a", has_text="脚本编辑")).not_to_be_visible(timeout=5000)
    expect(page.locator("a", has_text="资源管理")).not_to_be_visible(timeout=5000)

    # Project list page should also hide the legacy shell
    page.goto(f"{server_url}/dashboard/projects")
    expect(page.locator("a", has_text="项目")).not_to_be_visible(timeout=5000)
    expect(page.locator("a", has_text="Story Map")).not_to_be_visible(timeout=5000)


def test_onboarding_hides_workspace_editing_shell(page: Page, server_url: str) -> None:
    """Onboarding phase must NOT display editing workspace shell (Build/Preview/sidebar)."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_onb_shell_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("[data-testid='workspace-project-title']")).to_have_text(
        project_name, timeout=30000
    )

    # Onboarding view is visible
    expect(page.locator("[data-testid='workspace-onboarding-view']")).to_be_visible(timeout=10000)

    # Build / Preview must NOT be visible during onboarding
    expect(page.locator("button", has_text="Build")).to_have_count(0, timeout=5000)
    expect(page.locator("button", has_text="Preview")).to_have_count(0, timeout=5000)

    # Sidebar must NOT be visible during onboarding
    expect(page.locator("[data-testid='workspace-sidebar']")).to_have_count(0, timeout=5000)


def test_editing_workspace_still_shows_full_shell(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Editing phase must continue to show the full workspace shell."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_edit_shell_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("[data-testid='workspace-project-title']")).to_have_text(
        project_name, timeout=30000
    )

    # Build / Preview visible
    expect(page.locator("button", has_text="Build")).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="Preview")).to_be_visible(timeout=10000)

    # Sidebar visible
    expect(page.locator("[data-testid='workspace-sidebar']")).to_be_visible(timeout=10000)

    # Tabs visible
    expect(page.locator("button", has_text="蓝图")).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="Story Map")).to_be_visible(timeout=10000)


def test_workspace_has_single_project_title(page: Page, server_url: str) -> None:
    """Workspace must show the project name only once — in the main content header, not in AppShell."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_single_title_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")

    # Main workspace title is visible in content area
    workspace_title = page.locator("[data-testid='workspace-project-title']")
    expect(workspace_title).to_have_text(project_name, timeout=30000)

    # AppShell top header must NOT repeat the project name
    assert page.locator("header").get_by_text(project_name).count() == 0


def test_project_list_uses_new_dashboard_layout(page: Page, server_url: str) -> None:
    """Project list page should render the new dashboard homepage layout."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_dash_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects")

    # New dashboard header with brand
    expect(page.locator("[data-testid='dashboard-header']")).to_be_visible(timeout=10000)
    # New project CTA
    expect(page.locator("[data-testid='new-project-cta']")).to_be_visible(timeout=10000)
    # Project list area
    expect(page.locator("[data-testid='project-list-area']")).to_be_visible(timeout=10000)
    # Project card with the created project
    expect(page.locator("[data-testid='project-card']", has_text=project_name)).to_be_visible(timeout=10000)


def test_project_list_empty_state_uses_dashboard_layout(page: Page, server_url: str) -> None:
    """Empty project list should still show dashboard homepage structure."""
    assert wait_for_server(server_url), "Server not ready"

    # Mock empty project list to ensure empty state appears
    page.route(
        f"{server_url}/api/projects",
        lambda route, request: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"projects": [], "errors": []}),
        ),
    )

    page.goto(f"{server_url}/dashboard/projects")

    # Dashboard header still visible
    expect(page.locator("[data-testid='dashboard-header']")).to_be_visible(timeout=10000)
    # New project CTA still visible
    expect(page.locator("[data-testid='new-project-cta']")).to_be_visible(timeout=10000)
    # Empty state within project list area
    expect(page.locator("[data-testid='project-list-area']")).to_be_visible(timeout=10000)
    expect(page.locator("[data-testid='project-empty-state']")).to_be_visible(timeout=10000)


def test_create_project_from_new_homepage_enters_workspace(page: Page, server_url: str) -> None:
    """Creating a project from the new dashboard homepage should enter workspace."""
    assert wait_for_server(server_url), "Server not ready"

    page.goto(f"{server_url}/dashboard/projects")
    expect(page.locator("[data-testid='dashboard-header']")).to_be_visible(timeout=10000)

    project_name = f"playwright_new_home_{int(time.time())}"

    # Click new project CTA
    page.locator("[data-testid='new-project-cta']").click()

    # Create dialog should open
    expect(page.locator("[data-testid='create-project-dialog']")).to_be_visible(timeout=10000)
    page.locator("[data-testid='create-project-name-input']").fill(project_name)
    page.locator("[data-testid='create-project-submit']").click()

    # Should navigate to workspace
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)
    # Onboarding view should appear for new project without blueprint
    expect(page.locator("[data-testid='workspace-onboarding-view']")).to_be_visible(timeout=10000)


def test_homepage_and_workspace_use_consistent_shell(page: Page, server_url: str, e2e_workspace: Path) -> None:
    """Both homepage and workspace should use the new dashboard shell without legacy sidebar."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_consistent_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)

    # Homepage: no legacy sidebar
    page.goto(f"{server_url}/dashboard/projects")
    expect(page.locator("[data-testid='dashboard-header']")).to_be_visible(timeout=10000)
    expect(page.locator("a", has_text="项目")).not_to_be_visible(timeout=5000)
    expect(page.locator("a", has_text="Story Map")).not_to_be_visible(timeout=5000)
    expect(page.locator("a", has_text="脚本编辑")).not_to_be_visible(timeout=5000)
    expect(page.locator("a", has_text="资源管理")).not_to_be_visible(timeout=5000)

    # Navigate to workspace
    page.locator("[data-testid='project-card']", has_text=project_name).click()
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Workspace: also no legacy sidebar
    expect(page.locator("a", has_text="项目")).not_to_be_visible(timeout=5000)
    expect(page.locator("a", has_text="Story Map")).not_to_be_visible(timeout=5000)
    expect(page.locator("a", has_text="脚本编辑")).not_to_be_visible(timeout=5000)
    expect(page.locator("a", has_text="资源管理")).not_to_be_visible(timeout=5000)
    # Workspace content should be visible
    expect(page.locator("text=Campus Romance")).to_be_visible(timeout=10000)


def test_project_list_does_not_show_persistent_ai_panel(page: Page, server_url: str) -> None:
    """Homepage should NOT show a persistent right AI panel by default."""
    assert wait_for_server(server_url), "Server not ready"

    page.goto(f"{server_url}/dashboard/projects")
    expect(page.locator("[data-testid='dashboard-header']")).to_be_visible(timeout=10000)
    # Docked AI panel must NOT appear on homepage
    expect(page.locator("[data-testid='chat-panel-docked']")).to_have_count(0, timeout=5000)
    # Dashboard content should be fully visible
    expect(page.locator("[data-testid='project-list-area']")).to_be_visible(timeout=10000)


def test_project_list_has_no_ai_assistant(page: Page, server_url: str) -> None:
    """Homepage should NOT show AI assistant button or chat drawer."""
    assert wait_for_server(server_url), "Server not ready"

    page.goto(f"{server_url}/dashboard/projects")
    expect(page.locator("[data-testid='dashboard-header']")).to_be_visible(timeout=10000)
    # No docked panel
    expect(page.locator("[data-testid='chat-panel-docked']")).to_have_count(0, timeout=5000)

    # AI 助手 button must NOT be visible
    ai_button = page.locator("header button", has_text="AI 助手")
    expect(ai_button).to_have_count(0, timeout=5000)

    # Overlay chat drawer must NOT appear
    expect(page.locator("[data-testid='chat-drawer']")).to_have_count(0, timeout=5000)


def test_workspace_shows_persistent_ai_panel(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Workspace editing view should show both main content and persistent right AI panel."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_ai_ws_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("[data-testid='workspace-project-title']")).to_have_text(
        project_name, timeout=30000
    )

    # Main workspace content visible
    expect(page.locator("[data-testid='workspace-sidebar']")).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="蓝图")).to_be_visible(timeout=10000)

    # Right AI panel visible simultaneously
    ai_panel = page.locator("[data-testid='chat-panel-docked']")
    expect(ai_panel).to_be_visible(timeout=10000)
    # It should contain the Bot header
    expect(ai_panel.locator("text=AI 助手")).to_be_visible(timeout=5000)


def test_onboarding_uses_existing_right_ai_panel(page: Page, server_url: str) -> None:
    """Clicking '让 AI 生成蓝图' should use the already-visible right panel, not open an overlay."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_ai_onb_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("[data-testid='workspace-project-title']")).to_have_text(
        project_name, timeout=30000
    )

    # AI panel already visible
    ai_panel = page.locator("[data-testid='chat-panel-docked']")
    expect(ai_panel).to_be_visible(timeout=10000)

    # Click start AI
    page.locator("button", has_text="让 AI 生成蓝图").click()

    # Collecting conversation should appear directly in the existing panel
    # First assistant message now comes from backend via WS
    expect(ai_panel.locator("text=太棒了！让我来帮你")).to_be_visible(timeout=15000)
    expect(page.locator("text=正在与 AI 细化需求")).to_be_visible(timeout=10000)


# ---- Phase 3 round 3: onboarding / blueprint collection flow ----


def test_new_project_shows_onboarding_view(page: Page, server_url: str) -> None:
    """A newly created project without blueprint should show onboarding instead of empty workspace."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_onb_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Onboarding view should be visible
    expect(page.locator("text=让 AI 生成蓝图")).to_be_visible(timeout=10000)
    expect(page.locator("text=手动准备 YAML（即将支持）")).to_be_visible(timeout=10000)
    expect(page.locator("text=项目已创建，开始构建蓝图吧")).to_be_visible(timeout=10000)


def test_click_ai_generate_opens_chat_and_starts_collecting(
    page: Page, server_url: str
) -> None:
    """Clicking '让 AI 生成蓝图' should open chat drawer and enter collecting state."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_col_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Click the AI generate button
    page.locator("button", has_text="让 AI 生成蓝图").click()

    # Chat drawer should open with first interview question from backend
    expect(page.locator("text=太棒了！让我来帮你把这个想法变成完整的蓝图")).to_be_visible(timeout=15000)

    # Workspace should show collecting state
    expect(page.locator("text=正在与 AI 细化需求")).to_be_visible(timeout=10000)


def test_mobile_overlay_starts_collection_reliably(page: Page, server_url: str) -> None:
    """On narrow viewport, clicking '让 AI 生成蓝图' must still receive the first backend assistant message."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_mobile_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    # Simulate mobile viewport so overlay drawer is used instead of docked panel
    page.set_viewport_size({"width": 375, "height": 667})

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # On mobile, AI button should be visible in header (workspace route)
    ai_button = page.locator("header button", has_text="AI 助手")
    expect(ai_button).to_be_visible(timeout=5000)

    # Click start AI
    page.locator("button", has_text="让 AI 生成蓝图").click()

    # Chat drawer should open as overlay
    chat_drawer = page.locator("[data-testid='chat-drawer']")
    expect(chat_drawer).to_be_visible(timeout=10000)

    # First assistant message from backend must appear even though drawer/WS were just opened
    expect(chat_drawer.locator("text=太棒了！让我来帮你")).to_be_visible(timeout=15000)

    # Workspace should show collecting state
    expect(page.locator("text=正在与 AI 细化需求")).to_be_visible(timeout=10000)


def test_interview_progresses_to_reviewing_and_confirms(
    page: Page, server_url: str
) -> None:
    """After a few interview exchanges, user should see blueprint draft and be able to confirm."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_rev_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    console_logs = []
    page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Start collecting
    page.locator("button", has_text="让 AI 生成蓝图").click()
    # First assistant message now comes from backend via WS
    expect(page.locator("text=太棒了！让我来帮你")).to_be_visible(timeout=15000)

    # First user reply
    page.locator("textarea").fill("我想写一个3章的校园恋爱故事，主角是高中生")
    page.locator("button >> svg").last.click()

    # Wait for AI response and second question
    expect(page.locator("text=收到")).to_be_visible(timeout=10000)

    # Second user reply
    page.locator("textarea").fill("视觉风格是日系动漫，氛围轻松治愈")
    page.locator("button >> svg").last.click()

    # After enough turns, should enter reviewing with blueprint draft card
    onboarding_view = page.locator("[data-testid='workspace-onboarding-view']")
    expect(onboarding_view.locator("text=项目蓝图")).to_be_visible(timeout=15000)
    expect(onboarding_view.locator("text=确认并生成")).to_be_visible(timeout=15000)

    # Chat drawer should also show structured confirmation
    chat_drawer = page.locator("[data-testid='chat-panel-docked']")
    confirmation_panel = chat_drawer.locator("[data-testid='chat-blueprint-confirmation']")
    expect(chat_drawer.locator("text=蓝图草案确认")).to_be_visible(timeout=15000)

    # Click confirm from chat drawer
    confirmation_panel.locator("button", has_text="确认并生成").click()

    # Chat drawer should close after confirm
    expect(chat_drawer.locator("text=蓝图草案确认")).to_have_count(0, timeout=10000)

    # Should show generating state
    expect(page.locator("text=正在生成蓝图")).to_be_visible(timeout=10000)

    # Eventually should show blueprint content (editing state)
    expect(page.locator("text=项目信息")).to_be_visible(timeout=20000)


def test_manual_yaml_placeholder_shows_correctly(
    page: Page, server_url: str
) -> None:
    """Clicking manual YAML placeholder should show honest placeholder, not fake editing."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_man_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Click the manual YAML placeholder button
    page.locator("button", has_text="手动准备 YAML（即将支持）").click()

    # Should show placeholder message instead of entering fake editing state
    expect(page.locator("text=手动 YAML 编辑功能即将推出")).to_be_visible(timeout=10000)
    expect(page.locator("text=返回")).to_be_visible(timeout=10000)

    # Should NOT see fake editing workspace
    expect(page.locator("text=项目信息")).to_have_count(0, timeout=5000)

    # Click back to return to onboarding
    page.locator("button", has_text="返回").click()
    expect(page.locator("text=让 AI 生成蓝图")).to_be_visible(timeout=10000)


def test_reviewing_shows_confirmation_in_chat_drawer(
    page: Page, server_url: str
) -> None:
    """Reviewing phase should show structured confirmation card inside Chat Drawer."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_chat_rev_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Start collecting
    page.locator("button", has_text="让 AI 生成蓝图").click()
    expect(page.locator("text=太棒了！让我来帮你")).to_be_visible(timeout=15000)

    # First user reply
    page.locator("textarea").fill("我想写一个3章的校园恋爱故事，主角是高中生")
    page.locator("button >> svg").last.click()
    expect(page.locator("text=收到")).to_be_visible(timeout=10000)

    # Second user reply
    page.locator("textarea").fill("视觉风格是日系动漫，氛围轻松治愈")
    page.locator("button >> svg").last.click()

    # Chat drawer should still be open and show structured confirmation
    chat_drawer = page.locator("[data-testid='chat-panel-docked']")
    confirmation_panel = chat_drawer.locator("[data-testid='chat-blueprint-confirmation']")
    expect(chat_drawer.locator("text=蓝图草案确认")).to_be_visible(timeout=15000)
    expect(confirmation_panel.locator("text=未命名项目")).to_have_count(0, timeout=5000)
    expect(confirmation_panel.locator("text=" + project_name)).to_be_visible(timeout=15000)
    expect(confirmation_panel.locator("text=校园恋爱")).to_be_visible(timeout=15000)
    expect(confirmation_panel.locator("button", has_text="确认并生成")).to_be_visible(timeout=15000)
    expect(confirmation_panel.locator("button", has_text="继续调整")).to_be_visible(timeout=15000)

    # Main content should also show reviewing
    expect(page.locator("h2", has_text="蓝图草案已生成")).to_be_visible(timeout=10000)

    # Click "继续调整" from chat drawer should return to collecting
    confirmation_panel.locator("button", has_text="继续调整").click()
    expect(page.locator("text=正在与 AI 细化需求")).to_be_visible(timeout=10000)


def test_reviewing_refresh_restores_structured_messages(page: Page, server_url: str) -> None:
    """After reaching reviewing and refreshing, ChatDrawer should still show blueprint draft and confirmation request messages."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_refresh_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Start collecting
    page.locator("button", has_text="让 AI 生成蓝图").click()
    expect(page.locator("text=太棒了！让我来帮你")).to_be_visible(timeout=15000)

    # First user reply
    page.locator("textarea").fill("我想写一个3章的校园恋爱故事，主角是高中生")
    page.locator("button >> svg").last.click()
    expect(page.locator("text=收到")).to_be_visible(timeout=10000)

    # Second user reply
    page.locator("textarea").fill("视觉风格是日系动漫，氛围轻松治愈")
    page.locator("button >> svg").last.click()

    # Wait for reviewing state
    chat_drawer = page.locator("[data-testid='chat-panel-docked']")
    expect(chat_drawer.locator("text=蓝图草案确认")).to_be_visible(timeout=15000)

    # Refresh page
    page.reload()
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Re-open chat drawer (overlay on desktop may need re-opening)
    open_chat_drawer(page)

    # Verify structured messages are restored from history
    expect(chat_drawer.locator("text=蓝图草案已生成")).to_be_visible(timeout=15000)
    expect(chat_drawer.locator("text=请确认以下蓝图草案")).to_be_visible(timeout=15000)


def test_reviewing_refresh_restores_confirmable_state(page: Page, server_url: str) -> None:
    """After reaching reviewing and refreshing, both main content and ChatDrawer should show confirmable state."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_refresh_conf_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Start collecting
    page.locator("button", has_text="让 AI 生成蓝图").click()
    expect(page.locator("text=太棒了！让我来帮你")).to_be_visible(timeout=15000)

    # First user reply
    page.locator("textarea").fill("我想写一个3章的校园恋爱故事，主角是高中生")
    page.locator("button >> svg").last.click()
    expect(page.locator("text=收到")).to_be_visible(timeout=10000)

    # Second user reply
    page.locator("textarea").fill("视觉风格是日系动漫，氛围轻松治愈")
    page.locator("button >> svg").last.click()

    # Wait for reviewing
    chat_drawer = page.locator("[data-testid='chat-panel-docked']")
    expect(chat_drawer.locator("text=蓝图草案确认")).to_be_visible(timeout=15000)
    expect(page.locator("h2", has_text="蓝图草案已生成")).to_be_visible(timeout=10000)

    # Refresh page
    page.reload()
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Re-open chat drawer
    open_chat_drawer(page)

    # Verify confirmation panel is restored in ChatDrawer
    expect(chat_drawer.locator("text=蓝图草案确认")).to_be_visible(timeout=15000)
    expect(chat_drawer.locator("button", has_text="确认并生成")).to_be_visible(timeout=15000)
    expect(chat_drawer.locator("button", has_text="继续调整")).to_be_visible(timeout=15000)

    # Verify main content draft card is restored
    expect(page.locator("h2", has_text="蓝图草案已生成")).to_be_visible(timeout=10000)


def test_generating_refresh_restores_progress_state(page: Page, server_url: str) -> None:
    """After approving and entering generating, refreshing should restore generating state."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_refresh_gen_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Start collecting
    page.locator("button", has_text="让 AI 生成蓝图").click()
    expect(page.locator("text=太棒了！让我来帮你")).to_be_visible(timeout=15000)

    # First user reply
    page.locator("textarea").fill("我想写一个3章的校园恋爱故事，主角是高中生")
    page.locator("button >> svg").last.click()
    expect(page.locator("text=收到")).to_be_visible(timeout=10000)

    # Second user reply
    page.locator("textarea").fill("视觉风格是日系动漫，氛围轻松治愈")
    page.locator("button >> svg").last.click()

    # Wait for reviewing
    chat_drawer = page.locator("[data-testid='chat-panel-docked']")
    expect(chat_drawer.locator("text=蓝图草案确认")).to_be_visible(timeout=15000)

    # Approve from chat drawer
    confirmation_panel = chat_drawer.locator("[data-testid='chat-blueprint-confirmation']")
    confirmation_panel.locator("button", has_text="确认并生成").click()

    # Wait for first progress to appear, then immediately refresh
    expect(chat_drawer.locator("text=正在分析创作意图")).to_be_visible(timeout=15000)

    # Refresh page mid-generating
    page.reload()
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Re-open chat drawer
    open_chat_drawer(page)

    # Verify generating-related content is restored (at least one progress message from history)
    expect(chat_drawer.locator("text=正在分析创作意图")).to_be_visible(timeout=15000)


def test_main_content_blueprint_confirm_from_draft_card(page: Page, server_url: str) -> None:
    """Clicking '确认并生成' from main content BlueprintDraftCard should drive generating -> editing."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_main_conf_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Start collecting
    page.locator("button", has_text="让 AI 生成蓝图").click()
    expect(page.locator("text=太棒了！让我来帮你")).to_be_visible(timeout=15000)

    # First user reply
    page.locator("textarea").fill("我想写一个3章的校园恋爱故事，主角是高中生")
    page.locator("button >> svg").last.click()
    expect(page.locator("text=收到")).to_be_visible(timeout=10000)

    # Second user reply
    page.locator("textarea").fill("视觉风格是日系动漫，氛围轻松治愈")
    page.locator("button >> svg").last.click()

    # Wait for reviewing with draft card in main content
    onboarding_view = page.locator("[data-testid='workspace-onboarding-view']")
    expect(onboarding_view.locator("text=蓝图草案已生成")).to_be_visible(timeout=15000)
    expect(onboarding_view.locator("text=确认并生成")).to_be_visible(timeout=15000)

    # Click confirm from main content BlueprintDraftCard
    onboarding_view.locator("button", has_text="确认并生成").click()

    # Should show generating state
    expect(page.locator("text=正在生成蓝图")).to_be_visible(timeout=10000)

    # Eventually editing
    expect(page.locator("text=项目信息")).to_be_visible(timeout=20000)


def test_main_content_blueprint_reject_from_draft_card(page: Page, server_url: str) -> None:
    """Clicking '继续调整' from main content BlueprintDraftCard should return to collecting."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_main_rej_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Start collecting
    page.locator("button", has_text="让 AI 生成蓝图").click()
    expect(page.locator("text=太棒了！让我来帮你")).to_be_visible(timeout=15000)

    # First user reply
    page.locator("textarea").fill("我想写一个3章的校园恋爱故事，主角是高中生")
    page.locator("button >> svg").last.click()
    expect(page.locator("text=收到")).to_be_visible(timeout=10000)

    # Second user reply
    page.locator("textarea").fill("视觉风格是日系动漫，氛围轻松治愈")
    page.locator("button >> svg").last.click()

    # Wait for reviewing
    onboarding_view = page.locator("[data-testid='workspace-onboarding-view']")
    expect(onboarding_view.locator("text=蓝图草案已生成")).to_be_visible(timeout=15000)
    expect(onboarding_view.locator("text=继续调整")).to_be_visible(timeout=15000)

    # Click reject from main content BlueprintDraftCard
    onboarding_view.locator("button", has_text="继续调整").click()

    # Should return to collecting
    expect(page.locator("text=正在与 AI 细化需求")).to_be_visible(timeout=10000)

    # Should receive new assistant message from backend
    expect(page.locator("text=好的，我们继续调整蓝图")).to_be_visible(timeout=10000)


def test_mobile_main_content_confirm_works_when_chat_closed(page: Page, server_url: str) -> None:
    """On mobile with overlay drawer closed, clicking '确认并生成' from main content must still work."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_mob_conf_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.set_viewport_size({"width": 375, "height": 667})

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Start collecting
    page.locator("button", has_text="让 AI 生成蓝图").click()
    chat_drawer = page.locator("[data-testid='chat-drawer']")
    expect(chat_drawer).to_be_visible(timeout=10000)
    expect(chat_drawer.locator("text=太棒了！让我来帮你")).to_be_visible(timeout=15000)

    # Two interview turns
    page.locator("textarea").fill("我想写一个3章的校园恋爱故事")
    page.locator("button >> svg").last.click()
    expect(chat_drawer.locator("text=收到")).to_be_visible(timeout=10000)

    page.locator("textarea").fill("视觉风格是日系动漫")
    page.locator("button >> svg").last.click()

    # Wait for reviewing
    onboarding_view = page.locator("[data-testid='workspace-onboarding-view']")
    expect(onboarding_view.locator("text=蓝图草案已生成")).to_be_visible(timeout=15000)
    expect(onboarding_view.locator("text=确认并生成")).to_be_visible(timeout=15000)

    # Close chat drawer
    chat_drawer.locator("button[aria-label='Close chat']").click()
    # On mobile overlay the drawer slides out via translate-x-full but remains in DOM
    expect(chat_drawer).to_have_class(re.compile(r"translate-x-full"), timeout=5000)

    # Click confirm from main content while drawer is closed
    onboarding_view.locator("button", has_text="确认并生成").click()

    # Drawer should reopen and confirmation must go through to backend
    expect(chat_drawer).to_be_visible(timeout=5000)
    expect(page.locator("text=正在生成蓝图")).to_be_visible(timeout=10000)
    expect(page.locator("text=项目信息")).to_be_visible(timeout=20000)


def test_mobile_main_content_reject_works_when_chat_closed(page: Page, server_url: str) -> None:
    """On mobile with overlay drawer closed, clicking '继续调整' from main content must still work."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_mob_rej_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.set_viewport_size({"width": 375, "height": 667})

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Start collecting
    page.locator("button", has_text="让 AI 生成蓝图").click()
    chat_drawer = page.locator("[data-testid='chat-drawer']")
    expect(chat_drawer).to_be_visible(timeout=10000)
    expect(chat_drawer.locator("text=太棒了！让我来帮你")).to_be_visible(timeout=15000)

    # Two interview turns
    page.locator("textarea").fill("我想写一个3章的校园恋爱故事")
    page.locator("button >> svg").last.click()
    expect(chat_drawer.locator("text=收到")).to_be_visible(timeout=10000)

    page.locator("textarea").fill("视觉风格是日系动漫")
    page.locator("button >> svg").last.click()

    # Wait for reviewing
    onboarding_view = page.locator("[data-testid='workspace-onboarding-view']")
    expect(onboarding_view.locator("text=蓝图草案已生成")).to_be_visible(timeout=15000)
    expect(onboarding_view.locator("text=继续调整")).to_be_visible(timeout=15000)

    # Close chat drawer
    chat_drawer.locator("button[aria-label='Close chat']").click()
    # On mobile overlay the drawer slides out via translate-x-full but remains in DOM
    expect(chat_drawer).to_have_class(re.compile(r"translate-x-full"), timeout=5000)

    # Click reject from main content while drawer is closed
    onboarding_view.locator("button", has_text="继续调整").click()

    # Drawer should reopen and rejection must go through to backend
    expect(chat_drawer).to_be_visible(timeout=5000)
    expect(page.locator("text=正在与 AI 细化需求")).to_be_visible(timeout=10000)
    expect(page.locator("text=好的，我们继续调整蓝图")).to_be_visible(timeout=10000)


def test_return_to_collecting_allows_real_followup_refinement(
    page: Page, server_url: str
) -> None:
    """Clicking '继续调整' must allow real follow-up refinement, not immediate reviewing."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_ref_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Start collecting
    page.locator("button", has_text="让 AI 生成蓝图").click()
    expect(page.locator("text=太棒了！让我来帮你")).to_be_visible(timeout=15000)

    # First user reply
    page.locator("textarea").fill("我想写一个3章的校园恋爱故事，主角是高中生")
    page.locator("button >> svg").last.click()
    expect(page.locator("text=收到")).to_be_visible(timeout=10000)

    # Second user reply → enters reviewing
    page.locator("textarea").fill("视觉风格是日系动漫，氛围轻松治愈")
    page.locator("button >> svg").last.click()
    chat_drawer = page.locator("[data-testid='chat-panel-docked']")
    confirmation_panel = chat_drawer.locator("[data-testid='chat-blueprint-confirmation']")
    expect(confirmation_panel.locator("button", has_text="继续调整")).to_be_visible(timeout=15000)

    # Click "继续调整" in chat drawer
    confirmation_panel.locator("button", has_text="继续调整").click()

    # Should show collecting state
    expect(page.locator("text=正在与 AI 细化需求")).to_be_visible(timeout=10000)

    # Send a refinement input
    page.locator("textarea").fill("把主角改成大学生，增加一个反派角色")
    page.locator("button >> svg").last.click()

    # Should NOT immediately jump back to reviewing; should still be collecting
    # with a new AI response
    expect(page.locator("text=正在与 AI 细化需求")).to_be_visible(timeout=10000)
    expect(confirmation_panel).to_have_count(0, timeout=5000)

    # One more input can eventually bring us back to reviewing
    page.locator("textarea").fill("反派是学生会会长，暗中阻挠主角")
    page.locator("button >> svg").last.click()
    expect(confirmation_panel.locator("button", has_text="确认并生成")).to_be_visible(timeout=15000)


def test_manual_yaml_placeholder_resets_on_project_switch(
    page: Page, server_url: str
) -> None:
    """Manual YAML placeholder state must not leak across project switches."""
    assert wait_for_server(server_url), "Server not ready"

    project_a = f"playwright_leak_a_{int(time.time())}"
    project_b = f"playwright_leak_b_{int(time.time())}"
    create_project_via_api(server_url, project_a)
    create_project_via_api(server_url, project_b)

    # On project A: open manual YAML placeholder
    page.goto(f"{server_url}/dashboard/projects/{project_a}")
    expect(page.locator("h1")).to_have_text(project_a, timeout=30000)
    page.locator("button", has_text="手动准备 YAML（即将支持）").click()
    expect(page.locator("text=手动 YAML 编辑功能即将推出")).to_be_visible(timeout=10000)

    # Client-side navigate to project B
    _client_navigate_to_project(page, project_b)
    expect(page.locator("h1")).to_have_text(project_b, timeout=30000)

    # Project B should show its onboarding entry, NOT A's placeholder
    expect(page.locator("text=让 AI 生成蓝图")).to_be_visible(timeout=10000)
    expect(page.locator("text=手动准备 YAML（即将支持）")).to_be_visible(timeout=10000)
    expect(page.locator("text=手动 YAML 编辑功能即将推出")).to_have_count(0, timeout=5000)


def test_existing_blueprint_skips_onboarding(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Projects that already have a blueprint should skip onboarding and show workspace directly."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_skip_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Should NOT see onboarding
    expect(page.locator("text=让 AI 生成蓝图")).to_have_count(0, timeout=5000)
    expect(page.locator("text=项目已创建，开始构建蓝图吧")).to_have_count(0, timeout=5000)

    # Should see normal blueprint workspace
    expect(page.locator("text=Campus Romance")).to_be_visible(timeout=10000)
    expect(page.locator("text=项目信息")).to_be_visible(timeout=10000)


def test_workspace_existing_blueprint_does_not_fall_back_to_onboarding(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """A project with existing blueprint must enter editing workspace directly without flashing onboarding.

    Regression: if loadProjectData races or repeats, the page could briefly show
    onboarding (because blueprintPhase was not yet stable) and then get stuck there.
    """
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_stable_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)

    # Intercept snapshot APIs to keep loading state visible longer so we can
    # assert onboarding does not flash during the load window.
    pending_routes: list = []

    def handle_snapshot(route, request):
        url = request.url
        # Only hold the top-level snapshot endpoints, not sub-resources like /scenes/{id}/script
        if _is_top_level_snapshot_request(url):
            pending_routes.append(route)
            return
        route.continue_()

    page.route("**/api/projects/**", handle_snapshot)

    page.goto(f"{server_url}/dashboard/projects/{project_name}")

    # Poll until snapshot requests are captured (docked ChatDrawer increases mount time)
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if len(pending_routes) >= 1:
            break
        page.wait_for_timeout(50)

    # During the loading period, onboarding view must NOT appear
    assert page.locator("[data-testid='workspace-onboarding-view']").count() == 0, (
        "Onboarding view appeared during loading for a project with existing blueprint"
    )

    # Release all held snapshot requests
    while pending_routes:
        route = pending_routes.pop(0)
        route.continue_()

    # Allow any straggler script requests to be captured and released
    page.wait_for_timeout(800)
    while pending_routes:
        route = pending_routes.pop(0)
        route.continue_()

    # After loading completes, should be in editing workspace
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)
    expect(page.locator("[data-testid='workspace-onboarding-view']")).to_have_count(
        0, timeout=5000
    )
    expect(page.locator("text=Campus Romance")).to_be_visible(timeout=10000)
    expect(page.locator("text=项目信息")).to_be_visible(timeout=10000)


def test_project_switch_clears_confirmation_state(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Switching from a project with an active confirmation to a new project must not leak the confirmation state."""
    assert wait_for_server(server_url), "Server not ready"

    project_a = f"playwright_conf_switch_a_{int(time.time())}"
    project_b = f"playwright_conf_switch_b_{int(time.time())}"
    create_project_via_api(server_url, project_a)
    create_project_via_api(server_url, project_b)

    # Inject a reviewing session for project A so it shows confirmation panel
    session_path = e2e_workspace / project_a / "meta" / "blueprint_session.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps(
            {
                "pipeline_stage": "reviewing",
                "turn_count": 2,
                "awaiting_confirmation": True,
                "confirmation_id": "test-conf-switch-123",
                "updated_at": "2024-01-01T00:00:00",
                "draft": {
                    "title": project_a,
                    "genre": "校园恋爱",
                    "characters": [],
                    "chapters": [],
                },
            }
        ),
        encoding="utf-8",
    )

    page.goto(f"{server_url}/dashboard/projects/{project_a}")
    expect(page.locator("h1")).to_have_text(project_a, timeout=30000)

    chat_drawer = page.locator("[data-testid='chat-panel-docked']")
    # Project A should show confirmation panel
    expect(chat_drawer.locator("text=蓝图草案确认")).to_be_visible(timeout=10000)

    # Client-side navigate to project B
    _client_navigate_to_project(page, project_b)
    expect(page.locator("h1")).to_have_text(project_b, timeout=30000)

    # Project B must NOT show the old confirmation panel
    expect(chat_drawer.locator("text=蓝图草案确认")).to_have_count(0, timeout=5000)


def test_tool_confirmation_does_not_leak_on_project_switch(
    page: Page, server_url: str, mock_chat_server_url: str
) -> None:
    """A real awaiting_confirmation from /ws/chat in project A must not survive after switching to project B."""
    assert wait_for_server(server_url), "Server not ready"
    install_mock_chat_socket(page, mock_chat_server_url)

    project_a = f"playwright_tool_conf_a_{int(time.time())}"
    project_b = f"playwright_tool_conf_b_{int(time.time())}"
    create_project_via_api(server_url, project_a)
    create_project_via_api(server_url, project_b)

    page.goto(f"{server_url}/dashboard/projects/{project_a}")
    expect(page.locator("h1")).to_have_text(project_a, timeout=30000)

    chat_drawer = page.locator("[data-testid='chat-panel-docked']")

    # Open chat and send a message to trigger the mock WS awaiting_confirmation
    open_chat_drawer(page)
    page.locator("textarea").fill("generate a courtyard background")
    click_send_button(page)

    # Wait for the real awaiting_confirmation panel to appear
    expect(chat_drawer.locator("text=Mock background ready to save.")).to_be_visible(timeout=10000)

    # Client-side navigate to project B
    _client_navigate_to_project(page, project_b)
    expect(page.locator("h1")).to_have_text(project_b, timeout=30000)

    # The old tool confirmation panel must NOT survive the switch
    expect(chat_drawer.locator("text=Mock background ready to save.")).to_have_count(0, timeout=5000)


def test_missing_project_shows_error_state(page: Page, server_url: str) -> None:
    """Accessing a non-existent project workspace should show a clear error instead of an empty onboarding shell."""
    assert wait_for_server(server_url), "Server not ready"

    page.goto(f"{server_url}/dashboard/projects/fake-missing-project")

    # Should remain on the requested route (not silently redirected)
    expect(page).to_have_url(f"{server_url}/dashboard/projects/fake-missing-project")

    # Should show error state with "Project not found" message
    expect(page.locator("text=Project not found")).to_be_visible(timeout=15000)

    # Onboarding entry must NOT appear
    expect(page.locator("text=让 AI 生成蓝图")).to_have_count(0, timeout=5000)

    # Normal workspace sidebar must NOT appear
    expect(page.locator("[data-testid='workspace-sidebar']")).to_have_count(0, timeout=5000)


def test_missing_project_with_different_error_detail(page: Page, server_url: str) -> None:
    """A missing project must surface the error state even when the backend uses an unexpected detail message."""
    assert wait_for_server(server_url), "Server not ready"

    # Intercept /api/projects/select to return 404 with a non-standard detail message
    page.route(
        f"{server_url}/api/projects/select",
        lambda route, request: route.fulfill(
            status=404,
            content_type="application/json",
            body='{"detail": "No such project here"}',
        ),
    )

    page.goto(f"{server_url}/dashboard/projects/unknown-project")

    # Should remain on the requested route
    expect(page).to_have_url(f"{server_url}/dashboard/projects/unknown-project")

    # Should still show error state (driven by 404 status, not detail string)
    expect(page.locator("text=Project not found")).to_be_visible(timeout=15000)

    # Onboarding and workspace must not appear
    expect(page.locator("text=让 AI 生成蓝图")).to_have_count(0, timeout=5000)
    expect(page.locator("[data-testid='workspace-sidebar']")).to_have_count(0, timeout=5000)


def test_tool_confirmation_refresh_restores_panel_from_session(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Low-level: frontend can recover confirmation panel from an injected runtime session file."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_tool_refresh_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    # Inject a tool workflow runtime session to simulate an in-flight confirmation
    session_path = e2e_workspace / project_name / "meta" / "blueprint_session.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps(
            {
                "active_workflow": "tool",
                "pipeline_stage": "awaiting_confirmation",
                "awaiting_confirmation": True,
                "confirmation_id": "test-tool-refresh-123",
                "confirmation_message": "请确认生成此背景图",
                "confirmation_candidates": [
                    {"type": "image", "path": "game/images/background/test.png"}
                ],
                "tool_name": "generate_background",
                "updated_at": "2024-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    chat_drawer = page.locator("[data-testid='chat-panel-docked']")
    # Confirmation panel should be visible from session recovery
    expect(chat_drawer.locator("text=请确认生成此背景图")).to_be_visible(timeout=10000)

    # Refresh page
    page.reload()
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Confirmation panel must still be visible after refresh
    expect(chat_drawer.locator("text=请确认生成此背景图")).to_be_visible(timeout=10000)


def test_tool_confirmation_refresh_restores_panel(
    page: Page, e2e_workspace: Path
) -> None:
    """Real backend path: /ws/chat -> awaiting_confirmation -> session write -> refresh -> panel recovery."""
    url, proc = start_mock_llm_server(e2e_workspace)
    try:
        assert wait_for_server(url), "Server not ready"

        project_name = f"playwright_tool_real_{int(time.time())}"
        create_project_via_api(url, project_name)
        # Seed a blueprint so the project enters editing mode and bypasses the blueprint orchestrator
        _seed_project_blueprint(e2e_workspace, project_name)

        page.goto(f"{url}/dashboard/projects/{project_name}")
        expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

        chat_drawer = page.locator("[data-testid='chat-panel-docked']")

        # Open chat and send a message that triggers real backend tool confirmation
        open_chat_drawer(page)
        page.locator("textarea").fill("generate a background of a Japanese courtyard")
        click_send_button(page)

        # Wait for real awaiting_confirmation from backend (generate_background confirmation message)
        expect(chat_drawer.locator("text=已生成背景图，请确认是否保存。")).to_be_visible(timeout=10000)

        # Refresh page
        page.reload()
        expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

        # Confirmation panel must still be visible after refresh (recovered from runtime session)
        expect(chat_drawer.locator("text=已生成背景图，请确认是否保存。")).to_be_visible(timeout=10000)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def test_tool_running_refresh_restores_progress_state(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """A tool_running runtime session should recover as generic workflow progress, not blueprint phase."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_tool_run_{int(time.time())}"
    create_project_via_api(server_url, project_name)

    # Inject a tool-running runtime session
    session_path = e2e_workspace / project_name / "meta" / "blueprint_session.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps(
            {
                "active_workflow": "tool",
                "pipeline_stage": "tool_running",
                "awaiting_confirmation": False,
                "latest_progress": {"step": "正在调用 generate_background...", "percent": 0},
                "tool_name": "generate_background",
                "updated_at": "2024-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Must NOT show blueprint reviewing / generating / collecting UI
    # (onboarding is OK for a project without blueprint)
    expect(page.locator("text=蓝图草案已生成")).to_have_count(0, timeout=5000)
    expect(page.locator("text=正在生成蓝图")).to_have_count(0, timeout=5000)
    expect(page.locator("text=正在与 AI 细化需求")).to_have_count(0, timeout=5000)

    # Chat drawer should show the recovered progress step
    chat_drawer = page.locator("[data-testid='chat-panel-docked']")
    expect(chat_drawer.locator("text=正在调用 generate_background...")).to_be_visible(timeout=10000)

    # Refresh page
    page.reload()
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # After refresh, must still NOT show blueprint reviewing / generating UI
    expect(page.locator("text=蓝图草案已生成")).to_have_count(0, timeout=5000)
    expect(page.locator("text=正在生成蓝图")).to_have_count(0, timeout=5000)

    # Progress must still be visible
    expect(chat_drawer.locator("text=正在调用 generate_background...")).to_be_visible(timeout=10000)


def test_editing_project_with_tool_confirmation_stays_in_editing_mode_after_refresh(
    page: Page, e2e_workspace: Path
) -> None:
    """Editing project with active tool confirmation must stay in editing workspace after refresh."""
    url, proc = start_mock_llm_server(e2e_workspace)
    try:
        assert wait_for_server(url), "Server not ready"

        project_name = f"playwright_tool_edit_conf_{int(time.time())}"
        create_project_via_api(url, project_name)
        _seed_project_blueprint(e2e_workspace, project_name)

        page.goto(f"{url}/dashboard/projects/{project_name}")
        expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

        # Must start in editing workspace (not onboarding)
        expect(page.locator("[data-testid='workspace-sidebar']")).to_be_visible(timeout=10000)
        expect(page.locator("button", has_text="蓝图")).to_be_visible(timeout=10000)
        expect(page.locator("[data-testid='workspace-onboarding-view']")).to_have_count(0, timeout=5000)

        chat_drawer = page.locator("[data-testid='chat-panel-docked']")

        # Trigger real backend tool confirmation
        open_chat_drawer(page)
        page.locator("textarea").fill("generate a background of a Japanese courtyard")
        click_send_button(page)

        # Wait for confirmation panel
        expect(chat_drawer.locator("text=已生成背景图，请确认是否保存。")).to_be_visible(timeout=10000)

        # Must STAY in editing workspace while confirmation is active
        expect(page.locator("[data-testid='workspace-sidebar']")).to_be_visible(timeout=10000)
        expect(page.locator("button", has_text="蓝图")).to_be_visible(timeout=10000)
        expect(page.locator("[data-testid='workspace-onboarding-view']")).to_have_count(0, timeout=5000)

        # Refresh page
        page.reload()
        expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

        # After refresh, must STILL be in editing workspace
        expect(page.locator("[data-testid='workspace-sidebar']")).to_be_visible(timeout=10000)
        expect(page.locator("button", has_text="蓝图")).to_be_visible(timeout=10000)
        expect(page.locator("[data-testid='workspace-onboarding-view']")).to_have_count(0, timeout=5000)

        # Confirmation panel must still be recovered
        expect(chat_drawer.locator("text=已生成背景图，请确认是否保存。")).to_be_visible(timeout=10000)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def test_editing_project_with_tool_running_stays_in_editing_mode_after_refresh(
    page: Page, server_url: str, e2e_workspace: Path
) -> None:
    """Editing project with tool_running session must stay in editing workspace after refresh."""
    assert wait_for_server(server_url), "Server not ready"

    project_name = f"playwright_tool_edit_run_{int(time.time())}"
    create_project_via_api(server_url, project_name)
    _seed_project_blueprint(e2e_workspace, project_name)

    # Inject a tool-running runtime session
    session_path = e2e_workspace / project_name / "meta" / "blueprint_session.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps(
            {
                "active_workflow": "tool",
                "pipeline_stage": "tool_running",
                "awaiting_confirmation": False,
                "latest_progress": {"step": "正在调用 generate_background...", "percent": 0},
                "tool_name": "generate_background",
                "updated_at": "2024-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    page.goto(f"{server_url}/dashboard/projects/{project_name}")
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # Must stay in editing workspace (not onboarding)
    expect(page.locator("[data-testid='workspace-sidebar']")).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="蓝图")).to_be_visible(timeout=10000)
    expect(page.locator("[data-testid='workspace-onboarding-view']")).to_have_count(0, timeout=5000)

    # Chat drawer should show the recovered progress step
    chat_drawer = page.locator("[data-testid='chat-panel-docked']")
    expect(chat_drawer.locator("text=正在调用 generate_background...")).to_be_visible(timeout=10000)

    # Refresh page
    page.reload()
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)

    # After refresh, must still stay in editing workspace
    expect(page.locator("[data-testid='workspace-sidebar']")).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="蓝图")).to_be_visible(timeout=10000)
    expect(page.locator("[data-testid='workspace-onboarding-view']")).to_have_count(0, timeout=5000)

    # Progress must still be visible
    expect(chat_drawer.locator("text=正在调用 generate_background...")).to_be_visible(timeout=10000)
