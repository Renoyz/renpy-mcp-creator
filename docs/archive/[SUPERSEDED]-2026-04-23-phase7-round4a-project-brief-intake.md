# [ARCHIVED - SUPERSEDED] 2026-04-23-phase7-round4a-project-brief-intake

> **Date archived:** 2026-04-26
> **Status:** SUPERSEDED
> **Reason:** Project brief intake is implemented and working (verified in E2E: 07_intake_draft_ready.png generated). Plan checkboxes are stale.
>
> This document has been moved to . Original content preserved below.

---

# Phase 7 Round 4A Project Brief Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make agent-led intake the default entry path for new projects and materialize a project-scoped `Project Brief Draft` before users enter full Brief review.

**Architecture:** Add a lightweight persisted intake artifact and API so chat can write project-level intake progress while the workspace reads and displays it. Keep the existing Brief review and confirmation flow intact, but insert a new `Intake` workspace tab as the first-class entry for new projects. Promotion from intake to review becomes an explicit backend action that writes the editable `project_brief.json`.

**Tech Stack:** FastAPI, WebSocket chat orchestration, Pydantic models, ProjectManager JSON persistence, React workspace UI, pytest integration tests, Playwright E2E.

---

### Task 1: Intake Persistence Contract

**Files:**
- Modify: `src/renpy_mcp/blueprint/models.py`
- Modify: `src/renpy_mcp/blueprint/__init__.py`
- Modify: `src/renpy_mcp/services/project_manager.py`
- Test: `tests/integration/test_requirements_refinement_phase7_round1.py`

- [ ] **Step 1: Write the failing tests**

Add integration tests for intake persistence and strict semantics:

```python
def test_refinement_intake_roundtrip_uses_structured_model(...):
    ...

def test_get_refinement_intake_returns_404_when_missing(...):
    ...

def test_invalid_refinement_intake_file_raises_value_error(...):
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
uv run pytest tests/integration/test_requirements_refinement_phase7_round1.py -k "refinement_intake_roundtrip or invalid_refinement_intake"
```

Expected: FAIL because no intake model or persistence exists yet.

- [ ] **Step 3: Write the minimal intake model**

Add a focused intake contract in `src/renpy_mcp/blueprint/models.py`:

```python
class IntakePhase(str, Enum):
    PROJECT = "project"
    BRIEF_READY = "brief_ready"


class IntakeSlot(BaseModel):
    value: str | dict[str, Any] | None = None
    complete: bool = False


class RefinementIntake(BaseModel):
    phase: IntakePhase = IntakePhase.PROJECT
    current_summary: str = ""
    missing_slots: list[str] = Field(default_factory=list)
    slots: dict[str, IntakeSlot] = Field(default_factory=dict)
    brief_draft_ready: bool = False
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

Keep scope narrow:
- no chapter intake yet
- no freeze coupling
- no duplicated confirmation state

- [ ] **Step 4: Add ProjectManager read/write methods**

Implement strict persistence in `src/renpy_mcp/services/project_manager.py`:

```python
def read_refinement_intake(self, name: str) -> RefinementIntake | None:
    ...

def write_refinement_intake(self, name: str, intake: RefinementIntake) -> None:
    ...
```

Behavior:
- missing file -> `None`
- invalid JSON / invalid structure -> `ValueError`

- [ ] **Step 5: Run tests to verify they pass**

Run:

```powershell
uv run pytest tests/integration/test_requirements_refinement_phase7_round1.py -k "refinement_intake_roundtrip or invalid_refinement_intake"
```

Expected: PASS


### Task 2: Intake API and Promotion to Brief Review

**Files:**
- Modify: `src/renpy_mcp/web/fastapi_app.py`
- Test: `tests/integration/test_requirements_refinement_phase7_round1.py`

- [ ] **Step 1: Write the failing API tests**

Add tests for:

```python
def test_refinement_intake_status_returns_structured_project_intake(...):
    ...

