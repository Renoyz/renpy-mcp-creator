import path from "node:path";
import { pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";
import { resolveDesktopPaths, resolvePreloadPath } from "./paths";

describe("resolveDesktopPaths", () => {
  it("places mutable workspace and logs under userData", () => {
    const paths = resolveDesktopPaths({
      appPath: "C:/app",
      resourcesPath: "C:/app/resources",
      userDataPath: "C:/Users/Test/AppData/Roaming/RenPy MCP Creator",
      isPackaged: true,
      platform: "win32",
    });

    expect(paths.backendExecutable).toBe(
      path.join("C:/app/resources", "backend", "renpy-mcp-electron.exe")
    );
    expect(paths.workspaceDir).toBe(
      path.join("C:/Users/Test/AppData/Roaming/RenPy MCP Creator", "workspace")
    );
    expect(paths.logsDir).toBe(
      path.join("C:/Users/Test/AppData/Roaming/RenPy MCP Creator", "logs")
    );
  });

  it("resolves the preload script from an ESM module URL", () => {
    const mainModulePath = path.join("C:/app", "dist", "main.js");

    expect(resolvePreloadPath(pathToFileURL(mainModulePath).href)).toBe(
      path.join("C:/app", "dist", "preload.js")
    );
  });
});
