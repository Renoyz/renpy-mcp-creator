# Core Feature Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a usable end-to-end creator workflow: choose or create a project, enter that project workspace, use AI against the current project, write generated content back into the project, build the web version, and preview it from the dashboard.

**Architecture:** Introduce a single current-project context shared by the React app, dashboard routes, and chat WebSocket sessions. Use that context to turn existing low-level tools into a product workflow, then expose build and preview as explicit UI actions with test coverage anchored on the dashboard E2E path.

**Tech Stack:** React, React Router, FastAPI, WebSocket, FastMCP, Pydantic, pytest, Playwright

---

## File Structure

**Create**
- `dashboard/src/context/ProjectContext.tsx`
- `dashboard/src/pages/ProjectWorkspacePage.tsx`
- `docs/superpowers/plans/2026-04-15-core-feature-loop.md`

**Modify**
- `dashboard/src/App.tsx`
- `dashboard/src/AppShell.tsx`
- `dashboard/src/components/ChatDrawer.tsx`
- `dashboard/src/pages/ProjectSelectPage.tsx`
- `dashboard/src/pages/LegacyIframePage.tsx`
- `src/renpy_mcp/models.py`
- `src/renpy_mcp/web/fastapi_app.py`
- `src/renpy_mcp/web/chat_ws.py`
- `src/renpy_mcp/tools/project.py`
- `src/renpy_mcp/tools/assets.py`
- `src/renpy_mcp/tools/preview.py`
- `src/renpy_mcp/services/build_manager.py`
- `src/renpy_mcp/cli/app.py`
- `tests/integration/test_fastapi_api.py`
- `tests/integration/test_ws_chat.py`
- `tests/integration/test_ws_chat_confirmation.py`
- `tests/e2e/test_dashboard_playwright.py`

**Testing Focus**
- Current project selection and persistence
- Chat requests bound to a current project
- Generated assets written into runnable project paths
- Build and preview entry points from dashboard
- Dashboard E2E closure from create project to build result

### Task 1: Establish Current Project Context

**Files:**
- Create: `dashboard/src/context/ProjectContext.tsx`
- Modify: `dashboard/src/main.tsx`
- Modify: `dashboard/src/App.tsx`
- Modify: `dashboard/src/pages/ProjectSelectPage.tsx`
- Test: `tests/integration/test_fastapi_api.py`

- [ ] **Step 1: Write the failing API test for selecting a current project**

```python
def test_current_project_selection(client: TestClient, temp_project: Path):
    response = client.post("/api/projects/select", json={"name": temp_project.name})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["current_project"]["name"] == temp_project.name

    state = client.get("/api/projects/current")
    assert state.status_code == 200
    assert state.json()["current_project"]["name"] == temp_project.name
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_fastapi_api.py -k current_project_selection -v`
Expected: FAIL with `404` or missing route assertions for `/api/projects/select` and `/api/projects/current`

- [ ] **Step 3: Add backend current-project endpoints and model payload**

```python
class CurrentProjectPayload(BaseModel):
    name: str
    path: Path

@app.get("/api/projects/current")
async def api_current_project(config: RenPyConfig = Depends(get_config)):
    if not config.project_path:
        return {"current_project": None}
    return {
        "current_project": {
            "name": config.project_path.name,
            "path": str(config.project_path),
        }
    }

@app.post("/api/projects/select")
async def api_select_project(request: Request, config: RenPyConfig = Depends(get_config)):
    body = await request.json()
    name = body.get("name", "").strip()
    settings = get_settings()
    project_dir = settings.workspace / name
    if not (project_dir / "game").exists():
        raise HTTPException(status_code=404, detail="Project not found")
    config.project_path = project_dir
    return {
        "success": True,
        "current_project": {"name": project_dir.name, "path": str(project_dir)},
    }
```

- [ ] **Step 4: Add a React project context provider**

```tsx
type CurrentProject = { name: string; path: string } | null;

const ProjectContext = createContext<{
  currentProject: CurrentProject;
  setCurrentProject: (project: CurrentProject) => void;
}>({
  currentProject: null,
  setCurrentProject: () => {},
});
```

- [ ] **Step 5: Wrap the app with the provider and hydrate from `/api/projects/current`**

Run: `npm --prefix dashboard test`
Expected: If no frontend test runner exists yet, record `No test script` and continue to integration verification in later tasks

- [ ] **Step 6: Add project selection behavior to the project list page**

```tsx
const handleOpen = async (name: string) => {
  const resp = await fetch("/api/projects/select", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!resp.ok) throw new Error("Failed to open project");
  const data = await resp.json();
  setCurrentProject(data.current_project);
  navigate(`/projects/${name}`);
};
```

