# Staged Requirements Refinement Design

## Scope

This design introduces a mandatory staged refinement flow before formal blueprint freeze and downstream generation.

It covers:

- chat-driven idea intake
- structured `Project Brief` drafting and review
- structured `Chapter Outline` drafting and review
- stronger character-identity refinement before blueprint freeze
- mandatory confirmation gates before blueprint freeze
- chapter-level editing, add/delete, and reordering
- product-state gating before scene package / prototype generation

It does not yet cover:

- scene-level planning as a first-class review stage
- audit, preview evidence capture, or audit UI
- full planner-style redesign of the entire dashboard

## Goal

The current runtime flow moves from rough user intent to executable blueprint too quickly.

The new goal is to force the product to distinguish:

1. idea collection
2. project-level requirement convergence
3. chapter-level structure convergence
4. blueprint freeze

Only after those layers are explicitly confirmed should the system allow downstream generation.

This refinement must also lock character identity earlier than the current flow, so downstream generation does not invent or drift major character presentation after only minimal chat clarification.

## Product Requirement

The product must no longer treat “a few rounds of chat” as equivalent to “requirements are ready for generation”.

Instead, the system must require two explicit structured confirmation gates:

1. `Project Brief`
2. `Chapter Outline`

Both gates are mandatory.

Confirmation is granular:

- each brief card must be confirmed individually
- each chapter card must be confirmed individually

Advancement is global:

- all brief cards must be confirmed before chapter outline review can be completed
- all chapter cards must be confirmed before blueprint freeze can complete

The `Project Brief` gate must be strong enough to define who the main cast are, what they must remain like, and what kinds of character drift are unacceptable before any formal chapter planning is frozen.

## Design Summary

Adopt a hybrid flow:

### 1. Chat for collection

Chat remains the entry point for rough ideas, clarifications, and rewrites.

### 2. Structured review for convergence

The product then moves the user into explicit editable review surfaces for:

- project-level requirements
- chapter-level structure

### 3. Blueprint as frozen output

`Blueprint` is no longer the first structured artifact produced by chat alone.

It becomes the frozen output assembled from:

- confirmed project brief
- confirmed chapter outline

This separates:

- collection
- editing
- confirmation
- executable generation input

## User Flow

### Step 1. Idea Intake

The user starts in chat with rough intent, examples, and constraints.

The system may ask follow-up questions, but the goal is only to produce a `Project Brief Draft`.

The system must not jump directly to scene planning or prototype generation here.

### Step 2. Project Brief Draft

The system materializes a structured draft of project-level requirements.

Suggested cards:

- Core Premise
- Audience & Genre
- Tone & Themes
- Visual Style
- World Rules
- Core Cast
- Character Identity
- Character Relationship Baselines
- Constraints / No-Go

Each card supports:

- draft content
- user edits
- regenerate / rewrite assistance
- explicit confirmation

At this stage, character work must go beyond “list the names”.

The draft should capture at least for protagonist and major supporting cast:

- narrative role
- core motivation
- personality anchors
- visual identity anchors
- relationship baseline
- hard no-go drift

### Step 3. Project Brief Review Gate

The user must confirm every brief card.

Until all cards are confirmed:

- chapter outline may exist only as draft material
- blueprint freeze is blocked
- downstream generation is blocked

### Step 4. Chapter Outline Draft

Once the project brief is confirmed, the system generates a chapter outline draft.

Each chapter card should include at least:

- `chapter_name`
- `chapter_goal`
- `key_conflict`
- `emotional_arc`
- `reveals`
- `end_state`
- `mood_or_pacing_bias`
- `character_focus`
- `relationship_shift`
- `character_presentation_notes`

### Step 5. Chapter Outline Review Gate

The user can:

- edit chapter fields
- add chapters
- delete chapters
- reorder chapters
- confirm each chapter individually

Until all chapter cards are confirmed:

- blueprint freeze is blocked
- scene package generation is blocked
- prototype generation is blocked

### Step 6. Blueprint Freeze

Once the brief and chapter outline are fully confirmed, the system generates the formal frozen blueprint.

This becomes the handoff boundary to the existing Phase 5 / Phase 6 generation pipeline.

## State Machine

Recommended project-level states:

- `idea_collecting`
- `brief_draft`
- `brief_reviewing`
- `brief_confirmed`
- `chapter_outline_draft`
- `chapter_outline_reviewing`
- `chapter_outline_confirmed`
- `blueprint_ready`

