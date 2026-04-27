# Workflow Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a desktop-first, state-driven workflow dashboard with obvious generation progress, a single recommended next action, and improved review/generation page hierarchy.

**Architecture:** Add focused React components for workflow state derivation, the top workflow header, the left workflow rail, and the generation flow panel. Keep API calls and existing project context intact; this is a frontend orchestration and presentation refactor.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind CSS, Vitest, Testing Library, Lucide icons.

---

## File Structure

- Modify: `.gitignore`
  - Stop accidentally ignoring `dashboard/src/lib`.
- Create: `dashboard/src/lib/utils.ts`
  - Shared `cn()` helper used by existing components.
- Create: `dashboard/src/lib/refinementAutomation.ts`
  - Track currently ignored helper required by `ProjectWorkspacePage`.
- Create: `dashboard/src/lib/refinementAutomation.test.ts`
  - Track tests for the freeze automation helper.
- Create: `dashboard/src/components/workspace/workflowState.ts`
  - Derive workflow stages, progress, and primary action from current project data.
- Create: `dashboard/src/components/workspace/WorkflowStatusHeader.tsx`
  - Render current workflow state and single primary CTA.
- Create: `dashboard/src/components/workspace/WorkflowRail.tsx`
  - Render stage rail plus existing chapter/scene navigation.
- Create: `dashboard/src/components/workspace/GenerationFlowPanel.tsx`
  - Render visible generation process cards.
- Modify: `dashboard/src/pages/ProjectWorkspacePage.tsx`
  - Wire workflow state, replace scattered top status with header, and use workflow rail.
- Modify: `dashboard/src/components/workspace/StepwiseGenerationView.tsx`
  - Add `GenerationFlowPanel` above asset lists and improve stage hierarchy.
- Modify: `dashboard/src/components/workspace/BriefWorkspaceView.tsx`
  - Add review progress header and improve confirmed-card hierarchy.
- Modify: `dashboard/src/components/workspace/ChapterOutlineWorkspaceView.tsx`
  - Add review progress header consistent with Brief.
- Test: `dashboard/src/pages/ProjectWorkspacePage.test.tsx`
- Test: `dashboard/src/components/workspace/StepwiseGenerationView.test.tsx`

## Task 1: Restore Trackable Frontend Baseline

- [ ] **Step 1: Update ignore rules**

Change `.gitignore` to add:

```gitignore
!dashboard/src/lib/
!dashboard/src/lib/**
```

- [ ] **Step 2: Add tracked helper files**

Add the existing `cn()` helper and `runFreezeAutoGenerationChain()` helper under `dashboard/src/lib`.

- [ ] **Step 3: Run baseline build**

Run:

```bash
cd dashboard
npm run build
```

Expected: TypeScript and Vite build complete.

## Task 2: Workflow State Derivation

- [ ] **Step 1: Write failing tests**

Add tests in `ProjectWorkspacePage.test.tsx` that expect:

- `Enter Brief Review` when intake has a brief draft ready.
- `Freeze Blueprint` when outline is confirmed and freeze is allowed.
- `Generate Scene Packages` when blueprint is frozen and generation is idle.

- [ ] **Step 2: Run tests and verify red**

Run:

```bash
cd dashboard
npm exec vitest run src/pages/ProjectWorkspacePage.test.tsx
```

Expected: fail because workflow header does not exist.

- [ ] **Step 3: Implement workflow state module and header**

Create `workflowState.ts` and `WorkflowStatusHeader.tsx`. Wire them into `ProjectWorkspacePage.tsx`.

- [ ] **Step 4: Run tests and verify green**

Run:

```bash
cd dashboard
npm exec vitest run src/pages/ProjectWorkspacePage.test.tsx
```

Expected: pass.

## Task 3: Workflow Rail

- [ ] **Step 1: Write failing tests**

Add a test that expects workflow stages `Intake`, `Brief`, `Outline`, `Scene Packages`, `Build`, and `Preview` to be visible in the workspace.

- [ ] **Step 2: Implement `WorkflowRail`**

Create the component and replace the direct `WorkspaceSidebar` usage with the rail wrapping stage state plus chapter/scene tree.

- [ ] **Step 3: Run tests**

Run:

```bash
cd dashboard
npm exec vitest run src/pages/ProjectWorkspacePage.test.tsx src/components/workspace/WorkspaceTabs.test.tsx
```

Expected: pass.

## Task 4: Generation Flow Panel

- [ ] **Step 1: Write failing tests**

Add expectations in `StepwiseGenerationView.test.tsx` for visible process cards: `Scene Packages`, `Character Assets`, `Scene Backgrounds`, `Script Preview`, `Build`, `Preview`.

- [ ] **Step 2: Implement `GenerationFlowPanel`**

Render flow cards above existing asset sections. Keep current asset APIs and buttons intact.

- [ ] **Step 3: Run tests**

Run:

```bash
cd dashboard
npm exec vitest run src/components/workspace/StepwiseGenerationView.test.tsx
```

Expected: pass.

## Task 5: Review Page Hierarchy

- [ ] **Step 1: Add review header assertions**

Update Brief/Outline tests to assert confirmed count and remaining count.

- [ ] **Step 2: Implement review headers**

Add compact review progress headers to Brief and Outline pages, visually prioritizing unconfirmed items.

- [ ] **Step 3: Run affected tests**

Run:

```bash
cd dashboard
npm exec vitest run src/components/workspace/BriefWorkspaceView.test.tsx src/components/workspace/ChapterOutlineWorkspaceView.test.tsx
```

Expected: pass.

## Task 6: Browser Verification

- [ ] **Step 1: Build dashboard**

Run:

```bash
cd dashboard
npm run build
```

- [ ] **Step 2: Start local server**

Run:

```bash
python -m renpy_mcp.main --transport http --port 8080
```

- [ ] **Step 3: Use superpowers-chrome**

Open desktop viewport at:

```text
http://127.0.0.1:8080/dashboard/projects
http://127.0.0.1:8080/dashboard/projects/123
```

Capture screenshots and inspect:

- Workflow header is visible.
- One primary CTA is visually dominant.
- Generation flow panel appears before asset tables.
- Desktop layout does not look like a generic admin page.

## Task 7: Final Regression

- [ ] **Step 1: Run targeted dashboard tests**

Run:

```bash
cd dashboard
npm exec vitest run src/pages/ProjectWorkspacePage.test.tsx src/components/workspace/StepwiseGenerationView.test.tsx src/components/workspace/WorkspaceTabs.test.tsx
```

- [ ] **Step 2: Run dashboard build**

Run:

```bash
cd dashboard
npm run build
```

- [ ] **Step 3: Run available E2E tests**

Run the dashboard E2E test if Playwright is installed in the environment:

```bash
python -m pytest tests/e2e/test_dashboard_playwright.py -v
```

If unavailable, report the blocker with the exact error.

