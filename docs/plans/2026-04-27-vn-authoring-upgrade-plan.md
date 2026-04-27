# Prototype Game Shell Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strengthen the current prototype generation pipeline by adding a prototype-first Game Shell layer: AI generates the playable prototype first, the system derives editable shell/gallery/ending/credits configuration from that prototype, and the user refines presentation before web or Windows build.

**Architecture:** Keep the existing prototype pipeline as the primary path. Add a deterministic `GameShellConfig` and `GameShellRenderService` that derive shell content from committed or staged prototype outputs and generate additive Ren'Py files. Users edit the derived draft after the AI prototype exists; they do not need to define the full VN structure before generation. Branching, deep Story Planner editing, route variables, and full CG/ending authoring remain later phases and must not block this Game Shell upgrade.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, Ren'Py screen language, Ren'Py Gallery/Persistent APIs, React + Vite + TypeScript, existing `ProjectManager`, `StepwiseGenerationService`, `ScriptRenderService`, and Dashboard workspace.

---

## Scope Correction

This plan supersedes the earlier broad "VN authoring system" ordering. The current priority is not a full branching authoring tool. The current priority is:

1. Make generated prototypes feel more like complete Ren'Py games.
2. Automatically derive shell/gallery/ending/credits drafts from the generated prototype.
3. Let users refine the derived presentation layer after generation.
4. Add stable main menu / save-load / settings / extras / gallery surfaces.
5. Keep the existing linear prototype generation path working.
6. Add Windows build/export support alongside the existing web target.
7. Defer complex branch editing, route flags, final CG logic, and deep Story Planner UX.

The implementation must preserve the existing verified product loop:

```text
confirmed blueprint
  -> prototype scene generation
  -> background / sprite / font asset generation
  -> script writeback
  -> build / preview
```

The Game Shell should enhance this loop, not replace it.

---

## Source References

Use these references when implementing the plan:

- Ren'Py official docs:
  - Special screens: main menu, game menu, navigation, save, load, preferences.
  - Screen language.
  - Gallery and replay rooms.
  - Persistent data.
  - Voice and audio statements if later extended.
- Ren'Py default project template:
  - `screens.rpy`
  - `gui.rpy`
  - `options.rpy`
- Monogatari/RenJS:
  - Treat as UX references for VN feature packaging only.
- Existing project docs:
  - `docs/ROADMAP.md`
  - `docs/stepwise-generation-design.md`
  - `docs/tier4-stepwise-generation-with-import-design.md`
  - `docs/narrative-improvement-plan.md`
  - `docs/ui-redesign-analysis.md`

---

## Current Gaps This Plan Addresses

1. Generated prototypes currently focus on script/asset output and do not expose a stronger game-facing shell.
2. Users do not have a clear project-scoped place to refine the generated prototype's title screen, subtitle, theme, extras menu, gallery, ending gallery, or credits.
3. Gallery and ending gallery can be useful even before full branching exists:
   - Gallery can show generated backgrounds, accepted sprites, and later CGs.
   - Ending Gallery can initially show completed prototype/chapter endings and later support route endings.
4. The Dashboard needs a simple "Prototype Presentation" surface before deeper authoring features.
5. System UI should be deterministic. It should not rely on LLM-generated `screens.rpy`.
6. Build currently targets web; users need an explicit Windows package target using the configured Ren'Py SDK.

---

## Non-Goals For This Phase

Do not implement these in the first Game Shell phase:

- Full Story Planner.
- React Flow branch graph editor.
- Choice variables / affection / route flags.
- Branch reachability validator.
- Multi-ending condition evaluator.
- Full CG event authoring.
- LLM-driven screen code generation.
- Replacing user-authored Ren'Py UI files wholesale.

These features are retained in "Later Phases" at the end of this document.

---

## Target User Workflow

