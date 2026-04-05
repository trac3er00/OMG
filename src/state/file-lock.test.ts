import { describe, expect, test } from "bun:test";
import { existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { acquireLock, withLock } from "./file-lock.js";

function tempPath(name: string): string {
  return join(tmpdir(), `omg-lock-${name}-${Date.now()}-${Math.random().toString(16).slice(2)}`);
}

describe("file locking", () => {
  test("acquireLock creates file and releases", async () => {
    const filePath = tempPath("lockfile");
    const release = await acquireLock(filePath);
    expect(existsSync(filePath)).toBe(true);
    await release();
    rmSync(filePath, { force: true, recursive: true });
    rmSync(`${filePath}.lock`, { force: true, recursive: true });
  });

  test("withLock executes callback result", async () => {
    const filePath = tempPath("withlock");
    const output = await withLock(filePath, async () => "ok");
    expect(output).toBe("ok");
    rmSync(filePath, { force: true, recursive: true });
    rmSync(`${filePath}.lock`, { force: true, recursive: true });
  });
});
