import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  createBackendLaunchConfig,
  startBackend,
  type BackendLaunchConfig,
  type BackendProcessHandle,
} from "./backendProcess";

const tempDirs: string[] = [];
const closePromises: Promise<void>[] = [];

function createLogFile(): string {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "renpy-mcp-desktop-"));
  tempDirs.push(tempDir);
  return path.join(tempDir, "backend.log");
}

afterEach(async () => {
  await Promise.all(closePromises.splice(0));
  for (const tempDir of tempDirs.splice(0)) {
    fs.rmSync(tempDir, { force: true, recursive: true });
  }
});

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

describe("startBackend", () => {
  it("reports an unavailable executable through startupFailure", async () => {
    const handle = startBackendForTest({
      command: path.join(os.tmpdir(), `missing-renpy-backend-${process.pid}.exe`),
      args: [],
      env: process.env,
    });

    await expect(handle.startupFailure).rejects.toMatchObject({ code: "ENOENT" });
  });

  it("reports a backend that exits with code 23 before readiness", async () => {
    const handle = startBackendForTest({
      command: process.execPath,
      args: ["-e", "process.exit(23)"],
      env: process.env,
    });

    await expect(handle.startupFailure).rejects.toThrow(/exited before becoming ready.*23/i);
  });
});

function startBackendForTest(config: BackendLaunchConfig): BackendProcessHandle {
  const handle = startBackend(config, createLogFile());
  closePromises.push(
    new Promise((resolve) => {
      handle.child.once("close", () => resolve());
    })
  );

  return handle;
}