```text
Project Brief / Outline / Blueprint confirmed
  -> User runs prototype generation as today
  -> Character/background assets and scripts are staged/committed as today
  -> Backend derives a Game Shell draft from prototype metadata and accepted assets
  -> User opens Game Shell tab and edits title, subtitle, theme, gallery, endings, credits
  -> Backend renders additive shell files into staging or final commit
  -> User builds Web Preview or Windows Package
  -> Build opens with a polished title screen and extras surfaces
```

The user should not need to understand Ren'Py screen language to get a usable main menu and extras menu.
The user should also not need to define shell/gallery data before the AI prototype exists; the first usable draft is derived from real generated content.

---

## Design Principles

- **Prototype-first:** Every task must improve the current generated prototype experience.
- **AI-first, edit-second:** AI creates the prototype structure first. User editing refines that generated structure instead of blocking generation.
- **Derived draft:** Default shell/gallery/ending/credits content must be computed from project metadata, prototype scene packages, accepted assets, and current build state.
- **Deterministic shell:** Generate screen files from templates, not LLM free-form code.
- **Additive files:** Prefer generated files such as `zz_generated_shell.rpy` and `zz_generated_gallery.rpy` instead of overwriting `screens.rpy`.
- **Rollback-safe:** Game Shell files must commit and rollback with prototype scripts.
- **Project-relative metadata:** Persist logical ids and project-relative paths only.
- **Ren'Py defaults first:** Use Ren'Py's built-in save/load/preferences screens unless a small additive override is required.
- **Graceful no-assets mode:** Gallery/ending screens should render even if no CG assets exist yet.
- **Backward compatible:** Projects without `game_shell.json` should keep current behavior.
- **Export target clarity:** Web preview and Windows package are separate build targets with explicit status and artifacts.

---

## Proposed File Map

### Backend Models

- Modify: `src/renpy_mcp/blueprint/models.py`
  - Add `GameShellConfig`.
  - Add `GameShellGalleryItem`.
  - Add `GameShellEndingItem`.
  - Add `GameShellRenderPreview`.

### Backend Persistence

- Modify: `src/renpy_mcp/services/project_manager.py`
  - Add `read_game_shell(project_name)`.
  - Add `write_game_shell(project_name, config)`.
  - Persist to `meta/game_shell.json`.

### Backend Services

- Create: `src/renpy_mcp/services/game_shell_render_service.py`
  - Render additive Ren'Py shell files to staging.
  - Build gallery entries from accepted/generated project assets.
  - Build ending entries from prototype/chapter metadata.
  - Derive a default `GameShellConfig` when `meta/game_shell.json` is missing or stale.

- Modify: `src/renpy_mcp/services/stepwise_generation_service.py`
  - Stage shell files during script preview.
  - Commit shell files with prototype scripts.
  - Roll back shell files if any commit step fails.

- Modify: `src/renpy_mcp/services/prototype_activation_service.py` only if existing commit/rollback helpers need to be reused for shell files.

- Modify: `src/renpy_mcp/services/build_manager.py`
  - Add `target="windows"` support using the configured local Ren'Py SDK.
  - Keep `target="web"` behavior unchanged.
  - Persist target-specific build status and artifact path.

### Backend APIs

- Create: `src/renpy_mcp/web/routers/game_shell.py`
  - `GET /api/projects/{project_name}/game-shell`
  - `PUT /api/projects/{project_name}/game-shell`
  - `POST /api/projects/{project_name}/game-shell/render-preview`
  - `POST /api/projects/{project_name}/game-shell/reset-defaults`
  - `POST /api/projects/{project_name}/game-shell/derive`

- Modify: current FastAPI router registration site
  - Register the new router.

- Modify: existing build routes
  - Accept `target: "web" | "windows"`.
  - Return target-specific output metadata without leaking absolute paths in API payloads beyond existing build-status behavior.

### Frontend

- Modify: `dashboard/src/context/ProjectContext.tsx`
  - Add `GameShellConfig` types and load/save/render methods.

