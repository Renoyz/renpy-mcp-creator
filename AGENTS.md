# AGENTS.md

This file is for AI coding agents working in this repository.

## Scope

- This file applies to AI coding agents only.
- Optimize for small, verifiable changes.
- Do not expand work into a later phase unless the user explicitly asks for it.

## Current Product State

- The core pipeline is operational: create project → AI intake → brief → outline → blueprint freeze → multi-chapter scenes → asset review → script commit/rollback → build/preview.
- Historical evidence includes one real-LLM E2E run covering 14/14 stages in about 132 seconds. Real-LLM tests remain manual and are not a per-commit guarantee.
- Completed capabilities include adaptive refinement, position-aware narrative guidance, stepwise generation/import, derived asset slots, Game Shell, and the workflow Dashboard redesign.
- The project is now an open-source (MIT), non-commercial effort: priorities are release hygiene, GitHub publication, and community feedback. Installer/packaging work is deferred until user demand appears. The four known integration failures and the preview-process cleanup were fixed on 2026-07-19.
- Product differentiation work is ordered as GameIR v1 → Asset Manifest Protocol → generated/user ownership → compiler diagnostics.
- Dual-agent audit, another broad UI redesign, more providers, and hosted SaaS work are deferred until user validation succeeds.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) is the authoritative current-status document.
- [`docs/README.md`](docs/README.md) indexes active and archived documentation.
- [`docs/vn-engineering-middleware-gap-analysis.md`](docs/vn-engineering-middleware-gap-analysis.md) records the active product direction.
- [`docs/dual-agent-design.md`](docs/dual-agent-design.md) is a future design, not an active phase.

## Repo Map

- `src/renpy_mcp/`: Python backend, services, chat orchestration, FastAPI, asset pipeline
- `dashboard/`: React frontend
- `desktop/`: Electron desktop shell
- `packaging/`: PyInstaller configuration and Windows build scripts
- `tests/`: unit, integration, and E2E coverage
- `workspace/`: local generated projects and debug artifacts
- `docs/`: current roadmap, design documents, and documentation index
  - `docs/archive/`: completed, partial, or superseded plans and prompts
  - `docs/superpowers/specs/`: approved active design specifications
  - `docs/superpowers/plans/`: active implementation plans

## Non-Negotiable Rules

- Write or update failing tests before implementation whenever feasible.
- Do not revert or delete user changes unless explicitly requested.
- Do not leak absolute local filesystem paths through persisted metadata or API responses.
- Do not treat placeholder assets as real generated assets.
- Do not break rollback or staged-replacement guarantees for prototype generation.
- Do not fix only the success path; failure and rollback behavior must be considered for any pipeline change.
- Do not introduce mock or simulate-only frontend flows into production codepaths.
- Do not pull deferred dual-agent audit, preview evidence capture, or audit UI forward unless explicitly requested.
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
  - `python -m pytest tests/integration/... -x -q`
- Additional backend regression if relevant:
  - `python -m pytest tests/unit/... -x -q`
- Frontend build when frontend code changes:
  - `cd dashboard && npm run build`
- E2E when workflow, preview, or workspace behavior changes:
  - `python -m pytest tests/e2e/... -v`
- Full real-LLM E2E (manual trigger only):
  - `python -m pytest tests/e2e/test_full_game_creation_real_llm_playwright.py::test_full_game_creation_with_real_llm -v --tb=short -s`

For any test that touches generation paths:

- Stub `ImageService.generate_image(...)` when image output matters to the behavior under test.
- Or force `ImageService.is_available()` to be `False` when the test should exercise fallback behavior.
- Do not rely on local `.env` credentials or real external AI services during automated tests.

Do not claim a fix is complete without naming the tests run and their results.

## Historical Kimi Collaboration

Earlier phases used a design/execute split with external Kimi TDD prompts. Those completed prompts now live in `docs/archive/prompts/` and are historical evidence, not current implementation instructions.

If this workflow is reactivated:

1. Write a new current design and implementation plan.
2. Keep automated tests isolated from real model and image credentials.
3. Review every modified file and the complete diff.
4. Run targeted and relevant regression tests.
5. Trigger the real-LLM E2E only with explicit manual authorization.

## Preferred Workflow

1. Identify whether the change affects pipeline, assets, API, or UI.
2. Add or update tests first (TDD: RED → GREEN → REFACTOR).
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
- blueprint precondition consistency across stepwise upload APIs and tests
- mock build output paths remaining project-scoped and absolute-path safe
- preview servers are tracked by the shared `get_shared_preview_manager()` and stopped on FastAPI shutdown; tests must mock `PreviewManager.start` or stop previews explicitly
- frozen Dashboard path resolution in PyInstaller/Electron builds
- accidental use of real external AI credentials during tests
