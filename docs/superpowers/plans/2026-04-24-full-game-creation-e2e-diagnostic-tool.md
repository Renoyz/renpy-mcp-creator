# Full Game Creation E2E Diagnostic Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `tests/e2e/test_full_game_creation_real_llm_playwright.py` into a reliable end-to-end diagnostic tool that simulates human UI flow as closely as possible, captures screenshots and state artifacts at every step, and clearly distinguishes UI failures from backend, LLM, or build failures.

**Architecture:** Keep the current test file as the orchestration entrypoint, but extract reusable step-runner and artifact-capture helpers so each stage of the journey can be executed, diagnosed, and reported independently. Support multiple execution modes (`ui_only_debug`, `hybrid_recovery`, `mock_build`, `real_build`) so the same harness can be used for true UX validation, backend isolation, and final acceptance runs without conflating the results.

**Tech Stack:** Playwright, pytest, FastAPI test server bootstrap, httpx, filesystem artifact capture, real LLM providers, optional mock build backend.

---

### Task 1: Baseline the Existing Test and Freeze Current Failure Semantics

**Files:**
- Modify: `tests/e2e/test_full_game_creation_real_llm_playwright.py`
- Test: `tests/e2e/test_full_game_creation_real_llm_playwright.py`

- [ ] **Step 1: Add a failing baseline test marker and explicit current-mode summary**

Add a small helper section near the top of `tests/e2e/test_full_game_creation_real_llm_playwright.py` that declares the current harness mode and failure assumptions:

```python
TEST_MODE = "legacy_hybrid"
KNOWN_SHORTCUTS = {
    "intake_start": "textarea command injection",
    "brief_review": "api promote + api confirm fallback",
    "outline_review": "api promote + api confirm fallback",
    "build": "mock build by default",
}
```

- [ ] **Step 2: Add a failing assertion that documents the current anti-goal**

Add a small test like:

```python
def test_full_game_creation_tool_is_not_pure_ui_yet() -> None:
    assert TEST_MODE != "legacy_hybrid"
```

This should fail immediately and establishes that refactoring is intentional, not incidental.

- [ ] **Step 3: Run the targeted test to verify RED**

Run:

```powershell
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py::test_full_game_creation_tool_is_not_pure_ui_yet -q
```

Expected: `FAIL` because the harness still identifies itself as `legacy_hybrid`.

- [ ] **Step 4: Replace the placeholder mode with a real execution-mode contract**

Replace the ad-hoc constants with:

```python
from tests.e2e.helpers.full_game_creation_modes import ExecutionMode
```

and use explicit mode values later in the runner.

- [ ] **Step 5: Re-run the targeted test and delete/replace it with mode-specific assertions**

Run the same test command again.

Expected: the temporary RED test is removed or replaced by real mode validation in later tasks.


### Task 2: Extract Artifact Capture Into a Dedicated Helper

**Files:**
- Create: `tests/e2e/helpers/full_game_creation_artifacts.py`
- Modify: `tests/e2e/test_full_game_creation_real_llm_playwright.py`
- Test: `tests/e2e/test_full_game_creation_real_llm_playwright.py`

- [ ] **Step 1: Write the failing artifact-capture tests**

Add targeted tests near the current file or in a new lightweight pytest module:

```python
def test_artifact_writer_creates_run_directory(...):
    ...

def test_artifact_writer_saves_png_html_and_json(...):
    ...
```

Validate that one step creates:
- screenshot PNG
- page HTML dump
- structured JSON artifact
- human-readable notes file

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py -k "artifact_writer" -q
```

Expected: `FAIL` because no artifact helper exists yet.

- [ ] **Step 3: Create `full_game_creation_artifacts.py`**

Implement a focused helper with an API like:

```python
class ArtifactWriter:
    def __init__(self, root: Path, run_id: str) -> None:
        ...

    def capture_page(self, page: Page, step_id: str, note: str | None = None) -> None:
        ...

    def write_json(self, step_id: str, name: str, payload: dict) -> None:
        ...

    def write_text(self, step_id: str, name: str, text: str) -> None:
        ...
