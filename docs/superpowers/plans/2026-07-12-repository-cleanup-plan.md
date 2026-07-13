# Repository Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean the existing working tree, archive stale documentation, track the current desktop-packaging source, verify the remaining project, and create one final Git commit without losing local data or Git history.

**Architecture:** Use explicit, repository-contained path allowlists for every deletion and move. Keep runtime source and local user state separate: source and lock files are tracked, while secrets, workspaces, dependencies, caches, and build products stay local and ignored. Documentation is reduced to a small active surface with historical material preserved under `docs/archive/`.

**Tech Stack:** PowerShell, Git, Python 3.11, pytest, uv, React/Vite, Electron/TypeScript, npm/Vitest, Markdown.

---

**Commit policy:** The user explicitly requested one final commit. Do not commit individual tasks; complete all checks, review the staged diff, then create the single commit in Task 9.

### Task 1: Capture Safety Baseline

**Files:**
- Read: `.git/`, `.env`, `.venv/`, `workspace/`
- Read: `.gitignore`
- Read: `docs/superpowers/specs/2026-07-12-repository-cleanup-design.md`

- [ ] **Step 1: Confirm repository identity and history**

Run:

```powershell
git rev-parse --is-inside-work-tree
git rev-list --count HEAD
git status --short --branch
```

Expected: inside-work-tree is `true`, commit count is `118`, branch is `master`, and no file is staged.

- [ ] **Step 2: Confirm protected local paths exist before cleanup**

Run:

```powershell
@('.git', '.env', '.venv', 'workspace') | ForEach-Object {
    if (-not (Test-Path -LiteralPath $_)) { throw "Protected path missing before cleanup: $_" }
}
```

Expected: exit code 0 with no output.

- [ ] **Step 3: Record the pre-cleanup byte count**

Run a PowerShell size report for the exact deletion targets from Task 2 and save the numeric total in the execution notes, not in a generated repository file.

### Task 2: Delete Reproducible and Diagnostic Output

**Files:**
- Delete: `dashboard/node_modules/`
- Delete: `dashboard/dist/`
- Delete: `desktop/node_modules/`
- Delete: `desktop/dist/`
- Delete: `desktop/release/`
- Delete: `packaging/build/`
- Delete: `packaging/dist/`
- Delete: `.pytest_cache/`, `.ruff_cache/`, `.tmp-rembg-check/`, `.worktrees/`
- Delete: non-venv `__pycache__/`
- Delete: audited root debug, leak, UI-review, and log files

- [ ] **Step 1: Delete fixed directory targets with containment checks**

Use one PowerShell process end-to-end:

```powershell
$repo = [IO.Path]::GetFullPath((Get-Location).Path)
$targets = @(
    'dashboard/node_modules', 'dashboard/dist',
    'desktop/node_modules', 'desktop/dist', 'desktop/release',
    'packaging/build', 'packaging/dist',
    '.pytest_cache', '.ruff_cache', '.tmp-rembg-check', '.worktrees',
    'tests/integration/.tmp_sprite_test'
)
foreach ($relative in $targets) {
    $target = [IO.Path]::GetFullPath((Join-Path $repo $relative))
    if (-not $target.StartsWith($repo + [IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to delete outside repository: $target"
    }
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}
```

Expected: every removed path resolves below the repository root; `.env`, `.venv`, and `workspace/` are untouched.

- [ ] **Step 2: Delete non-venv Python caches with per-target containment checks**

```powershell
$repo = [IO.Path]::GetFullPath((Get-Location).Path)
Get-ChildItem -LiteralPath $repo -Recurse -Force -Directory -Filter '__pycache__' |
    Where-Object { $_.FullName -notlike "$repo\.venv\*" -and $_.FullName -notlike "$repo\.git\*" } |
    ForEach-Object {
        $target = [IO.Path]::GetFullPath($_.FullName)
        if (-not $target.StartsWith($repo + [IO.Path]::DirectorySeparatorChar)) {
            throw "Refusing to delete outside repository: $target"
        }
        Remove-Item -LiteralPath $target -Recurse -Force
    }
```

