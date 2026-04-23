# AGENTS.md

This file is for AI coding agents working in this repository.

## Scope

- This file applies to AI coding agents only.
- Optimize for small, verifiable changes.
- Do not expand work into a later phase unless the user explicitly asks for it.

## Current Product State

- This repository is currently in early **Phase 6** of the dashboard/backend refactor plan.
- The active product loop is:
  - confirmed blueprint
  - prototype scene generation
  - background / sprite / font asset generation
  - script writeback
  - build / preview
- The current Phase 6 focus is:
  - multi-chapter generation
  - generation-before-audit consistency constraints
- Phase 7 owns:
  - audit
  - preview evidence capture / inspector
  - audit UI
  - Creator / Auditor handoff points
- The primary plan source is:
  - [`docs/plans/2026-04-17-dashboard-backend-refactor-plan.md`](docs/plans/2026-04-17-dashboard-backend-refactor-plan.md)

## Repo Map

- `src/renpy_mcp/`: Python backend, services, chat orchestration, FastAPI, asset pipeline
- `dashboard/`: React frontend
- `tests/`: unit, integration, and E2E coverage
- `workspace/`: local generated projects and debug artifacts
- `docs/`: plans and design notes

## Non-Negotiable Rules

- Write or update failing tests before implementation whenever feasible.
- Do not revert or delete user changes unless explicitly requested.
- Do not leak absolute local filesystem paths through persisted metadata or API responses.
- Do not treat placeholder assets as real generated assets.
- Do not break rollback or staged-replacement guarantees for prototype generation.
- Do not fix only the success path; failure and rollback behavior must be considered for any pipeline change.
- Do not introduce mock or simulate-only frontend flows into production codepaths.
- Do not pull audit work, preview evidence capture, or audit UI forward into Phase 6 unless explicitly requested.
- Do not let automated tests call real LLM or image-generation services by default.

## Prototype Pipeline Guardrails

Changes in these files are high risk and must preserve transactional safety:

- `src/renpy_mcp/web/chat_ws.py`
- `src/renpy_mcp/services/prototype_generation_service.py`
- `src/renpy_mcp/web/fastapi_app.py`

When changing the prototype pipeline, always account for:

- when assets are created
- when they become user-visible
- how they are rolled back on failure
- whether same-path regeneration can overwrite a stable prior asset

## Asset Rules

- Background and sprite metadata paths must use controlled project-relative paths, not absolute paths.
- Raw character images with failed background removal must not be shown in runtime scenes by default.
- Intermediate asset files such as raw, transparent, normalized, or staging variants must have a cleanup strategy.
- Script references, index metadata, and API payloads must stay consistent with each other.
- If an asset is not safe to render, suppress it explicitly instead of pretending it is valid.

## Frontend Rules

- The dashboard must consume real project-scoped APIs.
- Do not rely on error message strings as protocol.
- Do not reintroduce local fake state machines when a backend status endpoint already exists.
- Keep workspace views readable, but do not break current build/preview flows while improving presentation.

## Verification Requirements

At minimum, run the affected tests after each change:

- Backend / integration:
  - `uv run pytest tests/integration/...`
- Additional backend regression if relevant:
  - `uv run pytest tests/unit/...`
- Frontend build when frontend code changes:
  - `cd dashboard && npm run build`
- E2E when workflow, preview, or workspace behavior changes:
  - `uv run pytest tests/e2e/...`

For any test that touches generation paths:

- Stub `ImageService.generate_image(...)` when image output matters to the behavior under test.
- Or force `ImageService.is_available()` to be `False` when the test should exercise fallback behavior.
- Do not rely on local `.env` credentials or real external AI services during automated tests.

Do not claim a fix is complete without naming the tests run and their results.

## Preferred Workflow

1. Identify whether the change affects pipeline, assets, API, or UI.
2. Add or update tests first.
3. Make the smallest implementation change that satisfies the tests.
4. Run targeted regression tests.
5. Report:
   - what changed
   - what was verified
   - any remaining risks

## Known High-Risk Areas

- multi-chapter generation without breaking the current single-chapter prototype path
- generation-before-audit style consistency across chapters
- confirmation-response latency and websocket progress streaming
- prototype rollback transactional boundaries
- same-path regeneration of background and sprite assets
- sprite renderability and suppression rules
- runtime CJK font correctness in web preview
- path normalization between script, index, and API layers
- accidental use of real external AI credentials during tests
