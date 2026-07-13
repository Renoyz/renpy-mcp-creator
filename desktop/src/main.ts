import path from "node:path";
import { app, BrowserWindow, dialog } from "electron";
import { createBackendLaunchConfig, startBackend } from "./backendProcess.js";
import { resolveDesktopPaths, resolvePreloadPath } from "./paths.js";
import { findFreePort } from "./ports.js";

let mainWindow: BrowserWindow | null = null;
let backendProcess: ReturnType<typeof startBackend>["child"] | null = null;

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

  const backend = startBackend(launchConfig, path.join(paths.logsDir, "backend.log"));
  backendProcess = backend.child;
  const dashboardUrl = `http://127.0.0.1:${port}/dashboard`;

  await Promise.race([waitForDashboard(dashboardUrl), backend.startupFailure]);

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 940,
    minWidth: 1180,
    minHeight: 760,
    title: "RenPy MCP Creator",
    webPreferences: {
      preload: resolvePreloadPath(import.meta.url),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  await mainWindow.loadURL(dashboardUrl);
}

function stopBackend(): void {
  const child = backendProcess;
  backendProcess = null;
  if (child?.pid !== undefined && child.exitCode === null && !child.killed) {
    child.kill();
  }
}

function handleStartupFailure(error: unknown): void {
  stopBackend();
  dialog.showErrorBox("Backend failed to start", error instanceof Error ? error.message : String(error));
  app.quit();
}

void app.whenReady().then(createWindow).catch(handleStartupFailure);

app.on("window-all-closed", () => {
  app.quit();
});

app.on("before-quit", () => {
  stopBackend();
});