- [ ] **Step 7: Run test to verify backend selection passes**

Run: `pytest tests/integration/test_fastapi_api.py -k current_project_selection -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add dashboard/src/context/ProjectContext.tsx dashboard/src/main.tsx dashboard/src/App.tsx dashboard/src/pages/ProjectSelectPage.tsx src/renpy_mcp/models.py src/renpy_mcp/web/fastapi_app.py tests/integration/test_fastapi_api.py
git commit -m "feat: add current project context"
```

### Task 2: Add a Real Project Workspace Route

**Files:**
- Create: `dashboard/src/pages/ProjectWorkspacePage.tsx`
- Modify: `dashboard/src/App.tsx`
- Modify: `dashboard/src/AppShell.tsx`
- Modify: `dashboard/src/pages/LegacyIframePage.tsx`
- Test: `tests/e2e/test_dashboard_playwright.py`

- [ ] **Step 1: Write the failing E2E expectation for opening a project workspace**

```python
page.goto(f"{server_url}/dashboard")
page.locator("button:has-text('新建项目')").click()
page.locator("input").fill(project_name)
page.locator("button:has-text('创建')").click()
page.locator(f"h4:has-text('{project_name}')").click()
expect(page.locator(f"text={project_name}")).to_be_visible()
expect(page.locator("text=Build")).to_be_visible()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/e2e/test_dashboard_playwright.py -k project_workspace -v`
Expected: FAIL because the project card is not actionable and there is no `/projects/:name` workspace route

- [ ] **Step 3: Add `ProjectWorkspacePage` with current project header, build button, preview button, and embedded tools links**

```tsx
export function ProjectWorkspacePage() {
  const { currentProject } = useProjectContext();
  if (!currentProject) return <Navigate to="/projects" replace />;
  return (
    <div className="space-y-6">
      <header>
        <h1>{currentProject.name}</h1>
        <p>{currentProject.path}</p>
      </header>
      <div className="flex gap-3">
        <button>Build</button>
        <button>Preview</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Route `/projects/:name` to the workspace and keep iframe pages project-aware**

```tsx
<Route path="/projects/:name" element={<ProjectWorkspacePage />} />
```

- [ ] **Step 5: Update shell navigation so the active project is visible in the header**

Run: `npm --prefix dashboard run build`
Expected: Vite build succeeds

- [ ] **Step 6: Re-run the targeted E2E slice**

Run: `pytest tests/e2e/test_dashboard_playwright.py -k project_workspace -v`
Expected: PASS or proceed with the next failing expectation around build/preview actions

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/App.tsx dashboard/src/AppShell.tsx dashboard/src/pages/LegacyIframePage.tsx dashboard/src/pages/ProjectSelectPage.tsx dashboard/src/pages/ProjectWorkspacePage.tsx tests/e2e/test_dashboard_playwright.py
git commit -m "feat: add project workspace route"
```

### Task 3: Bind Chat Sessions to the Current Project

**Files:**
- Modify: `dashboard/src/components/ChatDrawer.tsx`
- Modify: `src/renpy_mcp/web/chat_ws.py`
- Modify: `src/renpy_mcp/tools/project.py`
- Test: `tests/integration/test_ws_chat.py`
- Test: `tests/integration/test_ws_chat_confirmation.py`

- [ ] **Step 1: Write the failing WebSocket test for project-scoped chat**

```python
async def test_ws_chat_uses_current_project(ws_client):
    await ws_client.send_json({
        "type": "user_message",
        "content": "build the web version",
        "project_name": "demo_vn",
    })
    message = await ws_client.receive_json()
    assert message["type"] != "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_ws_chat.py -k current_project -v`
Expected: FAIL because the socket protocol ignores `project_name`

- [ ] **Step 3: Send `project_name` from `ChatDrawer` on every message and confirmation response**

```tsx
wsRef.current.send(JSON.stringify({
  type: "user_message",
  content: text,
  project_name: currentProject?.name ?? null,
}));
```

- [ ] **Step 4: Resolve `project_name` on the backend before running the chat engine**

```python
def _bind_project(project_name: str | None) -> None:
    if not project_name:
        return
    settings = get_settings()
    project_dir = settings.workspace / project_name
    if (project_dir / "game").exists():
        get_config().project_path = project_dir
```

- [ ] **Step 5: Add a guardrail response when no current project is available for project-bound requests**

```python
if "project" in content.lower() and get_config().project_path is None:
    await websocket.send_json({"type": "error", "message": "No active project selected."})
    continue
```

- [ ] **Step 6: Run targeted WebSocket tests**

