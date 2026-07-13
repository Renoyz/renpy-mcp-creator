# Electron Packaging MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the current RenPy MCP Creator codebase as a Windows Electron desktop app that starts the local Python/FastAPI backend and opens the existing dashboard.

**Architecture:** Electron owns desktop lifecycle and launches the backend as a child process. The Python backend continues to serve `/dashboard`, `/api`, and WebSocket routes on `127.0.0.1:<dynamic-port>`, so the React dashboard does not need a new API mode. Packaging is split into an Electron app under `desktop/` and PyInstaller build scripts under `packaging/`.

**Tech Stack:** Electron 41, electron-builder 26, TypeScript, Vitest, PyInstaller, existing FastAPI backend, existing Vite dashboard.

---

## File Structure

- Create `desktop/package.json`: Electron desktop package scripts and dependency versions.
- Create `desktop/tsconfig.json`: TypeScript config for Electron main-process code.
- Create `desktop/vitest.config.ts`: unit test config for desktop helper modules.
- Create `desktop/src/ports.ts`: find a free local TCP port.
- Create `desktop/src/paths.ts`: resolve packaged/backend/log/workspace paths.
- Create `desktop/src/backendProcess.ts`: spawn and stop the packaged backend process.
- Create `desktop/src/main.ts`: Electron app lifecycle, backend startup, window creation, and shutdown.
- Create `desktop/src/preload.ts`: empty preload bridge reserved for future safe IPC.
- Create `desktop/src/*.test.ts`: unit tests for ports, path resolution, and backend spawn args.
- Create `desktop/electron-builder.yml`: Windows builder configuration and extra resources.
- Create `packaging/pyinstaller/electron_backend_entry.py`: stable PyInstaller entrypoint that imports `renpy_mcp.main`.
- Create `packaging/pyinstaller/renpy-mcp-electron.spec`: PyInstaller entry for the backend.
- Create `packaging/scripts/build-dashboard.ps1`: build dashboard static files.
- Create `packaging/scripts/build-backend.ps1`: build backend executable.
- Create `packaging/scripts/build-electron.ps1`: install/build/package desktop app.
- Modify `.gitignore`: ignore desktop build outputs while keeping source files tracked.
- Modify `src/renpy_mcp/web/fastapi_app.py`: support dashboard static path when running from a PyInstaller frozen bundle.

## Task 1: Desktop Port Utility

**Files:**
- Create: `desktop/package.json`
- Create: `desktop/tsconfig.json`
- Create: `desktop/vitest.config.ts`
- Create: `desktop/src/ports.ts`
- Test: `desktop/src/ports.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it } from "vitest";
import { findFreePort } from "./ports";

describe("findFreePort", () => {
  it("returns an available loopback port", async () => {
    const port = await findFreePort();
    expect(Number.isInteger(port)).toBe(true);
    expect(port).toBeGreaterThan(0);
    expect(port).toBeLessThanOrEqual(65535);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd desktop; npm install; npm test -- --run src/ports.test.ts`

Expected: FAIL because `desktop/` and `findFreePort` do not exist.

- [ ] **Step 3: Add minimal desktop package and implementation**

Create `desktop/package.json`:

```json
{
  "name": "renpy-mcp-creator-desktop",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "main": "dist/main.js",
  "scripts": {
    "test": "vitest run",
    "build": "tsc -p tsconfig.json",
    "start": "npm run build && electron .",
    "dist": "npm run build && electron-builder --config electron-builder.yml"
  },
  "devDependencies": {
    "@types/node": "^25.6.0",
    "electron": "41.3.0",
    "electron-builder": "26.8.1",
    "typescript": "^6.0.2",
    "vitest": "^4.1.5"
  }
}
```

Create `desktop/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "lib": ["ES2022"],
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "outDir": "dist",
    "rootDir": "src",
    "types": ["node"]
  },
  "include": ["src/**/*.ts"]
}
```

Create `desktop/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
  },
});
```

Create `desktop/src/ports.ts`:

```ts
import net from "node:net";

export function findFreePort(host = "127.0.0.1"): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.on("error", reject);
    server.listen(0, host, () => {
      const address = server.address();
      if (address == null || typeof address === "string") {
        server.close(() => reject(new Error("Unable to allocate a TCP port")));
        return;
      }
      const port = address.port;
      server.close(() => resolve(port));
    });
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd desktop; npm test -- --run src/ports.test.ts`

