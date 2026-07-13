# Workflow Dashboard Redesign Design

## Goal

Redesign the desktop dashboard into a state-driven creative workflow cockpit that makes the generation process obvious, actionable, and reviewable. Mobile layout is explicitly out of scope for this phase.

## Constraints

- Preserve the real project-scoped API flow.
- Do not introduce mock-only production paths.
- Do not pull Phase 8 audit UI into this work.
- Keep current build and preview behavior intact.
- Keep the existing React/Vite/Tailwind stack.
- Target the `ui-ux-pro-max` benchmark score of 9/10 for the desktop workflow experience.

## Design Standard

The UI should feel like a professional creative operations tool: closer to Linear plus GitHub Actions plus a visual novel authoring desk than a generic admin panel.

Use:

- Indigo/blue for primary flow state.
- Emerald/green for complete and ready states.
- Amber for waiting or review states.
- Red for failed states.
- White cards, light gray work surface, thin borders, restrained shadows.
- Lucide icons only.
- One primary action per workflow state.

Avoid:

- Marketing hero layouts.
- Large decorative gradients.
- Multiple competing primary buttons.
- Chat bubbles for structured workflow output.
- Hidden workflow progress behind technical logs.

## Information Architecture

The desktop workspace keeps three zones:

1. Top: `WorkflowStatusHeader`
   - Shows current stage, overall step count, stage explanation, and one recommended action.
   - Secondary build/package/refresh actions move into lower-priority controls.
   - Announces errors and running state visually.

2. Left: `WorkflowRail`
   - Shows the production flow: Intake, Brief, Outline, Blueprint, Scene Packages, Characters, Backgrounds, Script, Build, Preview.
   - Shows scene/chapter tree under the flow.
   - Chapter/scene status remains visible while the user reviews details.

3. Center: active stage workspace
   - Existing tabs remain, but the active tab should be visually subordinate to workflow state.
   - Brief and Outline use review-queue styling.
   - Generation becomes a visible production board.

4. Right: AI and activity panel
   - Existing docked `ChatDrawer` remains.
   - Structured workflow status should be readable outside the chat stream.

## Workflow State Model

Use these UI statuses:

- `locked`: unavailable until an earlier stage completes.
- `ready`: next available action.
- `running`: operation in progress.
- `needs_review`: user confirmation required.
- `done`: completed.
- `failed`: operation failed and needs recovery.

Map existing project data into the workflow:

- Missing intake: Intake is ready.
- Brief draft ready but not fully confirmed: Brief needs review.
- Outline draft ready but not fully confirmed: Outline needs review.
- Freeze allowed or stale blueprint: Blueprint needs review/freeze.
- Frozen blueprint with incomplete scene generation: Scene Packages ready/running.
- Character asset draft: Characters needs review.
- Background asset draft: Backgrounds needs review.
- Script preview state: Script ready/done.
- Successful web build: Preview ready.

## Components

### WorkflowStatusHeader

Purpose: give the user a single source of truth for what is happening and what to do next.

Content:

- Stage label: `Step 4 of 9`
- Title: current stage.
- Subtitle: short plain-language explanation.
- Progress bar based on completed stages.
- Primary CTA.
- Secondary actions for build/package/preview when available.
- Failure banner with recovery copy.

### WorkflowRail

Purpose: make progress visible even while the center pane changes.

Content:

- Compact stage list with status icons.
- Chapter and scene navigation.
- Current active scene remains highlighted.

### GenerationFlowPanel

Purpose: replace the table-first generation view with a production-flow view.

Content:

- Step cards for Scene Packages, Characters, Backgrounds, Script, Build, Preview.
- Each card shows state, count, current object, and action.
- Asset lists stay below the flow panel.

### ReviewQueueHeader

Purpose: make Brief and Outline review pages easier to scan.

Content:

- Confirmed count.
- Remaining count.
- Recommended next action.
- Review cards visually prioritize unconfirmed content.

## Error Handling

- Errors appear in visible banners, not only console or chat.
- Failed workflow stages show `Retry` or route the user to the stage that can recover.
- Build and preview errors keep their existing backend messages but are shown under the workflow header.
- Dynamic error containers should use `role="alert"` in implementation where feasible.

## Testing

Add or update dashboard tests for:

- Workflow header chooses the correct primary action from mocked project state.
- Workflow rail renders generation stages and selected scene navigation.
- Generation view renders step cards before asset tables.
- Build controls still call the same API endpoints.
- Existing workspace and generation tests continue to pass.

Verification commands:

- `npm exec vitest run src/pages/ProjectWorkspacePage.test.tsx src/components/workspace/StepwiseGenerationView.test.tsx src/components/workspace/WorkspaceTabs.test.tsx`
- `npm run build`
- Relevant E2E dashboard test if available.
- Browser screenshots with `superpowers-chrome` at desktop viewport.

