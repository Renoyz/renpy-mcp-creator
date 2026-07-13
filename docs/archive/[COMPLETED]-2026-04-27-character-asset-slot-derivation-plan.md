# Character Asset Slot Derivation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derive Character Assets from completed character design so users review/fill a generated list instead of retyping character names.

**Architecture:** Extend `StepwiseGenerationService` to collect character requirements from scene packages, blueprint, and project brief, then attach metadata to `character_sprite` slots. Update `StepwiseGenerationView` to render that metadata on slot cards while keeping manual entry only for empty fallback cases.

**Tech Stack:** Python service/tests, FastAPI integration tests, React/TypeScript dashboard tests.

---

### Task 1: Backend Character Slot Derivation

**Files:**
- Modify: `src/renpy_mcp/services/stepwise_generation_service.py`
- Test: `tests/unit/test_stepwise_generation_service.py`

- [ ] Add failing tests that `start_characters()` creates slots from `blueprint.characters` and `project_brief.character_identity`.
- [ ] Run targeted unit tests and verify they fail because only scene packages currently create character slots.
- [ ] Implement character requirement collection and metadata attachment.
- [ ] Verify targeted tests pass.

### Task 2: Frontend Character List Rendering

**Files:**
- Modify: `dashboard/src/context/ProjectContext.tsx`
- Modify: `dashboard/src/components/workspace/StepwiseGenerationView.tsx`
- Test: `dashboard/src/components/workspace/StepwiseGenerationView.test.tsx`

- [ ] Add failing tests that derived character metadata appears in slot cards and empty manual entry is not shown when slots exist.
- [ ] Run targeted Vitest and verify failure.
- [ ] Add optional metadata fields to `AssetSlot` and render role/appearance/source in character cards.
- [ ] Verify targeted Vitest passes.

### Task 3: Regression Verification

**Files:**
- Test: `tests/integration/test_stepwise_generation_api.py`
- Test: `tests/e2e/test_dashboard_playwright.py`

- [ ] Run stepwise service unit tests.
- [ ] Run stepwise API integration tests.
- [ ] Run dashboard component tests.
- [ ] Run dashboard build.
- [ ] Run generation-tab E2E smoke.