- [ ] **Step 3: Delete the audited fixed artifact files**

Delete only these names if present:

```text
debug_after_click.png
debug_beta_project.png
debug_beta_project2.html
debug_beta_project2.png
debug_leak.png
debug_nav.html
leak_a_after_build.png
leak_a_build.png
leak_b_after_switch.png
leak_b_switch.png
regression.log
scripts/download_sdk.log
scripts/download_web_support.log
ui-ai-dock-collapsed.png
ui-ai-dock-expanded.png
ui-current-workspace-222.png
ui-workflow-redesign-9-final.png
ui-workflow-redesign-9-target.png
```

Use the same `GetFullPath` and repository-prefix check as Step 1 before each `Remove-Item -LiteralPath` call.

- [ ] **Step 4: Reconfirm protected paths**

Repeat Task 1 Step 2. Expected: all four protected paths still exist.

### Task 3: Remove the Superseded UI Prototype and Archive Historical Documents

**Files:**
- Delete: `new_design/`
- Move: superseded root design documents to `docs/archive/`
- Move: completed and partial documents from active docs directories to `docs/archive/`
- Move: `docs/prompts/` to `docs/archive/prompts/`

- [ ] **Step 1: Delete `new_design/` with an exact absolute target check**

Resolve `new_design` from the current repository root, confirm it is an immediate child of that root, then delete it recursively. Do not use a wildcard.

- [ ] **Step 2: Move root historical documents**

Apply this exact mapping:

```text
backend-refactor-plan.md
  -> docs/archive/[SUPERSEDED]-2026-04-17-backend-refactor-plan.md
design-specification.md
  -> docs/archive/[SUPERSEDED]-2026-04-14-design-specification.md
plan-spec-mode.md
  -> docs/archive/[SUPERSEDED]-2026-04-16-spec-mode-plan.md
product-design-proposal.md
  -> docs/archive/[SUPERSEDED]-2026-04-14-product-design-proposal.md
user-workflow-analysis.md
  -> docs/archive/[SUPERSEDED]-2026-04-14-user-workflow-analysis.md
validation-milestones.md
  -> docs/archive/[COMPLETED]-2026-04-15-validation-milestones.md
```

- [ ] **Step 3: Move completed or superseded active documents**

Apply this exact mapping:

```text
docs/narrative-improvement-plan.md
  -> docs/archive/[COMPLETED]-2026-04-26-narrative-improvement-plan.md
docs/p1-remaining-issues.md
  -> docs/archive/[COMPLETED]-2026-04-26-p1-remaining-issues.md
docs/refinement-interview-redesign.md
  -> docs/archive/[COMPLETED]-2026-04-26-refinement-interview-redesign.md
docs/stepwise-generation-design.md
  -> docs/archive/[COMPLETED]-2026-04-27-stepwise-generation-design.md
docs/stepwise-generation-concrete-design.md
  -> docs/archive/[SUPERSEDED]-2026-04-26-stepwise-generation-concrete-design.md
docs/tier4-stepwise-generation-with-import-design.md
  -> docs/archive/[PARTIAL]-2026-04-27-tier4-stepwise-generation-with-import-design.md
docs/ui-redesign-analysis.md
  -> docs/archive/[COMPLETED]-2026-04-28-ui-redesign-analysis.md
docs/plans/2026-04-17-dashboard-backend-refactor-plan.md
  -> docs/archive/[COMPLETED]-2026-04-27-dashboard-backend-refactor-plan.md
docs/plans/2026-04-27-vn-authoring-upgrade-plan.md
  -> docs/archive/[PARTIAL]-2026-04-27-vn-authoring-upgrade-plan.md
docs/superpowers/plans/2026-04-27-character-asset-slot-derivation-plan.md
  -> docs/archive/[COMPLETED]-2026-04-27-character-asset-slot-derivation-plan.md
docs/superpowers/plans/2026-04-27-workflow-dashboard-redesign-plan.md
  -> docs/archive/[COMPLETED]-2026-04-28-workflow-dashboard-redesign-plan.md
docs/superpowers/plans/2026-04-29-electron-packaging-mvp.md
  -> docs/archive/[PARTIAL]-2026-04-29-electron-packaging-mvp.md
docs/superpowers/specs/2026-04-21-multi-chapter-style-consistency-design.md
  -> docs/archive/[COMPLETED]-2026-04-21-multi-chapter-style-consistency-design.md
docs/superpowers/specs/2026-04-22-staged-requirements-refinement-design.md
  -> docs/archive/[COMPLETED]-2026-04-22-staged-requirements-refinement-design.md
docs/superpowers/specs/2026-04-23-agent-led-refinement-intake-design.md
  -> docs/archive/[COMPLETED]-2026-04-26-agent-led-refinement-intake-design.md
docs/superpowers/specs/2026-04-27-character-asset-slot-derivation-design.md
  -> docs/archive/[COMPLETED]-2026-04-27-character-asset-slot-derivation-design.md
docs/superpowers/specs/2026-04-27-workflow-dashboard-redesign-design.md
  -> docs/archive/[COMPLETED]-2026-04-28-workflow-dashboard-redesign-design.md
```