- Create: `dashboard/src/components/workspace/GameShellWorkspaceView.tsx`
  - Prototype shell editor.

- Modify: `dashboard/src/components/workspace/WorkspaceTabs.tsx`
  - Add `shell` tab, label "Prototype Shell" or "Game Shell".

- Modify: `dashboard/src/pages/ProjectWorkspacePage.tsx`
  - Load and render the new shell tab.

- Modify: build controls
  - Expose separate actions for Web Preview and Windows Package.
  - Show clear status for the selected target.

### Tests

- Create: `tests/unit/test_game_shell_render_service.py`
- Create: `tests/integration/test_game_shell_routes.py`
- Extend: `tests/integration/test_stepwise_generation.py`
- Extend: `tests/unit/test_build_manager.py` or equivalent build-manager coverage for Windows target command selection.
- Create: `dashboard/src/components/workspace/GameShellWorkspaceView.test.tsx`

---

## Data Model Proposal

Add these models to `src/renpy_mcp/blueprint/models.py`.

```python
class GameShellGalleryItem(BaseModel):
    id: str
    title: str
    image_path: str = ""
    source: Literal["background", "sprite", "cg", "placeholder"] = "placeholder"
    unlock_mode: Literal["always", "persistent"] = "always"
    persistent_key: str = ""


class GameShellEndingItem(BaseModel):
    id: str
    title: str
    description: str = ""
    unlock_mode: Literal["always", "persistent"] = "always"
    persistent_key: str = ""


class GameShellConfig(BaseModel):
    title: str = ""
    subtitle: str = ""
    theme: Literal["default", "dark", "light", "dramatic"] = "default"
    main_menu_background: str = ""
    show_gallery: bool = True
    show_endings: bool = True
    show_replay: bool = False
    show_credits: bool = True
    gallery_items: list[GameShellGalleryItem] = Field(default_factory=list)
    ending_items: list[GameShellEndingItem] = Field(default_factory=list)
    credits: list[str] = Field(default_factory=list)
    updated_at: str = ""


class GameShellRenderPreview(BaseModel):
    script_files: list[str] = Field(default_factory=list)
    preview: str = ""
    gallery_count: int = 0
    ending_count: int = 0
```

Notes:

- `main_menu_background` must be a project-relative path or logical asset id.
- `image_path` must be project-relative.
- `unlock_mode="always"` is the v1 default because full route/CG unlock logic is deferred.
- Persistent unlock keys are included now so later CG/ending systems can reuse the same model without breaking data.

---

## Generated Ren'Py File Strategy

Generate additive files:

```text
game/zz_generated_shell.rpy
game/zz_generated_gallery.rpy
```

Stage them first:

```text
game/__staging__/<round_id>/zz_generated_shell.rpy
game/__staging__/<round_id>/zz_generated_gallery.rpy
```

Do not replace:

```text
game/screens.rpy
game/gui.rpy
game/options.rpy
```

The generated files should:

- Add stable screens where possible.
- Add navigation entries for Gallery / Endings / Credits where possible.
- Provide callable screens if direct navigation override is too risky.
- Be valid when gallery or ending lists are empty.
- Contain comments marking them as managed generated files.

Managed header:

```renpy
# AUTO-GENERATED BY RenPy MCP Creator.
# Do not edit this file directly. Configure it from Dashboard Prototype Shell.
```

---

## Task 1: Game Shell Models and Persistence

**Files:**

- Modify: `src/renpy_mcp/blueprint/models.py`
- Modify: `src/renpy_mcp/services/project_manager.py`
- Test: `tests/unit/test_game_shell_render_service.py`

- [ ] Add `GameShellGalleryItem`, `GameShellEndingItem`, `GameShellConfig`, and `GameShellRenderPreview` to `models.py`.

- [ ] Add `ProjectManager.read_game_shell(project_name)`.

Behavior:

```text
Return GameShellConfig if meta/game_shell.json exists.
Return None if file does not exist.
Raise ValueError if JSON exists but is invalid.
```