Expected: PASS.

## Task 2: Packaged Path Resolution

**Files:**
- Create: `desktop/src/paths.ts`
- Test: `desktop/src/paths.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import path from "node:path";
import { describe, expect, it } from "vitest";
import { resolveDesktopPaths } from "./paths";

describe("resolveDesktopPaths", () => {
  it("places mutable workspace and logs under userData", () => {
    const paths = resolveDesktopPaths({
      appPath: "C:/app",
      resourcesPath: "C:/app/resources",
      userDataPath: "C:/Users/Test/AppData/Roaming/RenPy MCP Creator",
      isPackaged: true,
      platform: "win32",
    });

    expect(paths.backendExecutable).toBe(path.join("C:/app/resources", "backend", "renpy-mcp-electron.exe"));
    expect(paths.workspaceDir).toBe(path.join("C:/Users/Test/AppData/Roaming/RenPy MCP Creator", "workspace"));
    expect(paths.logsDir).toBe(path.join("C:/Users/Test/AppData/Roaming/RenPy MCP Creator", "logs"));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd desktop; npm test -- --run src/paths.test.ts`

Expected: FAIL because `resolveDesktopPaths` does not exist.

- [ ] **Step 3: Implement path resolution**

Create `desktop/src/paths.ts`:

```ts
import path from "node:path";

export interface DesktopPathInput {
  appPath: string;
  resourcesPath: string;
  userDataPath: string;
  isPackaged: boolean;
  platform: NodeJS.Platform;
}

export interface DesktopPaths {
  backendExecutable: string;
  workspaceDir: string;
  logsDir: string;
}

export function resolveDesktopPaths(input: DesktopPathInput): DesktopPaths {
  const executableName = input.platform === "win32" ? "renpy-mcp-electron.exe" : "renpy-mcp-electron";
  const backendRoot = input.isPackaged
    ? path.join(input.resourcesPath, "backend")
    : path.resolve(input.appPath, "..", "packaging", "dist", "renpy-mcp-electron");

  return {
    backendExecutable: path.join(backendRoot, executableName),
    workspaceDir: path.join(input.userDataPath, "workspace"),
    logsDir: path.join(input.userDataPath, "logs"),
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd desktop; npm test -- --run src/paths.test.ts`

Expected: PASS.

## Task 3: Backend Process Manager

**Files:**
- Create: `desktop/src/backendProcess.ts`
- Test: `desktop/src/backendProcess.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, expect, it, vi } from "vitest";
import { createBackendLaunchConfig } from "./backendProcess";

describe("createBackendLaunchConfig", () => {
  it("builds backend args and electron-specific environment", () => {
    const config = createBackendLaunchConfig({
      executable: "C:/app/backend/renpy-mcp-electron.exe",
      port: 49152,
      workspaceDir: "C:/user/workspace",
      logsDir: "C:/user/logs",
      baseEnv: { PATH: "C:/Windows" },
    });

    expect(config.command).toBe("C:/app/backend/renpy-mcp-electron.exe");
    expect(config.args).toEqual([
      "--transport",
      "http",
      "--host",
      "127.0.0.1",
      "--port",
      "49152",
      "--no-browser",
    ]);
    expect(config.env.RENPY_MCP_ELECTRON).toBe("1");
    expect(config.env.RENPY_MCP_WORKSPACE).toBe("C:/user/workspace");
    expect(config.env.RENPY_MCP_LOG_DIR).toBe("C:/user/logs");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd desktop; npm test -- --run src/backendProcess.test.ts`

Expected: FAIL because `createBackendLaunchConfig` does not exist.

- [ ] **Step 3: Implement backend process manager**

Create `desktop/src/backendProcess.ts`:

```ts
import fs from "node:fs";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";

export interface BackendLaunchInput {
  executable: string;
  port: number;
  workspaceDir: string;
  logsDir: string;
  baseEnv?: NodeJS.ProcessEnv;
}

export interface BackendLaunchConfig {
  command: string;
  args: string[];
  env: NodeJS.ProcessEnv;
}

export function createBackendLaunchConfig(input: BackendLaunchInput): BackendLaunchConfig {
  return {
    command: input.executable,
    args: [
      "--transport",
      "http",
      "--host",
      "127.0.0.1",
      "--port",
      String(input.port),
      "--no-browser",
    ],
    env: {
      ...(input.baseEnv ?? process.env),
      RENPY_MCP_ELECTRON: "1",
      RENPY_MCP_WORKSPACE: input.workspaceDir,
      RENPY_MCP_LOG_DIR: input.logsDir,
    },
  };
}

export function startBackend(config: BackendLaunchConfig, logFile: string): ChildProcessWithoutNullStreams {
  fs.mkdirSync(fs.dirname(logFile), { recursive: true });
  const child = spawn(config.command, config.args, {
    env: config.env,
    windowsHide: true,
  });
  const log = fs.createWriteStream(logFile, { flags: "a" });
  child.stdout.pipe(log);
  child.stderr.pipe(log);
  return child;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd desktop; npm test -- --run src/backendProcess.test.ts`

Expected: PASS.

## Task 4: Electron Main Process

**Files:**
- Create: `desktop/src/main.ts`
- Create: `desktop/src/preload.ts`
- Modify: `desktop/package.json`

- [ ] **Step 1: Write smoke-build test by compiling TypeScript**

Run: `cd desktop; npm run build`

Expected: FAIL because `main.ts` does not exist but `package.json` points to `dist/main.js`.

- [ ] **Step 2: Implement Electron lifecycle**

Create `desktop/src/preload.ts`:

```ts
export {};
```

Create `desktop/src/main.ts`:

```ts
import path from "node:path";
import { app, BrowserWindow, dialog } from "electron";
import { createBackendLaunchConfig, startBackend } from "./backendProcess.js";
import { resolveDesktopPaths } from "./paths.js";
import { findFreePort } from "./ports.js";

let mainWindow: BrowserWindow | null = null;
let backendProcess: ReturnType<typeof startBackend> | null = null;

async function waitForDashboard(url: string, timeoutMs = 30000): Promise<void> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const resp = await fetch(url);
      if (resp.ok) return;
    } catch {
      // Backend is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Backend did not become ready within ${timeoutMs}ms`);
}

async function createWindow(): Promise<void> {
  const port = await findFreePort();
  const paths = resolveDesktopPaths({
    appPath: app.getAppPath(),
    resourcesPath: process.resourcesPath,
    userDataPath: app.getPath("userData"),
    isPackaged: app.isPackaged,
    platform: process.platform,
  });

  const launchConfig = createBackendLaunchConfig({
    executable: paths.backendExecutable,
    port,
    workspaceDir: paths.workspaceDir,
    logsDir: paths.logsDir,
  });

  backendProcess = startBackend(launchConfig, path.join(paths.logsDir, "backend.log"));
  const dashboardUrl = `http://127.0.0.1:${port}/dashboard`;

  try {
    await waitForDashboard(dashboardUrl);
  } catch (error) {
    dialog.showErrorBox("Backend failed to start", error instanceof Error ? error.message : String(error));
    throw error;
  }

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 940,
    minWidth: 1180,
    minHeight: 760,
    title: "RenPy MCP Creator",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  await mainWindow.loadURL(dashboardUrl);
}

app.whenReady().then(() => {
  void createWindow();
});

app.on("window-all-closed", () => {
  app.quit();
});

app.on("before-quit", () => {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill();
  }
});
```

- [ ] **Step 3: Run build**

Run: `cd desktop; npm run build`

Expected: PASS.

## Task 5: Dashboard Path for Frozen Backend

**Files:**
- Modify: `src/renpy_mcp/web/fastapi_app.py`
- Test: `tests/unit/web/test_dashboard_path_resolution.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from renpy_mcp.web import fastapi_app