def test_promote_brief_draft_materializes_project_brief(...):
    ...

def test_promote_brief_draft_requires_brief_draft_ready(...):
    ...

def test_refinement_status_for_new_project_exposes_intake_entry_state(...):
    ...
```

Use a seeded intake artifact with slots like:

```python
{
    "phase": "project",
    "current_summary": "Sci-fi mystery about a missing brother.",
    "missing_slots": ["relationship_baselines", "constraints"],
    "slots": {
        "core_premise": {"value": "Sci-fi mystery...", "complete": True},
        "audience_genre": {"value": "YA sci-fi mystery", "complete": True},
    },
    "brief_draft_ready": False,
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
uv run pytest tests/integration/test_requirements_refinement_phase7_round1.py -k "promote_brief_draft or refinement_intake_status"
```

Expected: FAIL because no intake API exists yet.

- [ ] **Step 3: Add minimal intake endpoints**

Implement in `src/renpy_mcp/web/fastapi_app.py`:

```python
@app.get("/api/projects/{project_name}/refinement-intake")
async def api_project_refinement_intake(project_name: str):
    ...

@app.post("/api/projects/{project_name}/brief/promote-draft")
async def api_project_brief_promote_draft(project_name: str):
    ...
```

Rules:
- `GET /refinement-intake`
  - 404 when intake missing
  - 500 on invalid intake file
- `POST /brief/promote-draft`
  - 409 unless `brief_draft_ready == True`
  - creates `ProjectBrief` from intake slots
  - writes `meta/project_brief.json`
  - updates `meta.project.json` so refinement enters `brief_reviewing`

- [ ] **Step 4: Extend refinement-status with intake-facing fields**

Add minimal derived fields to `GET /api/projects/{name}/refinement-status`:

```python
{
    ...existing_fields,
    "intake_phase": "project" | "brief_ready" | None,
    "brief_draft_ready": bool,
    "intake_required": bool,
}
```

Rules:
- truly new project -> `intake_required = true`
- intake exists but no brief yet -> report intake state
- once brief exists -> existing review semantics continue

- [ ] **Step 5: Run tests to verify they pass**

Run:

```powershell
uv run pytest tests/integration/test_requirements_refinement_phase7_round1.py -k "promote_brief_draft or refinement_intake_status"
```

Expected: PASS


### Task 3: Chat Writes Project Intake State

**Files:**
- Modify: `src/renpy_mcp/web/chat_ws.py`
- Test: `tests/integration/test_ws_chat_blueprint.py`

- [ ] **Step 1: Write the failing chat integration tests**

Add tests for:

```python
def test_start_blueprint_collection_initializes_project_intake_state(...):
    ...

def test_collecting_turn_updates_refinement_intake_summary_and_slots(...):
    ...

def test_reviewing_transition_marks_brief_draft_ready_in_intake(...):
    ...
```

Keep the provider mocked. Assert the backend writes a project-scoped intake artifact while staying in the existing blueprint collection flow.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
uv run pytest tests/integration/test_ws_chat_blueprint.py -k "refinement_intake or brief_draft_ready"
```

Expected: FAIL because chat does not write intake state yet.

- [ ] **Step 3: Add minimal intake write-through in chat_ws**

When the project enters collecting/reviewing stages, write a lightweight intake snapshot:

```python
intake = RefinementIntake(
    phase=IntakePhase.PROJECT,
    current_summary=summary_text,
    missing_slots=[...],
    slots={
        "core_premise": IntakeSlot(value=premise, complete=bool(premise)),
        "audience_genre": IntakeSlot(value=audience, complete=bool(audience)),
        ...
    },
    brief_draft_ready=(pipeline_stage == "reviewing"),
)
pm.write_refinement_intake(project_name, intake)
```

Minimal rule for Round 4A:
- collecting -> partial slots, `brief_draft_ready = False`
- reviewing -> `brief_draft_ready = True`

Do not add chapter intake yet.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
uv run pytest tests/integration/test_ws_chat_blueprint.py -k "refinement_intake or brief_draft_ready"
```

Expected: PASS


### Task 4: Intake Workspace UI

**Files:**
- Modify: `dashboard/src/context/ProjectContext.tsx`
- Modify: `dashboard/src/components/workspace/WorkspaceTabs.tsx`
- Create: `dashboard/src/components/workspace/IntakeWorkspaceView.tsx`
- Modify: `dashboard/src/pages/ProjectWorkspacePage.tsx`
- Test: `tests/e2e/test_refinement_workspace_playwright.py`

- [ ] **Step 1: Write the failing E2E tests**

Add E2E coverage for:

```python
def test_workspace_new_project_defaults_to_intake_tab(...):
    ...

def test_workspace_intake_view_shows_agent_summary_and_missing_slots(...):
    ...

def test_workspace_brief_review_is_not_primary_before_draft_ready(...):
    ...

def test_workspace_promote_brief_draft_enters_brief_review(...):
    ...
```

Cover two states:
- no intake yet / totally new project
- seeded intake with `brief_draft_ready = True`

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
uv run pytest tests/e2e/test_refinement_workspace_playwright.py -k "intake_tab or brief_draft_ready"
```

Expected: FAIL because no Intake tab or intake UI exists yet.

- [ ] **Step 3: Extend ProjectContext for intake data**

Add types and methods:

```ts
export interface IntakeSlot {
  value: string | Record<string, unknown> | null;
  complete: boolean;
}

export interface RefinementIntake {
  phase: string;
  current_summary: string;
  missing_slots: string[];
  slots: Record<string, IntakeSlot>;
  brief_draft_ready: boolean;
}
```

Context additions:
- `refinementIntake`
- `refinementIntakeError`
- `loadRefinementIntake(name)`
- `promoteBriefDraft(name)`

404 remains empty intake state. Non-404 errors surface as error state.

- [ ] **Step 4: Add Intake tab and view**

Create `dashboard/src/components/workspace/IntakeWorkspaceView.tsx` with:

```tsx
export function IntakeWorkspaceView({ intake, error, onPromoteBriefDraft, projectName }: Props) {
  ...
}
```

Render:
- current summary
- missing slots
- current slot values
- CTA:
  - disabled / hidden when `brief_draft_ready` is false
  - enabled `Enter Brief Review` when true

Do not allow full Brief editing here.

- [ ] **Step 5: Rewire workspace entry path**

Modify `ProjectWorkspacePage.tsx`:
- add `intake` tab
- for truly new project, default active tab becomes `intake`
- Brief tab remains visible, but if no promoted brief yet it should explain:
  - “Start in Intake first”
  - not encourage blank authoring as the primary path

- [ ] **Step 6: Run tests to verify they pass**

Run:

```powershell
uv run pytest tests/e2e/test_refinement_workspace_playwright.py -k "intake_tab or brief_draft_ready"
cd dashboard; npm run build
```

Expected: E2E PASS and dashboard build succeeds.


### Task 5: Regression Verification

**Files:**
- Test only

- [ ] **Step 1: Run refinement integration regression**

Run:

```powershell
uv run pytest tests/integration/test_requirements_refinement_phase7_round1.py
```

Expected: PASS

- [ ] **Step 2: Run chat blueprint regression**

Run:

```powershell
uv run pytest tests/integration/test_ws_chat_blueprint.py
```

Expected: PASS

- [ ] **Step 3: Run refinement workspace E2E**

Run:

```powershell
uv run pytest tests/e2e/test_refinement_workspace_playwright.py
```

Expected: PASS

- [ ] **Step 4: Run affected FastAPI regression**

Run:

```powershell
uv run pytest tests/integration/test_fastapi_api.py
```

Expected: PASS

- [ ] **Step 5: Build dashboard**

Run:

```powershell
cd dashboard
npm run build
```

Expected: build succeeds