For every move, validate source and destination resolve under the repository root and fail if the destination already exists.

- [ ] **Step 4: Archive execution prompts**

Move the complete `docs/prompts/` directory to `docs/archive/prompts/`. The source contains historical Kimi execution prompts; no active runtime imports it.

### Task 4: Repair Ignore and Release Metadata

**Files:**
- Modify: `.gitignore`
- Modify: `pyproject.toml`
- Modify: `dashboard/package.json`
- Modify: `dashboard/package-lock.json`
- Create: `.env.example`
- Create: `LICENSE`
- Track: `uv.lock`

- [ ] **Step 1: Update `.gitignore` with `apply_patch`**

Required policy:

```gitignore
/lib/
/lib64/
.env
.env.*
!.env.example
.claude/settings.local.json
.codex/
.npmrc
.pypirc
test-results/
playwright-report/
.cache/
```

Keep the existing Python, Node, build, workspace, debug, and packaging rules. Remove `uv.lock` from the ignore file and remove the obsolete `dashboard/src/lib` negation rules after narrowing `/lib/`.

- [ ] **Step 2: Create `.env.example` with placeholders only**

Create exactly documented, non-secret examples:

```dotenv
# Ren'Py SDK and local workspace
RENPY_SDK_PATH=
RENPY_MCP_WORKSPACE=
RENPY_MCP_PORT=8080

# Choose at least one chat provider
ANTHROPIC_API_KEY=
ANTHROPIC_BASE_URL=https://api.kimi.com/coding/
ANTHROPIC_MODEL=claude-3-5-sonnet
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=
RENPY_MCP_DEEPSEEK_API_KEY=
RENPY_MCP_QWEN_API_KEY=

# Optional image generation
RENPY_MCP_GEMINI_API_KEY=
RENPY_MCP_DASHSCOPE_IMAGE_MODEL=qwen-image-2.1
RENPY_MCP_DASHSCOPE_CHARACTER_IMAGE_MODEL=qwen-image-2.0

# Generate a unique value for non-development deployments
SESSION_SECRET=
```

- [ ] **Step 3: Add the standard MIT license**

Use the standard MIT license text with copyright line:

```text
Copyright (c) 2026 RenPy MCP contributors
```

- [ ] **Step 4: Validate lock-file tracking policy**

Run `git check-ignore -v uv.lock`; expected: no output and exit code 1. Run `uv lock --check` if `uv` is installed; expected: lock file is current.

- [ ] **Step 5: Align package metadata**

Keep Python, Dashboard, and Desktop at version `0.1.0`. Set the Dashboard package name to `renpy-mcp-creator-dashboard`, mark it private, use the MIT license, and update the corresponding lock-file root metadata. Update the Python project description to the local-first engineering/prototype positioning without changing dependency behavior.

