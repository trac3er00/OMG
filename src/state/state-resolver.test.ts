import { describe, expect, test } from "bun:test";
import { existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { StateResolver } from "./state-resolver.js";

function tempProject(): string {
  return join(tmpdir(), `omg-state-project-${Date.now()}-${Math.random().toString(16).slice(2)}`);
}

describe("StateResolver", () => {
  test("resolves .omg/state layout", () => {
    const projectDir = tempProject();
    const resolver = new StateResolver(projectDir);
    const layout = resolver.layout();

    expect(layout.verificationController.endsWith(".omg/state/verification_controller")).toBe(true);
    expect(layout.memory.endsWith(".omg/state/memory.sqlite3")).toBe(true);
    rmSync(projectDir, { force: true, recursive: true });
  });

  test("ensure creates directory", () => {
    const projectDir = tempProject();
    const resolver = new StateResolver(projectDir);
    const created = resolver.ensure("ledger/sub");
    expect(existsSync(created)).toBe(true);
    rmSync(projectDir, { force: true, recursive: true });
  });
});
