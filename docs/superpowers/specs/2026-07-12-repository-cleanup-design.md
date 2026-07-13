# Repository Cleanup Design

**Date:** 2026-07-12
**Status:** Approved for implementation
**Scope:** Repository structure, generated artifacts, documentation, release metadata, and one final Git commit

## Goal

Turn the current working directory into a clean, reproducible development repository without losing user data, secrets, active source code, or the existing 118-commit Git history.

## Safety Boundaries

The cleanup uses explicit path allowlists. It must not use `git clean -fd`, `git clean -fdX`, a recursive delete computed from Git output, or any command that can cross the repository root.

The following local state is preserved:

- `.git/` and all existing commits and branches.
- `.env`, which contains local credentials and machine-specific configuration.
- `.venv/`, so the existing Python development environment remains usable.
- `workspace/`, because it can contain generated projects and user data.
- The non-cache contents of `.codex/skills/ui-ux-pro-max/`, because they are a working local agent skill.
- All current backend, dashboard, desktop, packaging, and test source files.

No remote, tag, release, push, history rewrite, or branch deletion is part of this cleanup.

## Deletion Scope

### Reproducible build and dependency output

Delete these ignored, reproducible directories:

- `dashboard/node_modules/`
- `dashboard/dist/`
- `desktop/node_modules/`
- `desktop/dist/`
- `desktop/release/`
- `packaging/build/`
- `packaging/dist/`

### Caches, logs, and diagnostics

Delete Python `__pycache__/` directories outside `.venv`, `.pytest_cache/`, `.ruff_cache/`, `.tmp-rembg-check/`, root-level `debug_*` and `leak_*` files, generated logs, empty `.worktrees/`, and empty test scratch directories.

### Superseded UI prototype

Delete the tracked `new_design/` tree in full. Its layout was an implementation input for the production `dashboard/`; the completed production UI and Git history now preserve the relevant result. No runtime source imports it.

Delete the five untracked root-level `ui-*.png` review images because they are not referenced by current documentation and duplicate completed UI work.

## Source and Release Files to Keep and Track

Track the existing Electron/PyInstaller MVP source as one coherent set:

- `desktop/` source, configuration, tests, and lock file.
- `packaging/pyinstaller/` and `packaging/scripts/`.
- `src/renpy_mcp/web/fastapi_app.py` frozen dashboard-path support.
- `tests/unit/web/test_dashboard_path_resolution.py`.

Track `uv.lock` and stop ignoring it so Python dependency resolution is reproducible.

Add `.env.example` with placeholder-only configuration and add the MIT `LICENSE` file already claimed by the README. No value from `.env` may be copied into tracked files.

## Ignore Policy

Update `.gitignore` to:

- keep build, dependency, workspace, cache, and secret output excluded;
- ignore `.env.*` while explicitly allowing `.env.example`;
- ignore local `.claude/settings.local.json`, `.codex/`, Playwright reports, test results, and package-registry credential files;
- remove the obsolete `uv.lock` ignore rule;
- narrow generic Python `lib/` rules so they cannot hide application `src/lib` directories.

## Documentation Structure

The active documentation surface becomes:

- `README.md`: installation, current capabilities, verification commands, and honest maturity status.
- `AGENTS.md`: current product state, active priorities, repository map, and verification rules.
- `CHANGELOG.md`: an unreleased section aligned with package version `0.1.0`.
- `docs/README.md`: documentation index and status definitions.
- `docs/ROADMAP.md`: current 2026-07-12 priorities and known test failures.
- `docs/vn-engineering-middleware-gap-analysis.md`: active product-direction analysis.
- `docs/dual-agent-design.md`: explicitly future work, not an active implementation phase.
- The repository-cleanup specification and implementation plan under `docs/superpowers/`.

Move superseded root design documents, completed implementation designs, completed execution prompts, and partial packaging plans into `docs/archive/` with `[COMPLETED]`, `[PARTIAL]`, or `[SUPERSEDED]` prefixes. Update surviving cross-references after each move. Historical files remain available in Git even if later removed from the active documentation surface.

## Verification

Before staging:

1. Confirm `.env`, `.venv`, and `workspace/` still exist.
2. Confirm build outputs, caches, debug artifacts, and `new_design/` are gone.
3. Check Markdown relative links and reject broken local references.
4. Check `.env.example` contains placeholders only.
5. Run `uv lock --check` when `uv` is available.
6. Run backend unit tests and the targeted frozen-dashboard-path test.
7. Reinstall frontend dependencies from lock files in order to run Dashboard and Desktop tests/builds, then remove regenerated `node_modules` and build output again.
8. Run the integration suite and report its actual pass/fail result without claiming a fully green repository if known failures remain.

The real-LLM E2E test remains manual and is not run during repository cleanup.

## Git Commit

The existing Git repository and `master` history are retained. Stage with an explicit allowlist and inspect both the staged file list and diff before committing. The commit must exclude `.env`, `.venv`, `workspace/`, `.claude/`, `.codex/`, dependency directories, build output, and generated reports.

The task ends with one commit:

```text
chore: clean repository and refresh project status
```

## Success Criteria

- The working tree contains only active source, current documentation, preserved user/local state, and deliberately ignored local tools.
- At least 1 GiB of reproducible output is removed.
- Current desktop packaging source is tracked, but generated installers and PyInstaller output are not.
- Documentation no longer claims stale test counts or nonexistent files.
- No secret or absolute local path is added to Git.
- The final commit succeeds and its exact verification results are reported.