```

Directory shape:

```text
workspace/screenshots/full_game_creation/<run-id>/
  01_project_list.png
  01_project_list.page.html
  01_project_list.notes.txt
  01_project_list.refinement-status.json
```

- [ ] **Step 4: Replace `_snap()` with artifact writer integration**

In the test file, keep `_snap()` only as a thin compatibility wrapper or remove it entirely and switch to:

```python
artifacts.capture_page(page, "01_project_list")
```

- [ ] **Step 5: Re-run artifact tests**

Run:

```powershell
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py -k "artifact_writer" -q
```

Expected: `PASS`.


### Task 3: Replace Command Injection With Real UI Intake Start

**Files:**
- Modify: `tests/e2e/test_full_game_creation_real_llm_playwright.py`
- Test: `tests/e2e/test_full_game_creation_real_llm_playwright.py`

- [ ] **Step 1: Write the failing intake-start test**

Add an assertion-driven test for the real UI entry path:

```python
def test_full_game_creation_starts_intake_via_button_not_textarea(...):
    ...
```

The test should:
- create a fresh project
- click `Start Intake with AI`
- wait for the first assistant message
- assert it contains `Project Brief` or `项目简报`
- assert it does **not** contain `完整的蓝图` or `blueprint`

- [ ] **Step 2: Run the targeted test to verify RED**

Run:

```powershell
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py::test_full_game_creation_starts_intake_via_button_not_textarea -q
```

Expected: `FAIL` with the current direct textarea-start logic still present.

- [ ] **Step 3: Extract `start_intake_via_button()` helper**

Implement in the main test file or a new runner helper:

```python
def start_intake_via_button(page: Page, artifacts: ArtifactWriter) -> None:
    page.get_by_role("button", name="Start Intake with AI", exact=True).click()
    chat = _resolve_chat_root(page)
    expect(chat.locator("text=Project Brief").or_(chat.locator("text=项目简报")).first).to_be_visible(timeout=60000)
    artifacts.capture_page(page, "05_intake_started")
```

- [ ] **Step 4: Remove textarea-based start from the full-flow test**

Delete the old block:

```python
page.locator("textarea").fill("start_refinement_intake")
page.locator("button >> svg").last.click()
```

and route the flow through the helper.

- [ ] **Step 5: Re-run the intake-start test**

Run:

```powershell
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py::test_full_game_creation_starts_intake_via_button_not_textarea -q
```

Expected: `PASS`.


### Task 4: Introduce Execution Modes Instead of Hardcoded Hybrid Behavior

**Files:**
- Create: `tests/e2e/helpers/full_game_creation_modes.py`
- Create: `tests/e2e/helpers/full_game_creation_runner.py`
- Modify: `tests/e2e/test_full_game_creation_real_llm_playwright.py`
- Test: `tests/e2e/test_full_game_creation_real_llm_playwright.py`

- [ ] **Step 1: Write the failing mode-contract tests**

Add tests for mode behavior:

```python
def test_ui_only_mode_forbids_api_shortcuts(...):
    ...

def test_hybrid_recovery_mode_allows_api_fallback_after_ui_failure(...):
    ...
```

- [ ] **Step 2: Run the targeted tests to verify RED**

Run:

```powershell
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py -k "ui_only_mode or hybrid_recovery_mode" -q
```

Expected: `FAIL` because the current file always uses mixed UI/API behavior.

- [ ] **Step 3: Create the mode contract**

In `full_game_creation_modes.py`, define:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ExecutionMode:
    name: str
    allow_api_promote_fallback: bool
    allow_api_confirm_fallback: bool
    use_mock_build: bool
    expect_real_build: bool

UI_ONLY_DEBUG = ExecutionMode(...)
HYBRID_RECOVERY = ExecutionMode(...)
MOCK_BUILD_ACCEPTANCE = ExecutionMode(...)
REAL_BUILD_ACCEPTANCE = ExecutionMode(...)
```

- [ ] **Step 4: Route full-flow execution through a runner class**