### Transition Rules

#### `idea_collecting -> brief_draft`

Triggered when the system has enough chat input to materialize a first structured project brief draft.

#### `brief_draft -> brief_reviewing`

Triggered when the draft is shown in the structured review surface.

#### `brief_reviewing -> brief_confirmed`

Triggered only when every brief card is confirmed.

#### `brief_confirmed -> chapter_outline_draft`

Triggered when chapter outline generation starts from the confirmed brief.

#### `chapter_outline_draft -> chapter_outline_reviewing`

Triggered when the draft chapter set is available in the chapter review surface.

#### `chapter_outline_reviewing -> chapter_outline_confirmed`

Triggered only when every chapter card is confirmed.

#### `chapter_outline_confirmed -> blueprint_ready`

Triggered when the frozen blueprint is assembled and persisted.

## Data Model

### ProjectBrief

Recommended persisted location:

- `meta/project_brief.json`

Suggested shape:

```json
{
  "cards": {
    "core_premise": {
      "content": "...",
      "confirmed": false
    },
    "audience_genre": {
      "content": "...",
      "confirmed": false
    },
    "tone_themes": {
      "content": "...",
      "confirmed": false
    },
    "visual_style": {
      "content": "...",
      "confirmed": false
    },
    "world_rules": {
      "content": "...",
      "confirmed": false
    },
    "core_cast": {
      "content": "...",
      "confirmed": false
    },
    "character_identity": {
      "content": {
        "characters": [
          {
            "character_id": "protagonist",
            "name": "...",
            "story_role": "...",
            "core_motivation": "...",
            "personality_anchors": ["..."],
            "visual_identity_anchors": ["..."],
            "forbidden_drift": ["..."]
          }
        ]
      },
      "confirmed": false
    },
    "relationship_baselines": {
      "content": {
        "relationships": [
          {
            "pair": ["protagonist", "deuteragonist"],
            "baseline": "...",
            "must_preserve": ["..."]
          }
        ]
      },
      "confirmed": false
    },
    "constraints": {
      "content": "...",
      "confirmed": false
    }
  },
  "updated_at": "..."
}
```

### ChapterOutline

Recommended persisted location:

- `meta/chapter_outline.json`

Suggested shape:

```json
{
  "chapters": [
    {
      "chapter_id": "ch1",
      "order": 1,
      "chapter_name": "Chapter 1",
      "chapter_goal": "...",
      "key_conflict": "...",
      "emotional_arc": "...",
      "reveals": "...",
      "end_state": "...",
      "mood_or_pacing_bias": "...",
      "character_focus": ["protagonist", "deuteragonist"],
      "relationship_shift": "...",
      "character_presentation_notes": "...",
      "confirmed": false
    }
  ],
  "updated_at": "..."
}
```

### Blueprint

Formal frozen output remains:

- `meta/blueprint.yaml`

But its source changes:

- no direct chat-to-blueprint path
- blueprint is assembled from confirmed upstream layers

The frozen blueprint should carry forward character-shaping outputs from the brief and chapter outline rather than forcing downstream generation to infer them again from raw chat.

## Character Refinement Requirements

Character definition must become a first-class part of staged refinement, not an implicit side effect of later generation.

### Project-Level Character Requirements

Before `brief_confirmed`, the product should have stable draft coverage for:

- protagonist identity
- major supporting cast identity
- role in story
- motivation
- personality anchors
- visual identity anchors
- relationship baseline
- forbidden drift

This is still lighter than a full production character bible, but it must be strong enough to stabilize:

- blueprint chapter planning
- downstream text voice
- later sprite / presentation consistency work

### Chapter-Level Character Requirements

Chapter outline should not redefine characters.

It may only express chapter-bounded character movement such as:

- which characters are in focus
- what relationship shift occurs in this chapter
- what emotional pressure changes
- what presentation emphasis is relevant in this chapter

It must not silently replace project-level identity anchors.

## Editing Rules

### Project Brief

Each card is individually editable and confirmable.

If a confirmed brief card is edited:

- that card returns to unconfirmed
- downstream chapter outline should be marked stale or sent back to draft-review state if the edit is material

Edits to character identity, relationship baseline, or forbidden drift should be treated as materially invalidating for downstream chapter planning unless explicitly proven otherwise.

### Chapter Outline

Each chapter card supports:

