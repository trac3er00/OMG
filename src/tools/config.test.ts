import { describe, expect, test } from "bun:test";
import { ConfigDiscovery } from "./config.js";
import type { ConfigDeps } from "./config.js";
import type { Stats } from "node:fs";

function makeStats(overrides: { isFile?: boolean; isDir?: boolean; size?: number } = {}): Stats {
  return {
    isFile: () => overrides.isFile ?? false,
    isDirectory: () => overrides.isDir ?? false,
    size: overrides.size ?? 0,
    isBlockDevice: () => false,
    isCharacterDevice: () => false,
    isSymbolicLink: () => false,
    isFIFO: () => false,
    isSocket: () => false,
    dev: 0,
    ino: 0,
    mode: 0,
    nlink: 0,
    uid: 0,
    gid: 0,
    rdev: 0,
    blksize: 0,
    blocks: 0,
    atimeMs: 0,
    mtimeMs: 0,
    ctimeMs: 0,
    birthtimeMs: 0,
    atime: new Date(0),
    mtime: new Date(0),
    ctime: new Date(0),
    birthtime: new Date(0),
  } as Stats;
}

function makeDeps(existingPaths: Record<string, { isFile?: boolean; isDir?: boolean; size?: number }>): ConfigDeps {
  return {
    stat: (async (path: string) => {
      const entry = existingPaths[path];
      if (!entry) throw new Error(`ENOENT: ${path}`);
      return makeStats(entry);
    }) as ConfigDeps["stat"],
    readdir: (async () => []) as unknown as ConfigDeps["readdir"],
    access: (async (path: string) => {
      if (!(path in existingPaths)) throw new Error(`EACCES: ${path}`);
    }) as ConfigDeps["access"],
  };
}

describe("ConfigDiscovery", () => {
  test("create returns ConfigDiscovery instance", () => {
    const cd = ConfigDiscovery.create();
    expect(cd).toBeInstanceOf(ConfigDiscovery);
  });

  test("discoverConfigs on nonexistent dir returns error", async () => {
    const deps = makeDeps({});
    const cd = ConfigDiscovery.create(deps);
    const result = await cd.discoverConfigs("/nonexistent");
    expect(result.configs).toEqual([]);
    expect(result.error).toContain("does not exist");
  });

  test("discoverConfigs finds claude_code configs", async () => {
    const deps = makeDeps({
      "/project": { isDir: true },
      "/project/CLAUDE.md": { isFile: true, size: 500 },
    });
    const cd = ConfigDiscovery.create(deps);
    const result = await cd.discoverConfigs("/project");

    expect(result.error).toBeUndefined();
    const claude = result.configs.find((c) => c.tool === "claude_code");
    expect(claude).toBeDefined();
    expect(claude?.paths).toContain("CLAUDE.md");
    expect(claude?.format).toBe("markdown");
    expect(claude?.sizeBytes).toBe(500);
    expect(claude?.readable).toBe(true);
  });

  test("discoverConfigs finds directory-type configs", async () => {
    const deps = makeDeps({
      "/project": { isDir: true },
      "/project/.vscode": { isDir: true },
    });
    const cd = ConfigDiscovery.create(deps);
    const result = await cd.discoverConfigs("/project");

    const vscode = result.configs.find((c) => c.tool === "vscode");
    expect(vscode).toBeDefined();
    expect(vscode?.format).toBe("directory");
  });

  test("discoverConfigs returns empty when no configs found", async () => {
    const deps = makeDeps({
      "/empty": { isDir: true },
    });
    const cd = ConfigDiscovery.create(deps);
    const result = await cd.discoverConfigs("/empty");

    expect(result.configs).toEqual([]);
    expect(result.error).toBeUndefined();
  });

  test("discoverConfigs finds multiple tool configs", async () => {
    const deps = makeDeps({
      "/project": { isDir: true },
      "/project/CLAUDE.md": { isFile: true, size: 100 },
      "/project/.cursorrules": { isFile: true, size: 200 },
      "/project/AGENTS.md": { isFile: true, size: 300 },
    });
    const cd = ConfigDiscovery.create(deps);
    const result = await cd.discoverConfigs("/project");

    const toolNames = result.configs.map((c) => c.tool);
    expect(toolNames).toContain("claude_code");
    expect(toolNames).toContain("cursor");
    expect(toolNames).toContain("codex");
  });

  test("discoverConfigs includes timestamp", async () => {
    const deps = makeDeps({
      "/project": { isDir: true },
    });
    const cd = ConfigDiscovery.create(deps);
    const result = await cd.discoverConfigs("/project");

    expect(result.timestamp).toBeTruthy();
    expect(result.scanDir).toBe("/project");
  });

  test("mergeConfigs creates tool-keyed map", () => {
    const cd = ConfigDiscovery.create();
    const merged = cd.mergeConfigs([
      { tool: "claude_code", paths: ["CLAUDE.md"], format: "markdown", sizeBytes: 100, readable: true },
      { tool: "cursor", paths: [".cursorrules"], format: "unknown", sizeBytes: 200, readable: true },
    ]);

    expect(merged["claude_code"]?.tool).toBe("claude_code");
    expect(merged["cursor"]?.sizeBytes).toBe(200);
  });

  test("mergeConfigs later entries overwrite earlier for same tool", () => {
    const cd = ConfigDiscovery.create();
    const merged = cd.mergeConfigs([
      { tool: "claude_code", paths: ["old.md"], format: "markdown", sizeBytes: 100, readable: true },
      { tool: "claude_code", paths: ["new.md"], format: "markdown", sizeBytes: 999, readable: true },
    ]);

    expect(merged["claude_code"]?.sizeBytes).toBe(999);
    expect(merged["claude_code"]?.paths).toContain("new.md");
  });

  test("mergeConfigs returns empty object for empty input", () => {
    const cd = ConfigDiscovery.create();
    const merged = cd.mergeConfigs([]);
    expect(Object.keys(merged)).toHaveLength(0);
  });
});