In `full_game_creation_runner.py`, add a small orchestrator:

```python
class FullGameCreationRunner:
    def __init__(self, page: Page, server_url: str, workspace: Path, mode: ExecutionMode, artifacts: ArtifactWriter):
        ...

    def run(self) -> None:
        ...
```

- [ ] **Step 5: Re-run the mode tests**

Run:

```powershell
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py -k "ui_only_mode or hybrid_recovery_mode" -q
```

Expected: `PASS`.


### Task 5: Make UI Failure Points Explicit Before Falling Back to API

**Files:**
- Modify: `tests/e2e/helpers/full_game_creation_runner.py`
- Modify: `tests/e2e/test_full_game_creation_real_llm_playwright.py`
- Test: `tests/e2e/test_full_game_creation_real_llm_playwright.py`

- [ ] **Step 1: Write failing diagnostic tests for Brief and Outline gating**

Add tests for the expected behavior:

```python
def test_runner_records_brief_tab_route_failure_before_api_fallback(...):
    ...

def test_runner_records_outline_tab_route_failure_before_api_fallback(...):
    ...
```

- [ ] **Step 2: Run the diagnostic tests to verify RED**

Run:

```powershell
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py -k "brief_tab_route_failure or outline_tab_route_failure" -q
```

Expected: `FAIL` because the current test jumps to API too early.

- [ ] **Step 3: Implement `attempt_enter_brief_review()` and `attempt_enter_outline_review()`**

The runner should first try the UI path, then diagnose, then optionally fall back:

```python
def attempt_enter_brief_review(self) -> None:
    self.page.get_by_role("button", name="Intake", exact=True).click()
    enter = self.page.locator("button", has_text="Enter Brief Review")
    expect(enter).to_be_visible(timeout=10000)
    enter.click()
    self.page.wait_for_timeout(1500)
    if not self._is_brief_tab_visible():
        self.capture_step_diagnostics("08_brief_tab_route_failure")
        if not self.mode.allow_api_promote_fallback:
            raise AssertionError("Brief review did not enter via UI")
```

Apply the same pattern for Outline.

- [ ] **Step 4: Ensure fallback usage is recorded in artifacts and summary**

Every fallback must write a note such as:

```text
fallback_used=api_promote_brief
reason=brief_tab_not_visible_after_ui_click
```

- [ ] **Step 5: Re-run the diagnostic tests**

Run:

```powershell
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py -k "brief_tab_route_failure or outline_tab_route_failure" -q
```

Expected: `PASS`.


### Task 6: Add Backend Log Capture and Run Summary Output

**Files:**
- Modify: `tests/e2e/test_full_game_creation_real_llm_playwright.py`
- Modify: `tests/e2e/conftest.py`
- Modify: `tests/e2e/helpers/full_game_creation_artifacts.py`
- Test: `tests/e2e/test_full_game_creation_real_llm_playwright.py`

- [ ] **Step 1: Write the failing summary/log tests**

Add tests such as:

```python
def test_real_llm_runner_writes_summary_markdown(...):
    ...

def test_real_llm_runner_persists_backend_logs(...):
    ...
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py -k "summary_markdown or backend_logs" -q
```

Expected: `FAIL` because the current harness only prints screenshot directory information.

- [ ] **Step 3: Change the real-LLM server bootstrap to log to files**

Modify `start_real_llm_server()` so each run writes:

```text
workspace/screenshots/full_game_creation/<run-id>/backend.stdout.log
workspace/screenshots/full_game_creation/<run-id>/backend.stderr.log
```

Do not keep unconsumed `PIPE`s for long-running runs.

- [ ] **Step 4: Generate `summary.md` at the end of every run**

Write a summary file with this shape:

```markdown
# Full Game Creation Run Summary

- Run ID: `...`
- Mode: `ui_only_debug`
- Project: `real_llm_...`
- LLM: `moonshot` / `kimi` / `unknown`
- Build mode: `mock` / `real`
- Result: `PASS` / `FAIL`
- First failing step: `08_brief_tab_route_failure`
- API fallback used: `yes` / `no`
- Freeze reached: `yes` / `no`
- Build reached: `yes` / `no`

## Artifacts
- `05_intake_started.png`
- `08_brief_tab_route_failure.page.html`
- `backend.stdout.log`
- `backend.stderr.log`
```