- edit
- confirm
- delete
- insert new chapter
- reorder

If a confirmed chapter is edited, moved, or regenerated:

- that chapter returns to unconfirmed

If chapter additions, deletions, or reordering materially affect project structure:

- blueprint freeze must be invalidated until the outline is reconfirmed

If chapter-level character focus, relationship shift, or presentation notes change:

- that chapter returns to unconfirmed
- blueprint freeze must be invalidated until the affected chapter set is reconfirmed

## Gating Rules

### Before `brief_confirmed`

Blocked:

- final chapter outline confirmation
- blueprint freeze
- scene package generation
- prototype generation

### Before `chapter_outline_confirmed`

Blocked:

- blueprint freeze
- scene package generation
- prototype generation

### Before `blueprint_ready`

Blocked:

- `scene-packages/generate`
- prototype generation endpoints
- build / preview flows that assume a frozen blueprint exists

## Frontend / Workspace Model

The workspace should expose three distinct surfaces:

### 1. Brief

Project-level card review and confirmation surface.

### 2. Chapters

Chapter list / chapter card review surface with:

- field editing
- add/delete
- reorder
- per-chapter confirmation

### 3. Blueprint

Frozen-output surface showing the executable structure that downstream generation will consume.

This surface should not be the primary editing surface for early requirement refinement.

## Chat Responsibilities

Chat remains useful, but its role narrows.

Chat is responsible for:

- rough idea intake
- clarification questions
- rewriting individual cards
- helping the user refine language

Chat should explicitly gather enough character detail to populate the brief draft, including:

- who the protagonist is
- who the indispensable supporting cast are
- what each major character wants
- what must remain recognizable about each major character
- what relationship baselines must not drift early

Chat is not responsible for:

- silently treating rough answers as executable final requirements
- bypassing structured confirmation gates

## API / Service Implications

The exact API shape can be refined in implementation planning, but the design requires at least:

- project brief read / update / confirm operations
- chapter outline read / update / reorder / confirm operations
- blueprint freeze operation
- status endpoints that expose whether a project is blocked by missing confirmations

The backend should enforce the gate conditions, not rely on frontend-only workflow discipline.

The backend should also validate that character-identity cards are present before allowing `brief_confirmed`, rather than treating a sparse name-only cast list as sufficient.

## Failure and Rollback Semantics

This refinement flow is stateful and must preserve consistency.

Key requirements:

- partial confirmation cannot be misrepresented as full readiness
- upstream edits must invalidate downstream frozen outputs when necessary
- stale chapter outline data must not remain silently authoritative after brief changes
- blueprint freeze must reflect exactly the currently confirmed upstream state

If freeze fails:

- the previously stable frozen blueprint should remain authoritative
- the system should report the failure explicitly
- upstream draft/review data must remain intact

## Testing Strategy

At minimum, implementation should cover:

1. project brief draft persistence and readback
2. per-card brief confirmation rules
3. chapter outline persistence and readback
4. chapter add/delete/reorder behavior
5. character identity and relationship baseline persistence
6. chapter confirmation gating rules
7. upstream edit invalidates downstream readiness
8. character-identity edits invalidate downstream chapter / blueprint readiness
9. blueprint freeze is blocked before all confirmations complete
10. blueprint freeze succeeds only from confirmed upstream layers
11. scene package / prototype generation endpoints reject requests before `blueprint_ready`
12. workspace status endpoints reflect the new refinement states accurately

## Recommended Rollout

### Phase 7 Round 1

- add `project_brief.json`
- add `chapter_outline.json`
- add state machine transitions and backend gating
- expose minimal read/write/confirm APIs

### Phase 7 Round 2

- build structured workspace surfaces for Brief and Chapters
- support add/delete/reorder for chapters
- show blocked readiness states clearly

### Phase 7 Round 3

- implement blueprint freeze from confirmed upstream layers
- remove direct chat-to-blueprint bypasses
- wire existing generation endpoints to `blueprint_ready`

## Recommendation

Adopt a mandatory staged refinement funnel:

- chat collection
- project brief confirmation
- chapter outline confirmation
- blueprint freeze

This is the smallest product change that directly addresses the current problem:

- requirement refinement is too compressed
- project-level and chapter-level convergence are not explicit enough
- downstream generation starts before the user has actually locked requirements

It preserves the existing chat-led experience while giving the system the structured gates it currently lacks.