- [ ] Add `ProjectManager.write_game_shell(project_name, config)`.

Behavior:

```text
Persist to meta/game_shell.json.
Use model_dump(mode="json").
Do not store absolute paths.
Update updated_at when route/service calls save.
```

- [ ] Add tests:

```text
test_game_shell_defaults_are_valid
test_game_shell_round_trip_persists_json
test_game_shell_rejects_invalid_json
test_game_shell_metadata_does_not_need_absolute_paths
```

- [ ] Run:

```bash
python -m pytest tests/unit/test_game_shell_render_service.py -x -q
```

Expected: all tests pass.

---

## Task 2: Game Shell Render Service

**Files:**

- Create: `src/renpy_mcp/services/game_shell_render_service.py`
- Test: `tests/unit/test_game_shell_render_service.py`

- [ ] Implement `GameShellRenderService`.

Suggested constructor:

```python
class GameShellRenderService:
    def __init__(self, pm: ProjectManager) -> None:
        self.pm = pm
```

- [ ] Implement:

```python
def default_config_for_project(self, project_name: str) -> GameShellConfig:
    ...
```

Rules:

```text
title comes from blueprint.title when available.
subtitle can be empty.
credits contains "Created with RenPy MCP Creator" by default.
gallery and ending screens are enabled by default.
```

- [ ] Implement:

```python
def render_shell_files(
    self,
    project_name: str,
    config: GameShellConfig,
    round_id: str,
) -> GameShellRenderPreview:
    ...
```

Output:

```text
game/__staging__/<round_id>/zz_generated_shell.rpy
game/__staging__/<round_id>/zz_generated_gallery.rpy
```

- [ ] Render `zz_generated_shell.rpy`.

Minimum content:

```renpy
screen mcp_creator_about():
    tag menu
    use game_menu(_("About"), scroll="viewport"):
        vbox:
            text "Title"
            text "Subtitle"
            text "Created with RenPy MCP Creator"
```

- [ ] Render `zz_generated_gallery.rpy`.

Minimum content:

```renpy
screen mcp_creator_gallery():
    tag menu
    use game_menu(_("Gallery"), scroll="viewport"):
        vbox:
            text "Gallery"
            text "No gallery items yet."

screen mcp_creator_endings():
    tag menu
    use game_menu(_("Endings"), scroll="viewport"):
        vbox:
            text "Endings"
            text "No endings unlocked yet."
```

- [ ] Include entries when configured:

```renpy
imagebutton:
    idle "images/background/example.png"
    action NullAction()

text "Prototype Complete"
```

- [ ] Escape user text safely for Ren'Py strings.

- [ ] Add tests:

```text
test_default_config_uses_blueprint_title
test_render_shell_files_writes_staging_files
test_render_shell_preview_lists_project_relative_files
test_render_gallery_empty_state_is_valid
test_render_gallery_items_include_project_relative_paths
test_render_endings_empty_state_is_valid
test_render_escapes_quotes_in_title_and_credits
```

- [ ] Run:

```bash
python -m pytest tests/unit/test_game_shell_render_service.py -x -q
```

Expected: all tests pass.

---

## Task 3: Game Shell API

**Files:**

- Create: `src/renpy_mcp/web/routers/game_shell.py`
- Modify: FastAPI router registration site
- Test: `tests/integration/test_game_shell_routes.py`

- [ ] Add `GET /api/projects/{project_name}/game-shell`.

Behavior:

```text
If meta/game_shell.json exists, return it.
If not, return default config from GameShellRenderService.
404 only when project does not exist.
```

- [ ] Add `PUT /api/projects/{project_name}/game-shell`.

Behavior:

```text
Validate body as GameShellConfig.
Reject absolute paths in main_menu_background and gallery image_path.
Persist config.
Return saved config.
```

- [ ] Add `POST /api/projects/{project_name}/game-shell/reset-defaults`.