- [ ] **Step 5: Re-run the summary/log tests**

Run:

```powershell
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py -k "summary_markdown or backend_logs" -q
```

Expected: `PASS`.


### Task 7: Separate Mock-Build Validation From Real-Build Validation

**Files:**
- Modify: `tests/e2e/test_full_game_creation_real_llm_playwright.py`
- Modify: `tests/e2e/conftest.py`
- Test: `tests/e2e/test_full_game_creation_real_llm_playwright.py`

- [ ] **Step 1: Write failing tests for build-mode honesty**

Add tests like:

```python
def test_mock_build_mode_is_reported_as_mock_not_complete_game_creation(...):
    ...

def test_real_build_mode_requires_mock_build_disabled(...):
    ...
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py -k "mock_build_mode or real_build_mode" -q
```

Expected: `FAIL` because current real-LLM test silently runs with `RENPY_MCP_MOCK_BUILD=1`.

- [ ] **Step 3: Split server bootstrap knobs**

Change `start_real_llm_server()` to accept:

```python
def start_real_llm_server(workspace: Path, *, use_mock_build: bool) -> tuple[str, subprocess.Popen]:
    ...
```

and derive env:

```python
if use_mock_build:
    env["RENPY_MCP_MOCK_BUILD"] = "1"
else:
    env.pop("RENPY_MCP_MOCK_BUILD", None)
```

- [ ] **Step 4: Split top-level tests by acceptance target**

Keep two explicit entrypoints:

```python
def test_full_game_creation_with_real_llm_ui_diagnostic(...):
    ...

def test_full_game_creation_with_real_llm_and_real_build(...):
    ...
```

The first may use `mock_build`, but the second must not.

- [ ] **Step 5: Re-run the build-mode tests**

Run:

```powershell
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py -k "mock_build_mode or real_build_mode" -q
```

Expected: `PASS`.


### Task 8: Final Regression and Operator Documentation

**Files:**
- Modify: `tests/e2e/test_full_game_creation_real_llm_playwright.py`
- Modify: `docs/plans/` or `docs/superpowers/plans/` only if a short operator note is needed
- Test: `tests/e2e/test_full_game_creation_real_llm_playwright.py`

- [ ] **Step 1: Add a short operator-facing docstring and CLI hints**

At the top of the test file, document:
- required env vars for real LLM
- when to use `ui_only_debug`
- when to use `hybrid_recovery`
- where artifacts are written
- what counts as a real pass

- [ ] **Step 2: Run the focused full-flow diagnostic in `ui_only_debug` mode**

Run:

```powershell
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py::test_full_game_creation_with_real_llm_ui_diagnostic -q -s
```

Expected:
- either PASS through pure UI
- or FAIL with a populated artifact directory and `summary.md`

- [ ] **Step 3: Run the fallback-enabled diagnostic in `hybrid_recovery` mode**

Run:

```powershell
uv run pytest tests/e2e/test_full_game_creation_real_llm_playwright.py::test_full_game_creation_with_real_llm_hybrid_recovery -q -s
```

Expected:
- progress beyond known UI blockers
- explicit fallback accounting in `summary.md`

- [ ] **Step 4: Run the broader affected regression suite**

Run:

```powershell
uv run pytest tests/e2e/test_refinement_workspace_playwright.py -q
uv run pytest tests/integration/test_ws_chat_blueprint.py -q
cd dashboard; npm run build
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add tests/e2e/test_full_game_creation_real_llm_playwright.py tests/e2e/helpers/full_game_creation_*.py tests/e2e/conftest.py docs/superpowers/plans/2026-04-24-full-game-creation-e2e-diagnostic-tool.md

git commit -m "test: add diagnostic full-game-creation e2e harness"
```
