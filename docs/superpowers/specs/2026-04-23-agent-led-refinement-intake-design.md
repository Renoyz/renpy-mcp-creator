# Agent-Led Refinement Intake Design

## Scope

This design corrects the current Phase 7 entry flow so new projects begin with agent-led intake instead of blank structured forms.

It covers:

- agent-led project intake as the default new-project path
- a visible `Intake` workspace surface that mirrors agent understanding in real time
- `Project Brief Draft` generation from guided intake
- handoff from intake into the existing `Project Brief` review/confirmation workspace
- a second intake stage for `Chapter Outline Draft` generation after brief confirmation
- explicit distinction between:
  - intake
  - draft readiness
  - structured review
  - freeze

It does not cover:

- replacing the existing Brief / Outline review workspaces
- scene-level planning as a first-class review stage
- audit, preview evidence capture, or audit UI
- redesigning the general chat product outside the refinement path

## Problem

The current Phase 7 implementation successfully introduced:

- structured `Project Brief`
- structured `Chapter Outline`
- explicit confirmation gates
- explicit blueprint freeze

But it drifted from the original product intent.

The original requirement was:

- the **agent should lead the refinement process by asking questions**
- the system should produce drafts from those answers
- the user should then review and confirm the drafts

The current behavior instead starts the user in an editable structured workspace and effectively treats:

- blank Brief editing
- blank Outline editing

as the primary entry path.

This makes the product feel like a form editor instead of an agent-assisted refinement loop.

## Goal

Restore the intended refinement flow:

1. agent asks targeted intake questions
2. agent accumulates structured understanding
3. agent materializes `Project Brief Draft`
4. user performs structured review and confirmation
5. agent materializes `Chapter Outline Draft`
6. user performs structured review and confirmation
7. user explicitly freezes the blueprint

The Brief / Outline workspaces remain valid, but their role changes:

- they are no longer the starting point for new projects
- they become the **review / confirmation layer** for agent-produced drafts

## Product Requirement

For a truly new project, the primary path must no longer be:

- open workspace
- click `Create Brief`
- manually author the first draft from scratch

Instead, the primary path must become:

- open workspace
- enter `Intake`
- answer agent questions
- watch draft slots fill in
- move to `Brief Review` only after the agent declares the draft ready

Manual editing remains allowed, but only after agent drafting has reached an explicit ready state.

## Design Summary

Adopt a hybrid flow:

### 1. Agent-led intake

Chat remains the primary mechanism for collecting user intent.

The agent asks targeted project-level questions one at a time.

### 2. Intake panel as visible state

A dedicated `Intake` workspace surface displays:

- current project understanding
- missing required dimensions
- in-progress structured draft slots
- readiness to enter review

This prevents the intake loop from becoming a black box.

### 3. Structured review remains downstream

The existing Brief / Outline workspaces remain the place for:

- structured edits
- confirmation
- correction of agent-produced drafts

### 4. Freeze remains the final handoff

The existing Round 3 blueprint freeze stays unchanged as the final explicit handoff into downstream generation.

## User Flow

### Step 1. New project opens in Intake

For a new project with no refinement artifacts:

- workspace opens normally
- active tab defaults to `Intake`
- the agent begins intake
- the user is not dropped into blank Brief editing

The Intake panel shows:

- what is already known
- what is still missing
- whether the agent can produce the first draft

### Step 2. Project-level intake

The agent gathers only enough information to produce a stable `Project Brief Draft`.

Required dimensions:

- core premise
- audience / genre
- tone / themes
- visual style
- world rules
- core cast
- character identity
- relationship baselines
- constraints / no-go

The agent must not jump directly into scene planning or generation during this phase.

### Step 3. Project Brief Draft Ready

Once enough project-level information has been collected, the system marks:

- `brief_draft_ready = true`

The Intake panel then offers:

- `Enter Brief Review`

At this point the draft becomes editable in the existing Brief workspace.

### Step 4. Brief Review / Confirm

The user edits and confirms the existing structured Brief cards.

The current Brief confirmation contract remains valid:

- `character_identity` must pass semantic validation
- every card must be confirmed

### Step 5. Chapter intake begins only after Brief is confirmed

Once Brief is fully confirmed, the agent starts the second stage:

- `Chapter Outline Draft` intake / drafting

This stage may ask follow-up questions about:

- chapter count
- pacing
- reveal cadence
- chapter endpoints
- chapter-level relationship evolution

### Step 6. Chapter Outline Draft Ready

Once enough chapter-level information exists:

- `chapter_outline_draft_ready = true`

The user then enters the existing Outline review workspace to:

- edit chapters
- add/delete/reorder
- confirm each chapter

### Step 7. Explicit Freeze

The existing explicit blueprint freeze remains required after:

- Brief fully confirmed
- Outline fully confirmed

No change is made here except that the source of those reviewed artifacts now comes from agent-led intake rather than blank forms.

## Interaction Model

### Chat responsibilities

Chat is responsible for:

- asking targeted intake questions
- summarizing current understanding
- revising draft content based on user answers
- declaring when a draft is ready for review

Chat is not responsible for:

- silently skipping intake and writing executable blueprints
- bypassing the confirmation workspaces
- directly freezing the blueprint

### Intake panel responsibilities

The Intake panel is responsible for making the agent’s current structured understanding visible.

It must show:

- progress through required dimensions
- a “current understanding” summary
- draft slot previews
- readiness to transition into review

### Review workspace responsibilities

Brief / Outline workspaces remain responsible for:

- structured editing
- explicit confirmation
- correcting draft details

They are no longer responsible for acting as the first place a new user invents all project content from scratch.

## Drafting Rules

### Brief drafting

The system must not expose full blank Brief editing as the preferred new-project start.

Instead:

- the agent populates draft cards progressively
- the Intake panel displays those partial cards
- the user enters full Brief editing only after the draft is marked ready

### Chapter drafting

Chapter drafting must remain downstream of Brief confirmation.

The system must not default to a blank Outline editor for a project whose brief has not yet been confirmed.

## Editability Rules

User preference for this design:

- during intake, the user should **not** immediately receive unrestricted full-form editing
- instead, the user may see draft content and accept the transition to review
- only once the agent marks a draft ready does the user enter full structured editing

This means:

### During intake

- the user can answer the agent
- the user can see the draft forming
- the user cannot yet perform arbitrary full-brief editing

### During review

- the user can fully edit and confirm the structured artifact

## Recommended State Model

The current refinement states should remain, but this design adds an explicit intake layer above them.

Recommended high-level states:

- `intake_project`
- `brief_draft_in_progress`
- `brief_draft_ready`
- `brief_reviewing`
- `brief_confirmed`
- `intake_chapters`
- `chapter_outline_draft_in_progress`
- `chapter_outline_draft_ready`
- `chapter_outline_reviewing`
- `chapter_outline_confirmed`
- `blueprint_ready`
- `blueprint_frozen`
- `blueprint_stale`

The existing persisted `refinement_state` does not need to grow to all of these in one round.

Instead:

- some of these may be represented first as derived UI / API states
- persisted states should be added only where they materially affect gating

## Data Model Impact

### Existing persisted artifacts remain

Keep:

- `meta/project_brief.json`
- `meta/chapter_outline.json`
- `meta/project.json`
- `meta/blueprint.yaml`

### New intake-state storage

Add a lightweight persisted intake artifact, for example:

- `meta/refinement_intake.json`

Suggested responsibilities:

- track which intake phase is active
- store collected partial answers
- store draft-slot completeness
- record whether `brief_draft_ready` or `chapter_outline_draft_ready` has been reached

This file should not replace the formal Brief / Outline files.

Instead:

- intake file = in-progress agent understanding
- brief / outline files = reviewable structured draft artifacts

### Why a separate intake artifact is useful

Without a separate intake artifact, the system risks conflating:

- partially collected agent understanding
- user-reviewed structured draft

Those are not the same thing.

Keeping them separate avoids:

- pretending a partial draft is ready for confirmation
- letting a half-collected intake appear as a legitimate review artifact

## API Design

Minimum new API surface:

### Intake status

- `GET /api/projects/{name}/refinement-intake`

Returns:

- active intake phase
- collected slots
- missing slots
- current summary
- draft readiness flags

### Intake start / continue

This should not become a fake frontend state machine.

The chat system should remain the authority for asking intake questions, but the dashboard needs project-scoped endpoints to fetch the materialized intake state.

That means:

- chat writes intake progress
- workspace reads intake progress

### Promote draft into review

When the agent marks the project brief draft ready, the workspace should allow a transition such as:

- `POST /api/projects/{name}/brief/promote-draft`

or an equivalent explicit action.

This should:

- materialize the current draft as the editable `ProjectBrief`
- transition the user into review

Likewise later for chapter outline:

- `POST /api/projects/{name}/chapter-outline/promote-draft`

These endpoints should only operate on agent-prepared intake data, not invent new content on their own.

## UI Design

### New Intake tab

Add a dedicated `Intake` tab to the workspace.

This becomes the default active tab for a truly new project.

The Intake tab should show:

1. **Progress**
   - how many required dimensions are covered
   - what remains missing

2. **Current understanding**
   - a concise natural-language summary from the agent

3. **Draft slots**
   - visible structured slots for the current phase
   - project-level first
   - chapter-level later

4. **Transition action**
   - `Enter Brief Review` when brief draft is ready
   - later `Enter Chapter Review` when chapter draft is ready

### Existing Brief / Outline tabs

These tabs remain, but their empty-state copy and semantics should change:

- they are not the recommended first step for a new project
- if no draft has been promoted yet, they should explain:
  - “Start in Intake first”
  - or equivalent wording

### Blueprint tab

No major change in this design.

It remains downstream and should continue to reflect:

- no blueprint yet
- freeze-ready
- frozen
- stale

## Legacy Behavior

Legacy projects should remain compatible.

For a legacy project with:

- no intake artifact
- no Brief / Outline refinement files
- existing `blueprint.yaml`

the workspace should continue to:

- show legacy-ready semantics
- avoid fake intake state
- avoid forcing migration before viewing existing blueprint content

## Error Handling

The strict error semantics already established in Phase 7 must remain:

- missing file != invalid file
- invalid structured file should surface a clear error
- UI must not collapse backend failures into empty state

This applies equally to the new intake artifact:

- missing intake file may be valid for some project stages
- invalid intake file must surface as explicit error

## Testing Strategy

### Backend / integration

Add tests for:

- new projects defaulting to intake semantics
- intake status roundtrip
- draft-ready transitions
- promoting brief draft into review artifact
- chapter intake blocked until brief confirmed
- invalid intake artifact returning explicit 500

### Workspace / E2E

Add tests for:

- new project opens with `Intake` visible
- agent-produced brief draft appears in the Intake panel
- `Enter Brief Review` becomes available only when draft ready
- Brief tab no longer acts as the required first authoring surface
- chapter intake does not appear until brief confirmed

## Incremental Delivery Plan

This should be implemented in two sub-rounds rather than one large rewrite.

### Round 4A: Project Brief Intake

Deliver:

- `Intake` tab
- intake-state API / persistence
- project-level agent intake visibility
- brief draft readiness
- transition from intake to Brief review

Do not yet deliver:

- chapter intake

### Round 4B: Chapter Outline Intake

Deliver:

- chapter-level intake state
- chapter outline draft readiness
- transition from intake to Outline review

By splitting the work this way, the system can correct the product entry path without destabilizing the already-completed review and freeze layers.

## Recommendation

Treat the current Phase 7 work as:

- Round 1: backend refinement contract
- Round 2: review workspace
- Round 3: blueprint freeze

Then add:

- Round 4A: agent-led project intake
- Round 4B: agent-led chapter intake

This preserves the value of the existing implementation while correcting the product flow to match the original intent:

- the agent leads refinement
- the user reviews and confirms
- freeze remains explicit