Behavior:

```text
Overwrite meta/game_shell.json with default config.
Return default config.
```

- [ ] Add `POST /api/projects/{project_name}/game-shell/render-preview`.

Behavior:

```text
Render shell files to staging using current round id or a shell-preview round id.
Return GameShellRenderPreview.
Do not commit files.
```

- [ ] Add integration tests:

```text
test_get_game_shell_returns_default_for_existing_project
test_put_game_shell_persists_config
test_put_game_shell_rejects_absolute_main_menu_background
test_put_game_shell_rejects_absolute_gallery_image_path
test_reset_defaults_restores_blueprint_title
test_render_preview_writes_only_staging_files
```

- [ ] Run:

```bash
python -m pytest tests/integration/test_game_shell_routes.py -x -q
```

Expected: all tests pass.

---

## Task 4: Dashboard Prototype Shell Editor

**Files:**

- Modify: `dashboard/src/context/ProjectContext.tsx`
- Create: `dashboard/src/components/workspace/GameShellWorkspaceView.tsx`
- Modify: `dashboard/src/components/workspace/WorkspaceTabs.tsx`
- Modify: `dashboard/src/pages/ProjectWorkspacePage.tsx`
- Test: `dashboard/src/components/workspace/GameShellWorkspaceView.test.tsx`

- [ ] Add TypeScript interfaces:

```ts
export interface GameShellGalleryItem {
  id: string;
  title: string;
  image_path: string;
  source: "background" | "sprite" | "cg" | "placeholder";
  unlock_mode: "always" | "persistent";
  persistent_key: string;
}

export interface GameShellEndingItem {
  id: string;
  title: string;
  description: string;
  unlock_mode: "always" | "persistent";
  persistent_key: string;
}

export interface GameShellConfig {
  title: string;
  subtitle: string;
  theme: "default" | "dark" | "light" | "dramatic";
  main_menu_background: string;
  show_gallery: boolean;
  show_endings: boolean;
  show_replay: boolean;
  show_credits: boolean;
  gallery_items: GameShellGalleryItem[];
  ending_items: GameShellEndingItem[];
  credits: string[];
  updated_at: string;
}
```

- [ ] Add context methods:

```text
loadGameShell(name)
saveGameShell(name, config)
resetGameShellDefaults(name)
renderGameShellPreview(name)
```

- [ ] Add a `shell` tab to `WorkspaceTabs`.

Recommended label:

```text
Prototype Shell
```

- [ ] Build `GameShellWorkspaceView`.

Minimum UI:

```text
Title input
Subtitle input
Theme segmented control or select
Main menu background project-relative path input
Toggles: Gallery, Ending Gallery, Replay, Credits
Gallery item list: id, title, image path, source
Ending item list: id, title, description
Credits list editor
Save button
Reset defaults button
Render preview button
Preview script files list
```

- [ ] Keep UI copy focused on actions and state.

Do not explain Ren'Py internals in the app. Use labels like:

```text
Title Screen
Extras
Gallery
Endings
Credits
```

- [ ] Add tests:

```text
renders_default_shell_config
updates_title_and_subtitle
toggles_gallery_and_saves
adds_gallery_item
adds_ending_item
reset_defaults_calls_api
render_preview_shows_script_file_list
```

- [ ] Run:

```bash
cd dashboard
npm run build
```

Expected: TypeScript and Vite build pass.

---

## Task 5: Integrate Game Shell With Stepwise Script Preview

**Files:**

- Modify: `src/renpy_mcp/services/stepwise_generation_service.py`
- Modify: `src/renpy_mcp/services/script_render_service.py` only if preview payload needs script file aggregation
- Test: `tests/integration/test_stepwise_generation.py`

- [ ] During `script/preview`, render Game Shell staging files when either condition is true:

```text
meta/game_shell.json exists
or default shell rendering is enabled by config flag
```

The simplest v1 behavior should be:

```text
Always render default Game Shell files during preview unless explicitly disabled later.
```

- [ ] Include shell files in preview response.

Current preview returns script content and script file list. Extend it so shell files are visible in `script_files`.

- [ ] Do not require Story Plan.

Game Shell must work with the current scene package / prototype path.

- [ ] Add tests:

```text
test_script_preview_includes_generated_shell_files
test_script_preview_uses_default_shell_without_saved_config
test_script_preview_uses_saved_game_shell_config
test_script_preview_does_not_require_story_plan
```

- [ ] Run:

```bash
python -m pytest tests/integration/test_stepwise_generation.py -x -q
```

Expected: all tests pass.

---

## Task 6: Commit and Rollback Shell Files With Prototype

**Files:**

- Modify: `src/renpy_mcp/services/stepwise_generation_service.py`
- Modify: `src/renpy_mcp/services/prototype_activation_service.py` if helper reuse is needed
- Test: `tests/integration/test_stepwise_generation.py`

- [ ] During `script/commit`, promote staged shell files:

```text
game/__staging__/<round_id>/zz_generated_shell.rpy -> game/zz_generated_shell.rpy
game/__staging__/<round_id>/zz_generated_gallery.rpy -> game/zz_generated_gallery.rpy
```

- [ ] Rollback requirements:

```text
If script commit fails, shell files must not remain partially promoted.
If shell commit fails, script files must roll back to their previous state.
If rollback fails, log warning with enough file context.
Never delete unrelated user-authored files.
```

- [ ] Preserve previous generated shell files.

Before promotion, backup:

```text
game/zz_generated_shell.rpy
game/zz_generated_gallery.rpy
```

Restore backups on failure.

- [ ] Add tests:

```text
test_commit_promotes_shell_files
test_commit_restores_previous_shell_files_on_failure
test_commit_removes_new_shell_files_on_failure_when_no_previous_files
test_commit_without_shell_staging_keeps_existing_behavior
```

- [ ] Run:

```bash
python -m pytest tests/integration/test_stepwise_generation.py -x -q
```

Expected: all tests pass.

---

## Task 7: Build and Preview Regression

**Files:**

- Extend existing E2E tests under `tests/e2e/`
- Extend frontend tests if build/preview UI changes

- [ ] Add a non-real E2E test that uses stubs only.

Scenario:

```text
create project
complete brief/outline/freeze path using existing test helpers
configure Prototype Shell title/subtitle/gallery/endings
run prototype generation with stubbed image service
preview script
commit
build
assert generated shell files exist
assert generated shell files are listed in preview/commit response
assert build status is previewable
assert no external LLM/image calls are made beyond existing stubs
```

- [ ] Add script content assertions:

```text
zz_generated_shell.rpy contains screen mcp_creator_about
zz_generated_gallery.rpy contains screen mcp_creator_gallery
zz_generated_gallery.rpy contains screen mcp_creator_endings
```

- [ ] Run targeted E2E:

```bash
python -m pytest tests/e2e/... -v
```

Expected: relevant E2E passes with stubbed external services.

Do not run the real-LLM E2E by default.

---

## Later Phase A: Lightweight Scene/Chapter Editing

This is intentionally after Game Shell.

Goal:

```text
Allow users to edit generated chapters/scenes enough to improve prototypes without building a full branch authoring system.
```

Possible tasks:

- Extend `ChapterOutlineWorkspaceView` to expose scene count and desired scene beats.
- Add a simple scene package editor for title, summary, location, mood, characters, and dialogue beat target.
- Persist user-edited scene package fields.
- Ensure AI generation fills empty fields but does not overwrite user-edited fields.

Deferred from first phase:

- Field-level locks across all authoring models.
- React Flow.
- Route graph editor.

---

## Later Phase B: Branching and Choices

Goal:

```text
Add first-class choices only after linear prototypes have a stronger game shell.
```

Recommended minimal model:

```text
ChoicePoint
ChoiceOption
NarrativeVariable
```

Recommended order:

1. Model and persistence.
2. Validation service.
3. Render `menu:` blocks.
4. Story Map branch edge display.
5. Dashboard editor.

Do not introduce this into the first Game Shell PR.

---

## Later Phase C: CG and Ending Authoring

Goal:

```text
Upgrade Gallery/Ending Gallery from shell surfaces into gameplay-aware unlock systems.
```

Recommended additions:

```text
CGEvent
EndingDefinition
persistent unlock statements
final CG association
ending condition validation
```

Use the `GameShellGalleryItem` and `GameShellEndingItem` model fields as the compatibility bridge.

---

## Rollout Strategy

### Phase 1: Game Shell Foundation

Implement Tasks 1-3.

Outcome:

- Game Shell config exists.
- Renderer can produce valid staging files.
- API can save/reset/preview shell config.
- Existing prototype generation remains unchanged.

### Phase 2: Dashboard and Preview

Implement Tasks 4-5.

Outcome:

- Users can configure the prototype shell in Dashboard.
- Script preview includes generated shell files.
- No Story Plan dependency.

### Phase 3: Commit/Build Hardening

Implement Tasks 6-7.

Outcome:

- Shell files commit/rollback with prototype scripts.
- Build/preview regression proves the generated game has shell surfaces.

### Later

Implement Later Phase A, B, and C only after shell-enhanced prototypes are stable.

---

## Risk Register

| Risk | Mitigation |
|------|------------|
| Generated shell breaks Ren'Py build | Keep generated files additive and minimal; add build/E2E regression |
| Existing prototype commit becomes unsafe | Promote shell files in the same staged commit/rollback path |
| User-authored UI files are overwritten | Do not replace `screens.rpy`, `gui.rpy`, or `options.rpy` |
| Gallery has no real CG assets yet | Render empty state and optionally include generated backgrounds as gallery items |
| Ending Gallery is premature without branching | Use always-visible prototype/chapter endings first; reserve persistent keys for later |
| More Dashboard tabs confuse users | Label the tab as Prototype Shell and keep controls focused on presentation |
| Absolute paths leak through config | Reject absolute paths in API and tests |
| LLM generates unstable screen code | Do not use LLM for Game Shell rendering |

---

## Verification Commands

Run targeted backend tests:

```bash
python -m pytest tests/unit/test_game_shell_render_service.py -x -q
python -m pytest tests/integration/test_game_shell_routes.py -x -q
python -m pytest tests/integration/test_stepwise_generation.py -x -q
```

Run frontend build:

```bash
cd dashboard
npm run build
```

Run E2E only for workflow-level changes:

```bash
python -m pytest tests/e2e/... -v
```

Do not run the real-LLM E2E by default. Only run it when explicitly requested:

```bash
python -m pytest tests/e2e/test_full_game_creation_real_llm_playwright.py::test_full_game_creation_with_real_llm -v --tb=short -s
```

---

## Recommended First PR

Keep the first PR focused:

```text
Task 1 + Task 2 + Task 3 only
```

Reason:

- It delivers the Game Shell foundation without touching script commit behavior.
- Existing generation/build/preview should remain unchanged.
- It gives frontend and commit integration a stable contract.

Suggested commit sequence:

```text
feat: add game shell config persistence
feat: render generated Ren'Py shell files
feat: expose game shell configuration API
```

---

## Self-Review

- The plan now fronts Game Shell work instead of Story Plan/branching work.
- The first implementation phase strengthens current prototype generation without requiring full authoring-system changes.
- Homepage, save/load, settings, Gallery, Ending Gallery, credits, and extras are treated as deterministic shell features.
- Branching, route variables, full CG events, final CG logic, and deep Story Planner UX are explicitly deferred.
- Existing staged generation and rollback constraints remain required.
- Automated tests remain stubbed and must not call real LLM or image services by default.
