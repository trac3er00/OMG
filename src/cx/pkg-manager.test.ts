import { describe, expect, test } from "bun:test";
import {
  detectPackageManagerFromFiles,
  getCommands,
  debugStackTrace,
} from "./pkg-manager.js";
import type { PackageManager } from "./pkg-manager.js";

describe("detectPackageManagerFromFiles", () => {
  test("bun.lock + package.json → bun", () => {
    expect(detectPackageManagerFromFiles(["package.json", "bun.lock"])).toBe(
      "bun",
    );
  });

  test("bun.lockb + package.json → bun", () => {
    expect(detectPackageManagerFromFiles(["package.json", "bun.lockb"])).toBe(
      "bun",
    );
  });

  test("yarn.lock + package.json → yarn", () => {
    expect(detectPackageManagerFromFiles(["package.json", "yarn.lock"])).toBe(
      "yarn",
    );
  });

  test("pnpm-lock.yaml + package.json → pnpm", () => {
    expect(
      detectPackageManagerFromFiles(["package.json", "pnpm-lock.yaml"]),
    ).toBe("pnpm");
  });

  test("package.json only → npm", () => {
    expect(detectPackageManagerFromFiles(["package.json"])).toBe("npm");
  });

  test("Cargo.toml → cargo", () => {
    expect(detectPackageManagerFromFiles(["Cargo.toml"])).toBe("cargo");
  });

  test("go.mod → go", () => {
    expect(detectPackageManagerFromFiles(["go.mod"])).toBe("go");
  });

  test("pyproject.toml → pip", () => {
    expect(detectPackageManagerFromFiles(["pyproject.toml"])).toBe("pip");
  });

  test("requirements.txt → pip", () => {
    expect(detectPackageManagerFromFiles(["requirements.txt"])).toBe("pip");
  });

  test("no recognized files → unknown", () => {
    expect(detectPackageManagerFromFiles(["README.md"])).toBe("unknown");
  });

  test("empty file list → unknown", () => {
    expect(detectPackageManagerFromFiles([])).toBe("unknown");
  });

  test("lock file without package.json skips to next rule", () => {
    expect(detectPackageManagerFromFiles(["bun.lock"])).toBe("unknown");
  });

  test("bun.lock takes priority over yarn.lock", () => {
    expect(
      detectPackageManagerFromFiles(["package.json", "bun.lock", "yarn.lock"]),
    ).toBe("bun");
  });
});

describe("getCommands", () => {
  const cases: { pm: PackageManager; install: string; addPrefix: string }[] = [
    { pm: "npm", install: "npm install", addPrefix: "npm install" },
    { pm: "yarn", install: "yarn install", addPrefix: "yarn add" },
    { pm: "pnpm", install: "pnpm install", addPrefix: "pnpm add" },
    { pm: "bun", install: "bun install", addPrefix: "bun add" },
    {
      pm: "pip",
      install: "pip install -r requirements.txt",
      addPrefix: "pip install",
    },
    { pm: "cargo", install: "cargo build", addPrefix: "cargo add" },
    { pm: "go", install: "go mod download", addPrefix: "go get" },
  ];

  for (const { pm, install, addPrefix } of cases) {
    test(`${pm}: install command`, () => {
      expect(getCommands(pm).install).toBe(install);
    });

    test(`${pm}: add command includes package name`, () => {
      expect(getCommands(pm).add("some-pkg")).toContain(addPrefix);
      expect(getCommands(pm).add("some-pkg")).toContain("some-pkg");
    });

    test(`${pm}: run command includes script name`, () => {
      expect(getCommands(pm).run("dev")).toContain("dev");
    });
  }

  test("unknown manager returns echo fallbacks", () => {
    const cmds = getCommands("unknown");
    expect(cmds.install).toContain("unknown");
    expect(cmds.test).toContain("no test runner");
  });
});

