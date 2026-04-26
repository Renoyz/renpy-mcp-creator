# [ARCHIVED - SUPERSEDED] 2026-04-23-phase7-round3-blueprint-freeze

> **Date archived:** 2026-04-26
> **Status:** SUPERSEDED
> **Reason:** Blueprint freeze is implemented and working (verified in E2E: 12_blueprint_frozen.png generated). Plan checkboxes are stale.
>
> This document has been moved to . Original content preserved below.

---

# Phase 7 Round 3 Blueprint Freeze Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit Blueprint Freeze handoff so downstream scene/package generation only runs from a confirmed and freshly frozen `blueprint.yaml`.

**Architecture:** Extend the refinement contract with a separate freeze-status layer persisted in `meta/project.json`, add a backend freeze endpoint that assembles and atomically replaces `meta/blueprint.yaml` with backup/rollback semantics, and expose the new state through `/refinement-status`. Then wire the workspace to show freeze readiness, stale state, and a user-triggered `Freeze Blueprint` action.

**Tech Stack:** FastAPI, Pydantic models, ProjectManager YAML persistence, React workspace UI, Playwright E2E, pytest integration tests.

---

### Task 1: Backend Freeze Contract

**Files:**
- Modify: `src/renpy_mcp/blueprint/models.py`
- Modify: `src/renpy_mcp/web/fastapi_app.py`
- Test: `tests/integration/test_requirements_refinement_phase7_round1.py`

- [ ] **Step 1: Write the failing tests**

Add integration tests for:

```python
def test_refinement_status_requires_frozen_blueprint_for_generation(...):
    ...

def test_freeze_blueprint_creates_blueprint_and_marks_project_frozen(...):
    ...

def test_upstream_edit_marks_frozen_blueprint_stale(...):
    ...

def test_generation_gate_rejects_blueprint_ready_but_not_frozen(...):
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
uv run pytest tests/integration/test_requirements_refinement_phase7_round1.py -k "frozen_blueprint or freeze_blueprint or stale_blueprint or not_frozen"
```

Expected: FAIL because no freeze-status model or freeze endpoint exists yet.

- [ ] **Step 3: Add the minimal backend contract**

Implement:

- `BlueprintFreezeStatus` enum in `src/renpy_mcp/blueprint/models.py`
- `ProjectMeta.blueprint_freeze_status`
- read-only `_compute_refinement_state(...)` keeps planning readiness only
- new helpers in `fastapi_app.py`:
  - assemble blueprint from confirmed brief + outline
  - compute generation_allowed as `planning ready + freeze status frozen`
  - mark freeze status `stale` on upstream brief/outline changes

- [ ] **Step 4: Add the explicit freeze endpoint**

Implement:

```python
@app.post("/api/projects/{project_name}/blueprint/freeze")
async def api_project_blueprint_freeze(project_name: str):
    ...
```

Behavior:
- reject unless brief/outline are fully confirmed
- build a `ProjectBlueprint` from current confirmed upstream data
- backup old `meta/blueprint.yaml` if it exists
- replace the authoritative blueprint
- persist `blueprint_freeze_status = frozen`
- rollback blueprint/meta on failure

- [ ] **Step 5: Run tests to verify they pass**

Run:

```powershell
uv run pytest tests/integration/test_requirements_refinement_phase7_round1.py -k "frozen_blueprint or freeze_blueprint or stale_blueprint or not_frozen"
```

Expected: PASS


### Task 2: Freeze Rollback and Re-freeze Safety

**Files:**
- Modify: `src/renpy_mcp/web/fastapi_app.py`
- Test: `tests/integration/test_requirements_refinement_phase7_round1.py`

- [ ] **Step 1: Write the failing rollback tests**

Add tests for:

```python
def test_freeze_blueprint_rolls_back_when_meta_persist_fails(...):
    ...

def test_freeze_blueprint_replaces_existing_blueprint_and_keeps_backup(...):
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
uv run pytest tests/integration/test_requirements_refinement_phase7_round1.py -k "freeze_blueprint_rolls_back or keeps_backup"
```

Expected: FAIL because rollback/backup behavior is not fully implemented yet.

- [ ] **Step 3: Implement minimal file-level transaction safety**

Ensure freeze:
- snapshots old blueprint/meta text
- writes new blueprint
- persists frozen status
- restores old blueprint/meta on any exception
- stores previous authoritative blueprint at a stable backup path

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
uv run pytest tests/integration/test_requirements_refinement_phase7_round1.py -k "freeze_blueprint_rolls_back or keeps_backup"
```

Expected: PASS


### Task 3: Workspace Freeze UI

**Files:**
- Modify: `dashboard/src/context/ProjectContext.tsx`
- Modify: `dashboard/src/components/workspace/RefinementStatusPanel.tsx`
- Modify: `dashboard/src/components/workspace/BlueprintWorkspaceView.tsx`
- Modify: `dashboard/src/pages/ProjectWorkspacePage.tsx`
- Test: `tests/e2e/test_refinement_workspace_playwright.py`

- [ ] **Step 1: Write the failing workspace tests**

Add E2E coverage for:

```python
def test_workspace_shows_freeze_action_when_refinement_ready(...):
    ...

def test_workspace_freeze_action_creates_frozen_blueprint(...):
    ...

def test_workspace_upstream_edit_marks_blueprint_stale(...):
    ...

def test_workspace_generation_stays_blocked_until_freeze(...):
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
uv run pytest tests/e2e/test_refinement_workspace_playwright.py -k "freeze_action or blueprint_stale or until_freeze"
```

Expected: FAIL because the workspace does not expose freeze state/actions yet.

- [ ] **Step 3: Implement the minimal workspace contract**

Add to `ProjectContext`:
- `blueprint_freeze_status`
- `freeze_allowed`
- `freezeBlueprint(name)`

Render in workspace:
- freeze CTA when `freeze_allowed` and status is `not_frozen` or `stale`
- frozen/stale badges
- blocked messaging that distinguishes planning-ready vs frozen-ready

Keep UI minimal:
- no version history
- no freeze wizard
- no later-phase audit coupling

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
uv run pytest tests/e2e/test_refinement_workspace_playwright.py -k "freeze_action or blueprint_stale or until_freeze"
```

Expected: PASS


### Task 4: End-to-End Regression Verification

**Files:**
- Test only

- [ ] **Step 1: Run targeted refinement integration regression**

Run:

```powershell
uv run pytest tests/integration/test_requirements_refinement_phase7_round1.py
```

Expected: PASS

- [ ] **Step 2: Run refinement workspace E2E**

Run:

```powershell
uv run pytest tests/e2e/test_refinement_workspace_playwright.py
```

Expected: PASS

- [ ] **Step 3: Run affected FastAPI regression**

Run:

```powershell
uv run pytest tests/integration/test_fastapi_api.py
```

Expected: PASS

- [ ] **Step 4: Build the dashboard**

Run:

```powershell
cd dashboard; npm run build
```

Expected: build succeeds

- [ ] **Step 5: Run prototype generation regression if generation gating changed**

Run:

```powershell
uv run pytest tests/integration/test_prototype_generation_phase6_round1.py tests/integration/test_prototype_generation_phase6_round2.py tests/integration/test_prototype_generation_phase6_round3.py tests/integration/test_prototype_generation_phase6_round4.py
```

Expected: PASS
