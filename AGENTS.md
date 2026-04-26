# AGENTS.md

This file is for AI coding agents working in this repository.

## Scope

- This file applies to AI coding agents only.
- Optimize for small, verifiable changes.
- Do not expand work into a later phase unless the user explicitly asks for it.

## Current Product State

- The core pipeline is **operational**: create project → AI intake → brief confirmation → outline confirmation → blueprint freeze → scene generation → asset generation → build → preview. Verified by full real-LLM E2E (14/14 stages, ~132s).
- The active product loop is:
  - confirmed blueprint
  - prototype scene generation (multi-chapter, with position-aware chapter outline derivation)
  - background / sprite / font asset generation
  - script writeback
  - build / preview
- **Completed (Phase 6–7)**: multi-chapter generation, staged requirements refinement (brief/outline/freeze), narrative completeness improvements, E2E diagnostic harness (27/27 tests pass).
- **In progress**: P1 issue fixes (silent exception swallows, sync I/O, duplicate code, Windows compatibility).
- **Future (Phase 8+)**: dual-agent audit (Creator/Auditor quality gate), adaptive refinement interview, stepwise generation, dashboard UI redesign.
- The authoritative status document is:
  - [`docs/ROADMAP.md`](docs/ROADMAP.md)
- Key design specs:
  - [`docs/dual-agent-design.md`](docs/dual-agent-design.md)
  - [`docs/refinement-interview-redesign.md`](docs/refinement-interview-redesign.md)
  - [`docs/stepwise-generation-design.md`](docs/stepwise-generation-design.md)

## Repo Map

- `src/renpy_mcp/`: Python backend, services, chat orchestration, FastAPI, asset pipeline
- `dashboard/`: React frontend
- `tests/`: unit, integration, and E2E coverage
- `workspace/`: local generated projects and debug artifacts
- `docs/`: plans, design specs, ROADMAP.md (authoritative status)
  - `docs/archive/`: completed or superseded plans
  - `docs/prompts/`: Kimi execution prompts (TDD format)
  - `docs/superpowers/specs/`: detailed design specifications

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

## Kimi Collaboration

This project uses a design/execute split:

- **Claude/DeepSeek** (this agent): design, planning, code review, E2E verification
- **Kimi** (external agent): code execution following TDD prompts

Kimi execution prompts live in `docs/prompts/kimi-*.md`. Each prompt is self-contained with:
- Exact file paths and line numbers
- Complete test code (RED phase)
- Minimal implementation code (GREEN phase)
- Verification commands per step
- FAQ section for anticipated obstacles
- Structured report template

After Kimi executes a prompt, Claude/DeepSeek reviews the result:
1. Read all modified files
2. Verify `git diff` matches the intended changes
3. Run the full test suite
4. Run the real-LLM E2E test
5. Provide a structured review (pass/fail/needs-fix)

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
- accidental use of real external AI credentials during tests
