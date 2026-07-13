import path from "node:path";
import { fileURLToPath } from "node:url";

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

export function resolvePreloadPath(moduleUrl: string): string {
  return path.join(path.dirname(fileURLToPath(moduleUrl)), "preload.js");
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
