import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

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

export interface BackendProcessHandle {
  child: ChildProcessWithoutNullStreams;
  startupFailure: Promise<never>;
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

export function startBackend(
  config: BackendLaunchConfig,
  logFile: string
): BackendProcessHandle {
  fs.mkdirSync(path.dirname(logFile), { recursive: true });
  const child = spawn(config.command, config.args, {
    env: config.env,
    windowsHide: true,
  });
  const log = fs.createWriteStream(logFile, { flags: "a" });
  const startupFailure = new Promise<never>((_resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      const detail = code === null ? `signal ${signal ?? "unknown"}` : `code ${code}`;
      reject(new Error(`Backend exited before becoming ready with ${detail}`));
    });
    log.once("error", reject);
  });

  child.stdout.pipe(log, { end: false });
  child.stderr.pipe(log, { end: false });
  child.once("close", () => log.end());

  return { child, startupFailure };
}