### Task 5: Refresh the Active Documentation Surface

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/ROADMAP.md`
- Create: `docs/README.md`
- Modify: `docs/dual-agent-design.md` cross-references if needed

- [ ] **Step 1: Rewrite `README.md` around current facts**

The final README must contain these sections and claims:

```markdown
# RenPy MCP Creator

Experimental, local-first Ren'Py engineering and prototype-generation tool for Chinese creators.

## Current capabilities
project creation -> AI intake -> brief -> outline -> blueprint freeze -> multi-chapter scenes -> asset review -> script commit/rollback -> build/preview

## Maturity
Version 0.1.0; development preview; no stable installer release yet.

## Requirements
Python 3.11+, Windows 10/11, Node.js 20.19+ or 22.12+ for Dashboard/Desktop source builds.

## Setup
Use `uv sync --extra dev` or `python -m pip install -e ".[dev]"`, copy `.env.example` to `.env`, and configure at least one provider.

## Run
Document `vn-creator start`, `vn-creator doctor`, and source-mode backend/dashboard commands.

## Verification
List unit, integration, E2E, Dashboard, and Desktop commands without claiming all tests pass.

## Documentation
Link `docs/README.md`, `docs/ROADMAP.md`, product-direction analysis, and future dual-agent design.

## License
MIT; link `LICENSE`.
```

- [ ] **Step 2: Rewrite `docs/ROADMAP.md` with the current date**

Required order:

1. Current operational pipeline and historical real-LLM E2E evidence.
2. Current local verification results, including four known integration failures unless the fresh run differs.
3. Active priority: release hygiene and real-user validation.
4. Next engineering priorities: fix test/lifecycle issues, define minimal GameIR, asset manifest, generated/user ownership.
5. Explicitly deferred: dual-agent audit, more model providers, broad UI redesign.
6. Links to active and archived documentation.

- [ ] **Step 3: Update `AGENTS.md`**

Keep all safety guardrails. Replace stale phase wording with the current priority order, update the repository map to include `desktop/`, `packaging/`, `docs/README.md`, and `docs/archive/`, and remove claims that all current tests pass.

- [ ] **Step 4: Align `CHANGELOG.md` with version `0.1.0`**

Rename the untagged `0.2.0` heading to `Unreleased`, retain its historical feature list, and add a 2026-07-12 repository-cleanup subsection covering documentation, lock files, desktop packaging source, and removal of obsolete prototypes/build products.

- [ ] **Step 5: Create `docs/README.md`**

Document active files, future designs, archived status prefixes, and the rule that only `docs/ROADMAP.md` is authoritative for current status.

- [ ] **Step 6: Repair local Markdown links**

Search every tracked Markdown file for links and plain-path references to moved files. Update active documents to their new archive paths or remove stale references. Historical archive documents may retain prose references, but clickable relative links must resolve.

### Task 6: Verify Existing Desktop-Packaging Source

**Files:**
- Track: `desktop/`
- Track: `packaging/pyinstaller/`
- Track: `packaging/scripts/`
- Modify already present: `src/renpy_mcp/web/fastapi_app.py`
- Track: `tests/unit/web/test_dashboard_path_resolution.py`

- [ ] **Step 1: Inspect the exact untracked source set**

Run `git status --short` and confirm generated `node_modules`, `dist`, `release`, `build`, and `.env` paths do not appear as commit candidates.

- [ ] **Step 2: Run the frozen-dashboard-path unit test**

```powershell
python -m pytest tests/unit/web/test_dashboard_path_resolution.py -q
```

Expected: 1 passed.

- [ ] **Step 3: Reinstall and verify Desktop from its lock file**

```powershell
Push-Location desktop
npm ci
npm test
npm run build
Pop-Location
```

Expected: 6 Desktop tests pass and TypeScript compilation exits 0.

- [ ] **Step 4: Reinstall and verify Dashboard from its lock file**

```powershell
Push-Location dashboard
npm ci
npm run build
npx vitest run
Pop-Location
```

Expected: Vite build exits 0 and all tracked Dashboard tests pass.

### Task 7: Run Backend Regression Verification

**Files:**
- Test: `tests/unit/`
- Test: `tests/integration/`

- [ ] **Step 1: Run unit tests**

```powershell
python -m pytest tests/unit -q --disable-warnings
```

Expected baseline: 461 passed, 1 skipped. If counts differ, record the actual result and update `docs/ROADMAP.md`.

- [ ] **Step 2: Run integration tests**

```powershell
python -m pytest tests/integration -q --disable-warnings
```

Expected baseline: 413 passed and 4 known failures. Do not fix unrelated integration behavior in this cleanup. Record exact failures in `docs/ROADMAP.md`.

- [ ] **Step 3: Clean any preview subprocess left by the integration suite**

Inspect `python.exe` processes whose command line contains both `http.server` and `pytest-of-`. Stop only those exact test-owned processes and report their PIDs.

### Task 8: Restore the Clean Physical Tree After Verification

**Files:**
- Delete again: `dashboard/node_modules/`, `dashboard/dist/`, `desktop/node_modules/`, `desktop/dist/`
- Delete again: newly created non-venv caches and test output

- [ ] **Step 1: Repeat the contained deletion logic from Task 2**

Remove only regenerated dependency/build/cache paths. Preserve lock files and all source.

- [ ] **Step 2: Measure reclaimed space and validate protected data**

Confirm at least 1 GiB was removed relative to Task 1. Re-run protected-path checks for `.git`, `.env`, `.venv`, and `workspace/`.

- [ ] **Step 3: Validate active documentation links**

Run the repository-local Markdown link checker implemented as a bounded PowerShell scan of relative Markdown links. Expected: no missing local targets in active documents.

### Task 9: Stage by Allowlist, Inspect, and Commit

**Files:**
- Stage: all deliberate tracked deletions/moves
- Stage: updated source, documentation, lock files, metadata, Desktop, packaging, and tests
- Exclude: all protected and generated paths

- [ ] **Step 1: Stage with explicit top-level allowlists**

```powershell
git add -- .gitignore .env.example LICENSE README.md AGENTS.md CHANGELOG.md uv.lock
git add -- docs
git add -- desktop/electron-builder.yml desktop/package.json desktop/package-lock.json desktop/tsconfig.json desktop/vitest.config.ts desktop/src
git add -- packaging/pyinstaller packaging/scripts
git add -- src/renpy_mcp/web/fastapi_app.py tests/unit/web/test_dashboard_path_resolution.py
git add -u -- new_design backend-refactor-plan.md design-specification.md plan-spec-mode.md product-design-proposal.md user-workflow-analysis.md validation-milestones.md
```

- [ ] **Step 2: Reject forbidden staged paths**

Run:

```powershell
git diff --cached --name-only |
    Select-String '(^|/)(\.env$|\.venv|workspace|node_modules|dist|build|release)(/|$)|^(\.claude|\.codex)/|^ui-.*\.png$'
```

Expected: no output. Also run `git diff --cached --check`; expected: exit 0.

- [ ] **Step 3: Scan staged text for secrets and absolute local paths**

Search staged content for high-confidence API-key prefixes, the current repository root returned by Git, user-profile path patterns, and actual values from `.env` without printing the secret values. Expected: zero real local-path or secret matches; synthetic test fixtures such as `C:/Users/Test` are allowed.

- [ ] **Step 4: Review staged scope**

Run `git diff --cached --stat`, `git diff --cached --name-status`, and review the complete staged diff for `.gitignore`, metadata, active documentation, packaging source, and the frozen-path implementation.

- [ ] **Step 5: Create the single final commit**

```powershell
git commit -m "chore: clean repository and refresh project status"
```

Expected: commit succeeds on `master`.

- [ ] **Step 6: Verify post-commit state**

Run:

```powershell
git status --short --branch
git log -1 --stat --oneline
```

Expected: tracked working tree is clean; only deliberately preserved ignored local state remains. Report the commit hash, reclaimed disk space, verification results, known integration failures, and confirm no push or tag was created.