def test_dashboard_dir_uses_frozen_bundle_root(monkeypatch, tmp_path):
    bundle_root = tmp_path / "bundle"
    dashboard = bundle_root / "dashboard" / "dist"
    dashboard.mkdir(parents=True)
    monkeypatch.setattr(fastapi_app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(fastapi_app.sys, "_MEIPASS", str(bundle_root), raising=False)

    assert fastapi_app._resolve_dashboard_dir() == dashboard
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/web/test_dashboard_path_resolution.py -q`

Expected: FAIL because `_resolve_dashboard_dir` does not exist.

- [ ] **Step 3: Implement frozen path resolution**

Modify `src/renpy_mcp/web/fastapi_app.py`:

```python
import sys
```

Add:

```python
def _resolve_dashboard_dir() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return bundle_root / "dashboard" / "dist"
    return Path(__file__).parent.parent.parent.parent / "dashboard" / "dist"
```

Change:

```python
DASHBOARD_DIR = Path(__file__).parent.parent.parent.parent / "dashboard" / "dist"
```

to:

```python
DASHBOARD_DIR = _resolve_dashboard_dir()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/web/test_dashboard_path_resolution.py -q`

Expected: PASS.

## Task 6: Packaging Scripts and Builder Config

**Files:**
- Create: `desktop/electron-builder.yml`
- Create: `packaging/pyinstaller/renpy-mcp-electron.spec`
- Create: `packaging/scripts/build-dashboard.ps1`
- Create: `packaging/scripts/build-backend.ps1`
- Create: `packaging/scripts/build-electron.ps1`
- Modify: `.gitignore`

- [ ] **Step 1: Add packaging files**

Create `desktop/electron-builder.yml`:

```yaml
appId: com.renpymcp.creator
productName: RenPy MCP Creator
directories:
  output: release
files:
  - dist/**
  - package.json
extraResources:
  - from: ../packaging/dist/renpy-mcp-electron
    to: backend
win:
  target:
    - nsis
  artifactName: "${productName} Setup ${version}.${ext}"
nsis:
  oneClick: false
  perMachine: false
  allowToChangeInstallationDirectory: true
```

Create `packaging/pyinstaller/renpy-mcp-electron.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

repo_root = Path.cwd()
dashboard_dist = repo_root / "dashboard" / "dist"

a = Analysis(
    [str(repo_root / "packaging" / "pyinstaller" / "electron_backend_entry.py")],
    pathex=[str(repo_root / "src")],
    binaries=[],
    datas=[
        (str(dashboard_dist), "dashboard/dist"),
        (str(repo_root / "src" / "renpy_mcp" / "web" / "static"), "renpy_mcp/web/static"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="renpy-mcp-electron",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="renpy-mcp-electron",
)
```

Create scripts:

```powershell
# packaging/scripts/build-dashboard.ps1
$ErrorActionPreference = "Stop"
Push-Location "$PSScriptRoot/../../dashboard"
npm install
npm run build
Pop-Location
```

```powershell
# packaging/scripts/build-backend.ps1
$ErrorActionPreference = "Stop"
Push-Location "$PSScriptRoot/../.."
python -m pip install pyinstaller
pyinstaller packaging/pyinstaller/renpy-mcp-electron.spec --distpath packaging/dist --workpath packaging/build --noconfirm
Pop-Location
```

```powershell
# packaging/scripts/build-electron.ps1
$ErrorActionPreference = "Stop"
Push-Location "$PSScriptRoot/../../desktop"
npm install
npm run dist
Pop-Location
```

- [ ] **Step 2: Ignore generated outputs**

Add to `.gitignore`:

```gitignore
# Desktop packaging
desktop/node_modules/
desktop/dist/
desktop/release/
packaging/build/
packaging/dist/
```

- [ ] **Step 3: Verify package config compiles**

Run: `cd desktop; npm run build`

Expected: PASS.

## Task 7: Verification

**Files:**
- No new files.

- [ ] **Step 1: Run desktop tests**

Run: `cd desktop; npm test`

Expected: all desktop tests pass.

- [ ] **Step 2: Run backend path test**

Run: `python -m pytest tests/unit/web/test_dashboard_path_resolution.py -q`

Expected: PASS.

- [ ] **Step 3: Run frontend build regression**

Run: `cd dashboard; npm run build`

Expected: PASS.

- [ ] **Step 4: Run existing focused frontend tests**

Run: `cd dashboard; npx vitest run src/AppShell.test.tsx src/pages/ProjectWorkspacePage.test.tsx`

Expected: PASS.

- [ ] **Step 5: Produce packaging dry-run command list**

Do not run a full installer build unless PyInstaller and Electron dependencies are installed successfully. Document the commands:

```powershell
.\packaging\scripts\build-dashboard.ps1
.\packaging\scripts\build-backend.ps1
.\packaging\scripts\build-electron.ps1
```

Expected: these scripts exist and are ready for a Windows packaging dry run.