Run: `pytest tests/integration/test_ws_chat.py tests/integration/test_ws_chat_confirmation.py -v`
Expected: PASS for the new project-bound chat cases

- [ ] **Step 7: Commit**

```bash
git add dashboard/src/components/ChatDrawer.tsx src/renpy_mcp/web/chat_ws.py src/renpy_mcp/tools/project.py tests/integration/test_ws_chat.py tests/integration/test_ws_chat_confirmation.py
git commit -m "feat: bind chat sessions to current project"
```

### Task 4: Make Generated Content Land in Runnable Project Paths

**Files:**
- Modify: `src/renpy_mcp/tools/assets.py`
- Modify: `src/renpy_mcp/tools/project.py`
- Modify: `src/renpy_mcp/services/build_manager.py`
- Test: `tests/unit/test_tools_asset_generation.py`
- Test: `tests/unit/test_tools_project_creator.py`

- [ ] **Step 1: Write the failing asset generation test for game-ready output**

```python
result = json.loads(await generate_background(
    project_name="demo_vn",
    description="school rooftop at sunset",
))
assert result["success"] is True
assert result["relative_files"][0].startswith("game/images/")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_tools_asset_generation.py -k game_ready_output -v`
Expected: FAIL because generated files currently live under `assets/`

- [ ] **Step 3: Change generated asset targets to `game/images/background` and `game/images/character`**

```python
output_dir = project_dir / "game" / "images" / image_type
output_dir.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Add helper logic that returns Ren'Py-ready asset references**

```python
payload["renpy_image_names"] = [
    Path(path).stem.replace("_", " ")
    for path in relative_files
]
```

- [ ] **Step 5: Add a script insertion helper for first-scene bootstrap**

```python
@mcp.tool()
async def attach_background_to_start(project_name: str, image_name: str) -> str:
    script_path = project_dir / "game" / "script.rpy"
    content = script_path.read_text(encoding="utf-8")
    updated = content.replace("label start:\n", f"label start:\n    scene {image_name}\n")
    script_path.write_text(updated, encoding="utf-8")
    return json.dumps({"success": True, "image_name": image_name}, ensure_ascii=False)
```

- [ ] **Step 6: Remove asset copy fallback from build manager once generated files already live in `game/images`**

Run: `pytest tests/unit/test_tools_asset_generation.py tests/unit/test_tools_project_creator.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/renpy_mcp/tools/assets.py src/renpy_mcp/tools/project.py src/renpy_mcp/services/build_manager.py tests/unit/test_tools_asset_generation.py tests/unit/test_tools_project_creator.py
git commit -m "feat: write generated assets into runnable project paths"
```

### Task 5: Expose Build and Preview as Dashboard Actions

**Files:**
- Modify: `dashboard/src/pages/ProjectWorkspacePage.tsx`
- Modify: `src/renpy_mcp/web/fastapi_app.py`
- Modify: `src/renpy_mcp/tools/preview.py`
- Modify: `src/renpy_mcp/services/build_manager.py`
- Modify: `src/renpy_mcp/services/preview_manager.py`
- Test: `tests/integration/test_fastapi_api.py`
- Test: `tests/unit/test_tools_web_preview.py`

- [ ] **Step 1: Write the failing API test for build and preview endpoints**

```python
def test_build_and_preview_endpoints(client: TestClient):
    build = client.post("/api/projects/build", json={"target": "web"})
    assert build.status_code == 200
    assert "success" in build.json()

    preview = client.post("/api/projects/preview")
    assert preview.status_code == 200
    assert preview.json()["url"].startswith("http://127.0.0.1:")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_fastapi_api.py -k build_and_preview_endpoints -v`
Expected: FAIL because the dashboard API has no such endpoints

- [ ] **Step 3: Add FastAPI endpoints that wrap existing build and preview services for the current project**

```python
@app.post("/api/projects/build")
async def api_build_project(request: Request, config: RenPyConfig = Depends(get_config)):
    if not config.project_path:
        raise HTTPException(status_code=400, detail="No current project")
    payload = await request.json()
    manager = BuildManager(get_settings())
    result = await manager.build(BuildRequest(project_name=config.project_path.name, target=payload.get("target", "web")))
    return result.model_dump(mode="json")