describe("debugStackTrace", () => {
  test("Cannot find module → suggests install with correct pm", () => {
    const trace = `Error: Cannot find module 'express'
    at Function.Module._resolveFilename (node:internal/modules/cjs/loader:933:15)`;

    const suggestions = debugStackTrace(trace, "bun");
    expect(suggestions.length).toBeGreaterThanOrEqual(1);

    const moduleSuggestion = suggestions.find(
      (s) => s.pattern === "Cannot find module",
    );
    expect(moduleSuggestion).toBeDefined();
    expect(moduleSuggestion!.fix).toBe("bun add express");
  });

  test("Cannot find module with npm → npm install", () => {
    const trace = "Error: Cannot find module 'lodash'";
    const suggestions = debugStackTrace(trace, "npm");
    const s = suggestions.find((s) => s.pattern === "Cannot find module");
    expect(s!.fix).toBe("npm install lodash");
  });

  test("ENOENT with path → suggests checking path", () => {
    const trace =
      "Error: ENOENT: no such file or directory, open '/app/config.json'";
    const suggestions = debugStackTrace(trace, "npm");

    const s = suggestions.find((s) => s.pattern === "ENOENT");
    expect(s).toBeDefined();
    expect(s!.fix).toContain("/app/config.json");
  });

  test("ENOENT without path → generic path suggestion", () => {
    const trace = "Error: ENOENT something went wrong";
    const suggestions = debugStackTrace(trace, "npm");
    expect(suggestions.find((s) => s.pattern === "ENOENT")).toBeDefined();
  });

  test("EADDRINUSE → suggests killing port process", () => {
    const trace = "Error: listen EADDRINUSE: address already in use :::3000";
    const suggestions = debugStackTrace(trace, "npm");

    const s = suggestions.find((s) => s.pattern === "EADDRINUSE");
    expect(s).toBeDefined();
    expect(s!.fix).toContain("3000");
  });

  test("TypeError → identifies the bad value", () => {
    const trace = "TypeError: foo is not a function";
    const suggestions = debugStackTrace(trace, "npm");

    const s = suggestions.find((s) => s.pattern === "TypeError");
    expect(s).toBeDefined();
    expect(s!.fix).toContain("foo");
  });

  test("ReferenceError → identifies undefined variable", () => {
    const trace = "ReferenceError: myVar is not defined";
    const suggestions = debugStackTrace(trace, "npm");

    const s = suggestions.find((s) => s.pattern === "ReferenceError");
    expect(s).toBeDefined();
    expect(s!.fix).toContain("myVar");
  });

  test("Rust compiler error → extracts error code", () => {
    const trace = "error[E0308]: mismatched types\n  --> src/main.rs:5:5";
    const suggestions = debugStackTrace(trace, "cargo");

    const s = suggestions.find((s) => s.pattern === "Rust compiler error");
    expect(s).toBeDefined();
    expect(s!.fix).toContain("E0308");
  });

  test("missing Rust crate → suggests cargo add", () => {
    const trace = "error: cannot find crate for `serde`";
    const suggestions = debugStackTrace(trace, "cargo");

    const s = suggestions.find((s) => s.pattern === "Missing Rust crate");
    expect(s).toBeDefined();
    expect(s!.fix).toBe("cargo add serde");
  });

  test("unknown trace → returns empty suggestions", () => {
    const trace = "Everything is fine, no errors here.";
    expect(debugStackTrace(trace, "npm")).toEqual([]);
  });

  test("multiple errors in one trace → returns multiple suggestions", () => {
    const trace = `Error: Cannot find module 'react'
TypeError: render is not a function`;
    const suggestions = debugStackTrace(trace, "yarn");
    expect(suggestions.length).toBeGreaterThanOrEqual(2);

    const patterns = suggestions.map((s) => s.pattern);
    expect(patterns).toContain("Cannot find module");
    expect(patterns).toContain("TypeError");
  });

  test("defaults to npm when no pm specified", () => {
    const trace = "Error: Cannot find module 'axios'";
    const suggestions = debugStackTrace(trace);
    const s = suggestions.find((s) => s.pattern === "Cannot find module");
    expect(s!.fix).toBe("npm install axios");
  });
});
