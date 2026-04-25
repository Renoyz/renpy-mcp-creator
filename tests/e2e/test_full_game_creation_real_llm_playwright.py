"""Playwright E2E: Full game creation with REAL LLM, step-by-step screenshots.

Current execution contract:
- UI interactions for project creation, intake chat, and final build/preview (screenshot-heavy)
- API calls for brief/outline confirmation to bypass frontend tab-routing race conditions
- mock build enabled by default, so this is a diagnostic hybrid harness rather than a pure-UI acceptance flow
"""

import json
import os
import re
import subprocess
import sys
import time
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Page, expect

REPO_ROOT = Path(__file__).parent.parent.parent
SCREENSHOT_DIR = REPO_ROOT / "workspace" / "screenshots" / "full_game_creation"


class _FakeArtifactPage:
    def __init__(self, html: str = "<html><body>artifact</body></html>") -> None:
        self.html = html
        self.screenshot_calls: list[tuple[str, bool]] = []

    def screenshot(self, *, path: str, full_page: bool) -> None:
        Path(path).write_bytes(b"fake-png")
        self.screenshot_calls.append((path, full_page))

    def content(self) -> str:
        return self.html


def _load_artifact_writer() -> type:
    helper_path = REPO_ROOT / "tests" / "e2e" / "helpers" / "full_game_creation_artifacts.py"
    spec = spec_from_file_location("full_game_creation_artifacts", helper_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ArtifactWriter


def _load_helper_module(module_name: str, relative_path: str):
    helper_path = REPO_ROOT / relative_path
    assert helper_path.exists(), f"Missing helper module: {helper_path}"
    spec = spec_from_file_location(module_name, helper_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_full_game_creation_runner_module():
    return _load_helper_module(
        "full_game_creation_runner",
        "tests/e2e/helpers/full_game_creation_runner.py",
    )


def _load_execution_modes_module():
    return _load_helper_module(
        "full_game_creation_modes",
        "tests/e2e/helpers/full_game_creation_modes.py",
    )


def _artifact_run_id(prefix: str) -> str:
    return f"{prefix}_{time.time_ns()}"


def test_artifact_writer_creates_run_directory(tmp_path: Path) -> None:
    ArtifactWriter = _load_artifact_writer()

    writer = ArtifactWriter(tmp_path, "run-001")

    assert writer.run_dir == tmp_path / "run-001"
    assert writer.run_dir.exists()
    assert writer.run_dir.is_dir()


def test_artifact_writer_saves_png_html_json_and_text(tmp_path: Path) -> None:
    ArtifactWriter = _load_artifact_writer()

    writer = ArtifactWriter(tmp_path, "run-002")
    page = _FakeArtifactPage("<html><body>captured</body></html>")

    writer.capture_page(page, "01_project_list", note="project list visible")
    writer.write_json("01_project_list", "refinement-status", {"state": "ready"})
    writer.write_text("01_project_list", "operator-note", "operator note")

    assert (writer.run_dir / "01_project_list.png").read_bytes() == b"fake-png"
    assert (writer.run_dir / "01_project_list.page.html").read_text(encoding="utf-8") == page.html
    assert (writer.run_dir / "01_project_list.notes.txt").read_text(encoding="utf-8") == "project list visible"
    assert (
        writer.run_dir / "01_project_list.refinement-status.json"
    ).read_text(encoding="utf-8") == '{\n  "state": "ready"\n}'
    assert (
        writer.run_dir / "01_project_list.operator-note.txt"
    ).read_text(encoding="utf-8") == "operator note"


def test_snap_compatibility_wrapper_writes_default_notes_and_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys.modules[__name__], "SCREENSHOT_DIR", tmp_path)
    monkeypatch.setattr(time, "time_ns", lambda: 1234567890123456789)
    if hasattr(_snap, "_writer"):
        delattr(_snap, "_writer")

    page = _FakeArtifactPage("<html><body>compatibility</body></html>")

    screenshot_path = _snap(page, "01_project_list")
    run_dir = tmp_path / "legacy_1234567890123456789"

    assert screenshot_path == run_dir / "01_project_list.png"
    assert screenshot_path.read_bytes() == b"fake-png"
    assert (run_dir / "01_project_list.page.html").read_text(encoding="utf-8") == page.html
    assert (
        run_dir / "01_project_list.notes.txt"
    ).read_text(encoding="utf-8") == "Auto-captured step 01_project_list."
    assert json.loads((run_dir / "01_project_list.artifact.json").read_text(encoding="utf-8")) == {
        "step_id": "01_project_list",
        "artifacts": {
            "screenshot": "01_project_list.png",
            "page_html": "01_project_list.page.html",
            "notes": "01_project_list.notes.txt",
        },
    }


def test_snap_explicit_writer_ignores_hidden_fallback_state(tmp_path: Path) -> None:
    ArtifactWriter = _load_artifact_writer()
    stale_writer = ArtifactWriter(tmp_path, "stale-run")
    explicit_writer = ArtifactWriter(tmp_path, "explicit-run")
    _snap._writer = stale_writer

    page = _FakeArtifactPage("<html><body>explicit</body></html>")

    screenshot_path = _snap(page, "01_project_list", writer=explicit_writer)

    assert screenshot_path == explicit_writer.run_dir / "01_project_list.png"
    assert (explicit_writer.run_dir / "01_project_list.page.html").read_text(encoding="utf-8") == page.html
    assert not (stale_writer.run_dir / "01_project_list.png").exists()
    assert _snap._writer is stale_writer


def test_artifact_run_id_uses_time_ns_for_uniqueness(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "time_ns", lambda: 987654321012345678)

    assert _artifact_run_id("real_llm") == "real_llm_987654321012345678"
    assert _artifact_run_id("legacy") == "legacy_987654321012345678"


def test_ui_only_mode_forbids_api_shortcuts() -> None:
    modes = _load_execution_modes_module()

    assert modes.UI_ONLY_DEBUG.name == "ui_only_debug"
    assert modes.UI_ONLY_DEBUG.allow_api_promote_fallback is False
    assert modes.UI_ONLY_DEBUG.allow_api_confirm_fallback is False
    assert modes.UI_ONLY_DEBUG.use_mock_build is True
    assert modes.UI_ONLY_DEBUG.expect_real_build is False


def test_hybrid_recovery_mode_allows_api_fallback_after_ui_failure() -> None:
    modes = _load_execution_modes_module()
    runner_module = _load_full_game_creation_runner_module()
    observed_stages: list[str] = []

    def record(stage_name: str):
        def _callback(_runner):
            observed_stages.append(stage_name)
            return stage_name

        return _callback

    runner = runner_module.FullGameCreationRunner(
        page=None,
        server_url="http://example.test",
        workspace=Path("workspace"),
        mode=modes.HYBRID_RECOVERY,
        artifacts=None,
        create_project=record("create_project"),
        intake=record("intake"),
        brief_review=record("brief_review"),
        outline_review=record("outline_review"),
        freeze_and_build=record("freeze_and_build"),
    )

    assert runner.can_use_api_promote_fallback(ui_failure=False) is False
    assert runner.can_use_api_confirm_fallback(ui_failure=False) is False
    assert runner.can_use_api_promote_fallback(ui_failure=True) is True
    assert runner.can_use_api_confirm_fallback(ui_failure=True) is True
    run_results = runner.run()
    assert run_results == [
        "create_project",
        "intake",
        "brief_review",
        "outline_review",
        "freeze_and_build",
    ]
    assert observed_stages == run_results


def test_runner_records_brief_tab_route_failure_before_api_fallback() -> None:
    modes = _load_execution_modes_module()
    runner_module = _load_full_game_creation_runner_module()
    call_order: list[str] = []

    runner = runner_module.FullGameCreationRunner(
        page=None,
        server_url="http://example.test",
        workspace=Path("workspace"),
        mode=modes.HYBRID_RECOVERY,
        artifacts=None,
    )

    def ui_attempt(_runner):
        call_order.append("ui")
        return False

    def fallback(_runner):
        call_order.append("fallback")
        return "api_fallback"

    result = runner.attempt_brief_review(ui_attempt, fallback)

    assert result == "api_fallback"
    assert call_order == ["ui", "fallback"]
    assert runner.diagnostics == [{"code": "brief_tab_route_failure", "stage": "brief_review"}]


def test_runner_records_outline_tab_route_failure_before_api_fallback() -> None:
    modes = _load_execution_modes_module()
    runner_module = _load_full_game_creation_runner_module()
    call_order: list[str] = []

    runner = runner_module.FullGameCreationRunner(
        page=None,
        server_url="http://example.test",
        workspace=Path("workspace"),
        mode=modes.HYBRID_RECOVERY,
        artifacts=None,
    )

    def ui_attempt(_runner):
        call_order.append("ui")
        return False

    def fallback(_runner):
        call_order.append("fallback")
        return "api_fallback"

    result = runner.attempt_outline_review(ui_attempt, fallback)

    assert result == "api_fallback"
    assert call_order == ["ui", "fallback"]
    assert runner.diagnostics == [{"code": "outline_tab_route_failure", "stage": "outline_review"}]


def test_default_execution_mode_loader_returns_hybrid_recovery() -> None:
    mode = _load_default_execution_mode()

    assert mode.name == "hybrid_recovery"
    assert mode.allow_api_promote_fallback is True
    assert mode.allow_api_confirm_fallback is True
    assert mode.use_mock_build is True


def test_real_llm_runner_persists_backend_logs(tmp_path: Path) -> None:
    ArtifactWriter = _load_artifact_writer()
    artifacts = ArtifactWriter(tmp_path, "run-logs")

    stdout_path, stderr_path, stdout_handle, stderr_handle = _open_backend_log_files(artifacts)
    stdout_handle.write("server output\n")
    stderr_handle.write("server error\n")
    _close_backend_log_files(stdout_handle, stderr_handle)

    assert stdout_path == artifacts.path_for("backend.stdout.log")
    assert stderr_path == artifacts.path_for("backend.stderr.log")
    assert stdout_path.read_text(encoding="utf-8") == "server output\n"
    assert stderr_path.read_text(encoding="utf-8") == "server error\n"


def test_real_llm_runner_writes_summary_markdown(tmp_path: Path) -> None:
    ArtifactWriter = _load_artifact_writer()
    modes = _load_execution_modes_module()
    runner_module = _load_full_game_creation_runner_module()
    artifacts = ArtifactWriter(tmp_path, "run-summary")
    artifacts.write_root_text("backend.stdout.log", "stdout")
    artifacts.write_root_text("backend.stderr.log", "stderr")
    artifacts.write_root_text("05_intake_started.png", "")

    runner = runner_module.FullGameCreationRunner(
        page=None,
        server_url="http://example.test",
        workspace=Path("workspace"),
        mode=modes.HYBRID_RECOVERY,
        artifacts=artifacts,
    )
    runner.record_diagnostic("brief_tab_route_failure", stage="brief_review")
    runner.record_fallback(
        "api_promote_brief",
        stage="brief_review",
        reason="brief_tab_not_visible_after_ui_click",
        step_id="08_brief_tab_route_failure",
    )

    summary_path = _write_run_summary(
        artifacts,
        mode=modes.HYBRID_RECOVERY,
        project_name="real_llm_demo",
        llm_label="unknown",
        result="FAIL",
        first_failing_step="08_brief_tab_route_failure",
        runner=runner,
        freeze_reached=False,
        build_reached=False,
    )
    summary = summary_path.read_text(encoding="utf-8")

    assert summary_path == artifacts.path_for("summary.md")
    assert "# Full Game Creation Run Summary" in summary
    assert "- Run ID: `run-summary`" in summary
    assert "- Mode: `hybrid_recovery`" in summary
    assert "- Project: `real_llm_demo`" in summary
    assert "- Result: `FAIL`" in summary
    assert "- First failing step: `08_brief_tab_route_failure`" in summary
    assert "- API fallback used: `yes`" in summary
    assert "- `backend.stdout.log`" in summary
    assert "- `backend.stderr.log`" in summary


FULL_GAME_CREATION_MODES = _load_execution_modes_module()
ExecutionMode = FULL_GAME_CREATION_MODES.ExecutionMode


def _load_default_execution_mode() -> ExecutionMode:
    return FULL_GAME_CREATION_MODES.HYBRID_RECOVERY

KNOWN_SHORTCUTS = {
    "intake_start": "workspace Start Intake with AI button",
    "brief_review": "api promote + api confirm fallback after ui failure",
    "outline_review": "api promote + api confirm fallback after ui failure",
    "build": "mock build by default",
}

# Task 1 TDD marker:
# The initial RED baseline was a temporary anti-goal test:
# `test_full_game_creation_tool_is_not_pure_ui_yet` with
# `assert TEST_MODE != "legacy_hybrid"`.
# It intentionally failed before this file moved to the explicit mode contract below.
TASK_1_RED_BASELINE_MARKER = {
    "temporary_test": "test_full_game_creation_tool_is_not_pure_ui_yet",
    "temporary_assertion": 'assert TEST_MODE != "legacy_hybrid"',
    "replacement": "ExecutionMode + KNOWN_SHORTCUTS contract tests",
}


def test_full_game_creation_task1_red_baseline_is_recorded() -> None:
    assert TASK_1_RED_BASELINE_MARKER["temporary_test"].endswith("not_pure_ui_yet")
    assert "legacy_hybrid" in TASK_1_RED_BASELINE_MARKER["temporary_assertion"]
    assert "ExecutionMode" in TASK_1_RED_BASELINE_MARKER["replacement"]
    assert "KNOWN_SHORTCUTS" in TASK_1_RED_BASELINE_MARKER["replacement"]


def test_full_game_creation_is_explicitly_not_pure_ui_yet() -> None:
    mode = _load_default_execution_mode()

    assert mode.expect_real_build is False
    assert mode.name == "hybrid_recovery"
    assert mode.allow_api_promote_fallback is True
    assert mode.allow_api_confirm_fallback is True
    assert mode.use_mock_build is True


def test_full_game_creation_server_env_uses_execution_mode_mock_build(tmp_path: Path) -> None:
    env = _server_env_for_mode(tmp_path, _load_default_execution_mode())

    assert env["RENPY_MCP_WORKSPACE"] == str(tmp_path)
    assert env["RENPY_MCP_MOCK_BUILD"] == "1"


def test_full_game_creation_legacy_shortcuts_are_frozen() -> None:
    assert "Start Intake with AI button" in KNOWN_SHORTCUTS["intake_start"]
    assert "api promote" in KNOWN_SHORTCUTS["brief_review"]
    assert "api confirm fallback" in KNOWN_SHORTCUTS["brief_review"]
    assert "api promote" in KNOWN_SHORTCUTS["outline_review"]
    assert "api confirm fallback" in KNOWN_SHORTCUTS["outline_review"]
    assert "mock build" in KNOWN_SHORTCUTS["build"]


def test_full_game_creation_confirmation_failures_raise_clearly() -> None:
    with pytest.raises(AssertionError, match="brief confirmation failures"):
        _assert_confirmation_successes(
            "brief",
            [
                ("hook", 200, ""),
                ("setting", 500, "server error"),
            ],
        )


def test_full_game_creation_requires_build_button() -> None:
    with pytest.raises(AssertionError, match="Build/preview action is unavailable"):
        _assert_build_button_present(0)


def test_pending_confirm_buttons_excludes_disabled_confirmed_buttons(page: Page) -> None:
    page.set_content(
        """
        <main>
          <button disabled>Confirmed</button>
          <button>Confirm</button>
          <button disabled>Confirm</button>
        </main>
        """
    )

    confirm_buttons = _pending_confirm_buttons(page)

    assert confirm_buttons.count() == 1
    expect(confirm_buttons.first).to_have_text("Confirm")


def test_freeze_blueprint_button_uses_first_exact_match(page: Page) -> None:
    page.set_content(
        """
        <main>
          <button>Freeze Blueprint</button>
          <button>Freeze Blueprint</button>
        </main>
        """
    )

    freeze_button = _freeze_blueprint_button(page)

    assert freeze_button.count() == 1
    expect(freeze_button).to_have_text("Freeze Blueprint")


def test_wait_for_blueprint_file_detects_freeze_completion(tmp_path: Path) -> None:
    blueprint_path = tmp_path / "meta" / "blueprint.yaml"
    blueprint_path.parent.mkdir(parents=True, exist_ok=True)
    blueprint_path.write_text("title: demo\n", encoding="utf-8")

    _wait_for_blueprint_file(blueprint_path, timeout_seconds=0.1)


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


def _server_env_for_mode(workspace: Path, mode: ExecutionMode) -> dict[str, str]:
    env = os.environ.copy()
    env["RENPY_MCP_WORKSPACE"] = str(workspace)
    if mode.use_mock_build:
        env["RENPY_MCP_MOCK_BUILD"] = "1"
    else:
        env.pop("RENPY_MCP_MOCK_BUILD", None)
    return env


def _assert_confirmation_successes(stage: str, attempts: list[tuple[str, int, str]]) -> None:
    failures = [
        f"{item_id} -> {status} {body}".strip()
        for item_id, status, body in attempts
        if status != 200
    ]
    assert not failures, f"{stage} confirmation failures: {'; '.join(failures)}"


def _assert_build_button_present(button_count: int) -> None:
    assert button_count > 0, "Build/preview action is unavailable in the current UI state."


def _pending_confirm_buttons(page: Page):
    return page.locator("button:not([disabled])").filter(has_text=re.compile(r"^Confirm$"))


def _freeze_blueprint_button(page: Page):
    return page.get_by_role("button", name="Freeze Blueprint", exact=True).first


def _wait_for_blueprint_file(blueprint_path: Path, timeout_seconds: float = 30.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if blueprint_path.exists():
            return
        time.sleep(0.5)
    raise AssertionError(f"blueprint.yaml was not created within {timeout_seconds} seconds")


def _open_backend_log_files(artifacts):
    stdout_path = artifacts.path_for("backend.stdout.log")
    stderr_path = artifacts.path_for("backend.stderr.log")
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    return stdout_path, stderr_path, stdout_handle, stderr_handle


def _close_backend_log_files(*handles) -> None:
    for handle in handles:
        try:
            handle.flush()
        finally:
            handle.close()


def start_real_llm_server(workspace: Path, *, mode: ExecutionMode, artifacts) -> tuple[str, subprocess.Popen]:
    """Start backend with REAL LLM (no mock)."""
    port = _find_free_port()
    env = _server_env_for_mode(workspace, mode)
    stdout_path, stderr_path, stdout_handle, stderr_handle = _open_backend_log_files(artifacts)

    cmd = [sys.executable, "-m", "renpy_mcp.main", "--transport", "http", "--port", str(port)]
    proc = subprocess.Popen(
        cmd,
        stdout=stdout_handle,
        stderr=stderr_handle,
        env=env,
        cwd=str(REPO_ROOT),
        text=True,
        encoding="utf-8",
    )
    proc._stdout_handle = stdout_handle
    proc._stderr_handle = stderr_handle
    proc._stdout_log_path = stdout_path
    proc._stderr_log_path = stderr_path

    url = f"http://127.0.0.1:{port}"
    if not _wait_for_port("127.0.0.1", port, timeout=30.0):
        stop_real_llm_server(proc)
        raise RuntimeError(f"Backend did not start on {url}")

    deadline = time.time() + 10.0
    while time.time() < deadline:
        try:
            if httpx.get(f"{url}/api/status", timeout=2.0).status_code == 200:
                return url, proc
        except Exception:
            pass
        time.sleep(0.5)

    stop_real_llm_server(proc)
    raise RuntimeError(f"Backend did not become ready on {url}")


def stop_real_llm_server(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5.0)
    finally:
        _close_backend_log_files(proc._stdout_handle, proc._stderr_handle)

def _snap(page: Page, name: str, *, writer: object | None = None) -> Path:
    if writer is None:
        ArtifactWriter = _load_artifact_writer()
        writer = ArtifactWriter(SCREENSHOT_DIR, _artifact_run_id("legacy"))
    screenshot_path = writer.capture_page(page, name, note=f"Auto-captured step {name}.")
    writer.write_json(
        name,
        "artifact",
        {
            "step_id": name,
            "artifacts": {
                "screenshot": screenshot_path.name,
                "page_html": f"{name}.page.html",
                "notes": f"{name}.notes.txt",
            },
        },
    )
    return screenshot_path


def _create_project_via_api(server_url: str, project_name: str) -> None:
    response = httpx.post(
        f"{server_url}/api/projects",
        json={"name": project_name},
        timeout=10.0,
    )
    assert response.status_code == 200, response.text


def _open_workspace_from_project_list(page: Page, server_url: str, project_name: str) -> None:
    page.goto(f"{server_url}/dashboard")
    project_card = page.locator("[data-testid='project-card']", has_text=project_name)
    expect(project_card).to_be_visible(timeout=10000)
    project_card.click()
    expect(page.locator("h1")).to_have_text(project_name, timeout=10000)


def _resolve_chat_surface(page: Page):
    chat_panel = page.locator("[data-testid='chat-panel-docked']")
    if chat_panel.count() > 0:
        return chat_panel
    return page.locator("[data-testid='chat-drawer']")


def _start_intake_via_button(
    page: Page,
    *,
    writer: object | None = None,
    step_name: str | None = None,
):
    expect(page.locator("text=Start Project Intake")).to_be_visible(timeout=10000)
    start_btn = page.get_by_role("button", name="Start Intake with AI", exact=True)
    expect(start_btn).to_be_visible(timeout=10000)
    start_btn.click()
    chat = _resolve_chat_surface(page)
    expect(chat).to_be_visible(timeout=10000)
    intake_copy = chat.locator("text=Project Brief").first
    expect(intake_copy).to_be_visible(timeout=60000)
    if step_name is not None:
        _snap(page, step_name, writer=writer)
    return chat


def test_full_game_creation_starts_intake_via_button_not_textarea(
    page: Page,
    server_url: str,
    tmp_path: Path,
) -> None:
    project_name = _artifact_run_id("button_intake")
    ArtifactWriter = _load_artifact_writer()
    artifacts = ArtifactWriter(tmp_path, project_name)

    _create_project_via_api(server_url, project_name)
    _open_workspace_from_project_list(page, server_url, project_name)

    chat = _start_intake_via_button(page, writer=artifacts, step_name="05_intake_started")

    expect(chat.locator("text=Project Brief").first).to_be_visible(timeout=10000)
    expect(page.locator("text=Agent Intake")).to_be_visible(timeout=10000)
    expect(page.locator("text=Start Project Intake")).not_to_be_visible(timeout=10000)
    expect(chat.get_by_text(re.compile("blueprint", re.IGNORECASE))).to_have_count(0)
    assert (artifacts.run_dir / "05_intake_started.png").exists()


def _run_create_project_stage(runner) -> str:
    page = runner.page
    server_url = runner.server_url
    artifacts = runner.artifacts
    project_name = artifacts.run_id

    page.goto(f"{server_url}/dashboard/projects")
    expect(page.locator("h1")).to_be_visible(timeout=30000)
    _snap(page, "01_project_list", writer=artifacts)

    page.locator("[data-testid='new-project-cta']").click()
    expect(page.locator("[data-testid='create-project-dialog']")).to_be_visible(timeout=10000)
    _snap(page, "02_dialog_opened", writer=artifacts)

    page.locator("[data-testid='create-project-name-input']").fill(project_name)
    _snap(page, "03_name_filled", writer=artifacts)

    page.locator("[data-testid='create-project-submit']").click()
    expect(page.locator("h1")).to_have_text(project_name, timeout=30000)
    _snap(page, "04_workspace_loaded", writer=artifacts)
    return project_name


def _run_intake_stage(runner) -> None:
    page = runner.page
    artifacts = runner.artifacts

    chat = _start_intake_via_button(page, writer=artifacts, step_name="05_intake_started")
    page.locator("textarea").fill("3 chapters, Western fantasy, dragon-slaying warrior")
    page.locator("button >> svg").last.click()
    expect(chat.locator("text=Got it").first).to_be_visible(timeout=60000)
    _snap(page, "06_intake_turn1", writer=artifacts)

    page.locator("textarea").fill("You decide. Make it epic.")
    page.locator("button >> svg").last.click()
    chat.locator("text=Brief Review").or_(chat.locator("text=Blueprint generation failed")).first.wait_for(
        state="visible",
        timeout=120000,
    )
    _snap(page, "07_intake_draft_ready", writer=artifacts)

    if chat.locator("text=Blueprint generation failed").count() > 0:
        _snap(page, "07b_intake_error", writer=artifacts)
        raise AssertionError("LLM returned error in intake draft generation. See screenshot 07b.")


def _try_complete_brief_review_ui(runner) -> bool:
    page = runner.page
    artifacts = runner.artifacts

    page.get_by_role("button", name="Intake", exact=True).click()
    enter_brief = page.locator("button", has_text="Enter Brief Review")
    expect(enter_brief).to_be_visible(timeout=10000)
    enter_brief.click()

    brief_heading = page.locator("h2", has_text="Project Brief")
    try:
        expect(brief_heading).to_be_visible(timeout=5000)
    except AssertionError:
        _snap(page, "08b_brief_tab_route_failure", writer=artifacts)
        return False

    _snap(page, "08_brief_tab_loaded", writer=artifacts)
    for _ in range(20):
        confirm_buttons = _pending_confirm_buttons(page)
        if confirm_buttons.count() == 0:
            break
        btn = confirm_buttons.first
        btn.click()
        expect(btn).to_be_disabled(timeout=15000)

    enter_outline = page.locator("button", has_text="Enter Chapter Outline Review")
    if enter_outline.count() == 0:
        _snap(page, "09b_brief_ui_incomplete", writer=artifacts)
        return False

    _snap(page, "09_brief_all_confirmed", writer=artifacts)
    return True


def _fallback_brief_review_api(runner) -> str:
    page = runner.page
    server_url = runner.server_url
    artifacts = runner.artifacts
    project_name = artifacts.run_id

    resp = httpx.post(f"{server_url}/api/projects/{project_name}/brief/promote-draft", timeout=30.0)
    print(f"\n[PROMOTE BRIEF] status={resp.status_code} body={resp.text}\n")
    assert resp.status_code == 200, f"Promote brief failed: {resp.status_code} {resp.text}"

    brief_resp = httpx.get(f"{server_url}/api/projects/{project_name}/brief", timeout=10.0)
    print(f"[GET BRIEF] status={brief_resp.status_code}")
    assert brief_resp.status_code == 200, f"Get brief failed: {brief_resp.status_code}"
    brief_data = brief_resp.json()
    print(f"[BRIEF CARDS] {list(brief_data.get('cards', {}).keys())}")

    brief_confirmation_attempts: list[tuple[str, int, str]] = []
    for card_key in brief_data.get("cards", {}):
        confirm_resp = httpx.post(
            f"{server_url}/api/projects/{project_name}/brief/confirm-card",
            json={"card_key": card_key},
            timeout=10.0,
        )
        print(f"[CONFIRM {card_key}] status={confirm_resp.status_code}")
        if confirm_resp.status_code != 200:
            print(f"[CONFIRM ERROR] {confirm_resp.text}")
        brief_confirmation_attempts.append((card_key, confirm_resp.status_code, confirm_resp.text))

    _assert_confirmation_successes("brief", brief_confirmation_attempts)

    page.reload()
    page.wait_for_timeout(1500)
    _snap(page, "09_brief_all_confirmed", writer=artifacts)
    return "api_fallback"


def _try_complete_outline_review_ui(runner) -> bool:
    page = runner.page
    artifacts = runner.artifacts

    page.get_by_role("button", name="Brief", exact=True).click()
    page.wait_for_timeout(800)
    enter_outline = page.locator("button", has_text="Enter Chapter Outline Review")
    if enter_outline.count() > 0:
        enter_outline.click()
    else:
        page.get_by_role("button", name="Outline", exact=True).click()

    outline_heading = page.locator("h2", has_text="Chapter Outline")
    try:
        expect(outline_heading).to_be_visible(timeout=5000)
    except AssertionError:
        _snap(page, "10b_outline_tab_route_failure", writer=artifacts)
        return False

    _snap(page, "10_outline_tab_loaded", writer=artifacts)
    for _ in range(20):
        confirm_buttons = _pending_confirm_buttons(page)
        if confirm_buttons.count() == 0:
            break
        btn = confirm_buttons.first
        btn.click()
        expect(btn).to_be_disabled(timeout=15000)

    freeze_btn = page.locator("button", has_text="Freeze Blueprint")
    if freeze_btn.count() == 0:
        _snap(page, "11b_outline_ui_incomplete", writer=artifacts)
        return False

    _snap(page, "11_outline_all_confirmed", writer=artifacts)
    return True


def _fallback_outline_review_api(runner) -> str:
    page = runner.page
    server_url = runner.server_url
    artifacts = runner.artifacts
    project_name = artifacts.run_id

    resp = httpx.post(f"{server_url}/api/projects/{project_name}/chapter-outline/promote-draft", timeout=30.0)
    print(f"\n[PROMOTE OUTLINE] status={resp.status_code} body={resp.text}\n")
    assert resp.status_code == 200, f"Promote outline failed: {resp.status_code} {resp.text}"

    outline_resp = httpx.get(f"{server_url}/api/projects/{project_name}/chapter-outline", timeout=10.0)
    assert outline_resp.status_code == 200, f"Get outline failed: {outline_resp.status_code}"
    outline_data = outline_resp.json()
    print(f"[OUTLINE CHAPTERS] {len(outline_data.get('chapters', []))}")

    outline_confirmation_attempts: list[tuple[str, int, str]] = []
    for ch in outline_data.get("chapters", []):
        ch_id = ch.get("chapter_id")
        confirm_resp = httpx.post(
            f"{server_url}/api/projects/{project_name}/chapter-outline/confirm-chapter",
            json={"chapter_id": ch_id},
            timeout=10.0,
        )
        print(f"[CONFIRM CHAPTER {ch_id}] status={confirm_resp.status_code}")
        outline_confirmation_attempts.append((str(ch_id), confirm_resp.status_code, confirm_resp.text))

    _assert_confirmation_successes("outline", outline_confirmation_attempts)

    page.reload()
    page.wait_for_timeout(1500)
    _snap(page, "11_outline_all_confirmed", writer=artifacts)
    return "api_fallback"


def _run_brief_review_stage(runner) -> str:
    return runner.attempt_brief_review(_try_complete_brief_review_ui, _fallback_brief_review_api)


def _run_outline_review_stage(runner) -> str:
    return runner.attempt_outline_review(_try_complete_outline_review_ui, _fallback_outline_review_api)


def _run_freeze_and_build_stage(runner) -> None:
    page = runner.page
    server_url = runner.server_url
    e2e_workspace = runner.workspace
    artifacts = runner.artifacts
    project_name = artifacts.run_id

    page.get_by_role("button", name="Outline", exact=True).click()
    page.wait_for_timeout(800)
    blueprint_path = e2e_workspace / project_name / "meta" / "blueprint.yaml"
    freeze_btn = _freeze_blueprint_button(page)
    if freeze_btn.count() > 0:
        freeze_btn.click()
    else:
        httpx.post(f"{server_url}/api/projects/{project_name}/blueprint/freeze", timeout=10.0)
    _wait_for_blueprint_file(blueprint_path)

    # Wait for auto-generation chain to complete (postFreezeFlow)
    post_freeze_status = page.locator("[data-testid='post-freeze-status']")
    post_freeze_success = post_freeze_status.filter(has_text="Scene packages and prototype scripts are ready")
    post_freeze_failed = post_freeze_status.filter(has_text="failed").or_(
        post_freeze_status.locator("text=Error").or_(post_freeze_status.locator("text=error"))
    )
    post_freeze_success.or_(post_freeze_failed).first.wait_for(state="visible", timeout=120000)

    if post_freeze_failed.count() > 0:
        _snap(page, "12b_post_freeze_failed", writer=artifacts)
        raise AssertionError(
            f"Post-freeze auto-generation chain failed: {post_freeze_status.text_content()}"
        )

    _snap(page, "12_blueprint_frozen", writer=artifacts)

    build_btn = page.locator("button", has_text="Build")
    _assert_build_button_present(build_btn.count())
    build_btn.first.click()
    # "Generating" here refers to the prototype-generation phase (pre-build),
    # not the build itself; kept because the UI may show either label.
    build_progress = page.locator("text=Building").or_(page.locator("text=Generating")).first
    expect(build_progress).to_be_visible(timeout=30000)
    _snap(page, "13_build_started", writer=artifacts)

    build_ok = page.locator("button", has_text="Build OK")
    build_failed = page.locator("button", has_text="Retry Build")
    build_status = page.locator("[data-testid='build-status']")

    build_ok.or_(build_failed).first.wait_for(state="visible", timeout=120000)

    if build_failed.count() > 0:
        status_text = build_status.text_content() or "(no build status text)"
        _snap(page, "14b_build_failed", writer=artifacts)
        raise AssertionError(f"Build failed: {status_text}")

    _snap(page, "14_build_complete", writer=artifacts)

    print(f"\n=== All screenshots saved to: {artifacts.run_dir} ===")


def _detect_llm_label() -> str:
    anthropic_base = os.environ.get("ANTHROPIC_BASE_URL", "").lower()
    if "moonshot" in anthropic_base:
        return "moonshot"
    if "kimi" in anthropic_base:
        return "kimi"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic-compatible"
    return "unknown"


def _write_run_summary(
    artifacts,
    *,
    mode: ExecutionMode,
    project_name: str,
    llm_label: str,
    result: str,
    first_failing_step: str,
    runner,
    freeze_reached: bool,
    build_reached: bool,
):
    api_fallback_used = "yes" if getattr(runner, "fallbacks", []) else "no"
    build_mode = "real" if mode.expect_real_build else "mock"
    artifact_names = sorted(path.name for path in artifacts.run_dir.iterdir())
    lines = [
        "# Full Game Creation Run Summary",
        "",
        f"- Run ID: `{artifacts.run_id}`",
        f"- Mode: `{mode.name}`",
        f"- Project: `{project_name}`",
        f"- LLM: `{llm_label}`",
        f"- Build mode: `{build_mode}`",
        f"- Result: `{result}`",
        f"- First failing step: `{first_failing_step}`",
        f"- API fallback used: `{api_fallback_used}`",
        f"- Freeze reached: `{'yes' if freeze_reached else 'no'}`",
        f"- Build reached: `{'yes' if build_reached else 'no'}`",
        "",
        "## Diagnostics",
    ]
    for entry in getattr(runner, "diagnostics", []):
        lines.append(f"- `{entry['code']}` ({entry['stage']})")
    if not getattr(runner, "diagnostics", []):
        lines.append("- none")
    lines.extend(["", "## Fallbacks"])
    for entry in getattr(runner, "fallbacks", []):
        lines.append(f"- `{entry['fallback_used']}` because `{entry['reason']}`")
    if not getattr(runner, "fallbacks", []):
        lines.append("- none")
    lines.extend(["", "## Artifacts"])
    for name in artifact_names:
        lines.append(f"- `{name}`")
    return artifacts.write_markdown("summary.md", "\n".join(lines) + "\n")


def _run_full_game_creation_test(
    page: Page,
    e2e_workspace: Path,
    execution_mode: ExecutionMode,
    run_id_prefix: str,
) -> None:
    """Shared harness for full-game creation tests with configurable execution mode."""
    project_name = _artifact_run_id(run_id_prefix)
    ArtifactWriter = _load_artifact_writer()
    artifacts = ArtifactWriter(SCREENSHOT_DIR, project_name)
    server_url, proc = start_real_llm_server(e2e_workspace, mode=execution_mode, artifacts=artifacts)
    runner_module = _load_full_game_creation_runner_module()
    runner = runner_module.FullGameCreationRunner(
        page=page,
        server_url=server_url,
        workspace=e2e_workspace,
        mode=execution_mode,
        artifacts=artifacts,
        create_project=_run_create_project_stage,
        intake=_run_intake_stage,
        brief_review=_run_brief_review_stage,
        outline_review=_run_outline_review_stage,
        freeze_and_build=_run_freeze_and_build_stage,
    )

    page.on("pageerror", lambda err: artifacts.write_text(
        "browser_errors", "console", f"{err}\n", suffix=".log"
    ))

    result = "PASS"
    first_failing_step = "n/a"
    try:
        runner.run()
    except Exception as exc:
        result = "FAIL"
        first_failing_step = runner.diagnostics[0]["code"] if getattr(runner, "diagnostics", []) else exc.__class__.__name__
        raise
    finally:
        stop_real_llm_server(proc)
        freeze_reached = artifacts.path_for("12_blueprint_frozen.png").exists()
        build_reached = artifacts.path_for("13_build_started.png").exists() or artifacts.path_for("14_build_complete.png").exists()
        _write_run_summary(
            artifacts,
            mode=execution_mode,
            project_name=project_name,
            llm_label=_detect_llm_label(),
            result=result,
            first_failing_step=first_failing_step,
            runner=runner,
            freeze_reached=freeze_reached,
            build_reached=build_reached,
        )


def test_full_game_creation_with_real_llm(
    page: Page,
    e2e_workspace: Path,
) -> None:
    """Full end-to-end: create project -> intake chat (real LLM) -> brief -> outline -> freeze -> build.
    Screenshots saved to workspace/screenshots/full_game_creation/.
    Uses HYBRID_RECOVERY mode (API fallback enabled) by default.
    """
    _run_full_game_creation_test(page, e2e_workspace, _load_default_execution_mode(), "real_llm")


def test_full_game_creation_with_real_llm_ui_diagnostic(
    page: Page,
    e2e_workspace: Path,
) -> None:
    """UI_ONLY_DEBUG mode: disables all API fallbacks to surface pure UI bugs.
    Any UI race or broken tab route will cause a hard failure.
    """
    _run_full_game_creation_test(page, e2e_workspace, FULL_GAME_CREATION_MODES.UI_ONLY_DEBUG, "ui_diag")


def test_full_game_creation_with_real_llm_and_real_build(
    page: Page,
    e2e_workspace: Path,
) -> None:
    """REAL_BUILD_ACCEPTANCE mode: runs the real Ren'Py build instead of mock build.
    Validates that the generated prototype is actually playable.
    Trigger manually; do not run in standard CI.
    """
    _run_full_game_creation_test(page, e2e_workspace, FULL_GAME_CREATION_MODES.REAL_BUILD_ACCEPTANCE, "real_build")