```

- [ ] **Step 4: Add workspace buttons that call build and preview endpoints and render the returned status**

```tsx
const handleBuild = async () => {
  setBuildState({ status: "running" });
  const resp = await fetch("/api/projects/build", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target: "web" }) });
  setBuildState(await resp.json());
};
```

- [ ] **Step 5: Add preview URL rendering and open-in-browser behavior only after a successful build**

Run: `pytest tests/integration/test_fastapi_api.py tests/unit/test_tools_web_preview.py -v`
Expected: PASS for build/preview API tests

- [ ] **Step 6: Commit**

```bash
git add dashboard/src/pages/ProjectWorkspacePage.tsx src/renpy_mcp/web/fastapi_app.py src/renpy_mcp/tools/preview.py src/renpy_mcp/services/build_manager.py src/renpy_mcp/services/preview_manager.py tests/integration/test_fastapi_api.py tests/unit/test_tools_web_preview.py
git commit -m "feat: expose build and preview in dashboard"
```

### Task 6: Restore Startup Readiness with SDK Provisioning

**Files:**
- Modify: `src/renpy_mcp/cli/app.py`
- Modify: `src/renpy_mcp/main.py`
- Modify: `src/renpy_mcp/services/sdk_provisioner.py`
- Test: `tests/unit/test_sdk_provisioner.py`

- [ ] **Step 1: Write the failing startup readiness test**

```python
def test_start_ensures_sdk(mocker):
    provisioner = mocker.patch("renpy_mcp.cli.app.SdkProvisioner")
    provisioner.return_value.ensure_sdk = AsyncMock()
    runner = CliRunner()
    result = runner.invoke(main, ["start", "--no-browser"])
    provisioner.return_value.ensure_sdk.assert_awaited()
    assert result.exit_code == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_sdk_provisioner.py -k start_ensures_sdk -v`
Expected: FAIL because `start` does not call `ensure_sdk`

- [ ] **Step 3: Call `ensure_sdk()` before serving the dashboard**

```python
provisioner = SdkProvisioner(settings)
asyncio.run(provisioner.ensure_sdk())
```

- [ ] **Step 4: Keep the startup path non-blocking when the SDK already exists**

Run: `pytest tests/unit/test_sdk_provisioner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/renpy_mcp/cli/app.py src/renpy_mcp/main.py src/renpy_mcp/services/sdk_provisioner.py tests/unit/test_sdk_provisioner.py
git commit -m "feat: ensure sdk readiness on startup"
```

### Task 7: Lock the Product Loop with End-to-End Acceptance Tests

**Files:**
- Modify: `tests/e2e/test_dashboard_playwright.py`
- Modify: `tests/integration/test_ws_chat.py`
- Modify: `tests/integration/test_fastapi_api.py`

- [ ] **Step 1: Rewrite the failing E2E scenario around the intended product loop**

```python
def test_dashboard_chat_generate_build(page: Page, server_url: str) -> None:
    page.goto(f"{server_url}/dashboard")
    page.locator("button:has-text('新建项目')").click()
    page.locator("input").fill(project_name)
    page.locator("button:has-text('创建')").click()
    page.locator(f"h4:has-text('{project_name}')").click()
    page.locator("button:has-text('AI 助手')").click()
    page.locator("textarea").fill("Generate a school rooftop background and build the web version")
    page.locator("button:has(.lucide-send)").click()
    page.locator("button:has-text('确认')").click()
    page.locator("button:has-text('确认')").click()
    expect(page.locator("text=success")).to_be_visible(timeout=120000)
```

- [ ] **Step 2: Run the E2E test to verify the remaining failures**

Run: `pytest tests/e2e/test_dashboard_playwright.py -v`
Expected: Any remaining failure must map to a broken step in the intended product loop, not to selector drift or missing setup

- [ ] **Step 3: Add integration assertions for project selection, chat binding, and build status payloads**

```python
assert build_payload["project_name"] == project_name
assert preview_payload["url"].endswith("/index.html")
```

- [ ] **Step 4: Run the focused acceptance suite**

Run: `pytest tests/integration/test_fastapi_api.py tests/integration/test_ws_chat.py tests/e2e/test_dashboard_playwright.py -v`
Expected: PASS

- [ ] **Step 5: Run the full regression suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/e2e/test_dashboard_playwright.py tests/integration/test_fastapi_api.py tests/integration/test_ws_chat.py
git commit -m "test: lock core feature loop acceptance coverage"
```

## Self-Review

**Spec coverage:** This plan covers the agreed requirements: current project context, dashboard workspace, chat project binding, generated content writing back into the project, build/preview actions, SDK readiness, and acceptance tests for the end-to-end loop.

**Placeholder scan:** No `TODO`, `TBD`, or deferred implementation markers remain in task steps.

**Type consistency:** The plan consistently uses `current_project`, `project_name`, `/api/projects/current`, `/api/projects/select`, `/api/projects/build`, and `/api/projects/preview` across frontend and backend tasks.
