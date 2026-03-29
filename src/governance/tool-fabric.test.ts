import { describe, expect, test } from "bun:test";
import { rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ToolFabric } from "./tool-fabric.js";

describe("ToolFabric", () => {
  function mkFabric() {
    const dir = join(tmpdir(), `fabric-test-${Date.now()}-${Math.random().toString(16).slice(2)}`);
    return { fabric: new ToolFabric(dir), dir };
  }

  test("default lane allows any tool", async () => {
    const { fabric, dir } = mkFabric();
    try {
      const result = await fabric.evaluateRequest("Read", {});
      expect(result.action).toBe("allow");
    } finally {
      fabric.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("restricted lane blocks unauthorized tool", async () => {
    const { fabric, dir } = mkFabric();
    try {
      fabric.registerLane("restricted", { allowedTools: ["Read", "Grep"] });
      const result = await fabric.evaluateRequest("Write", {}, "restricted");
      expect(result.action).toBe("deny");
    } finally {
      fabric.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("restricted lane allows authorized tool", async () => {
    const { fabric, dir } = mkFabric();
    try {
      fabric.registerLane("restricted", { allowedTools: ["Read", "Grep"] });
      const result = await fabric.evaluateRequest("Read", {}, "restricted");
      expect(result.action).toBe("allow");
    } finally {
      fabric.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("ledger records decisions", async () => {
    const { fabric, dir } = mkFabric();
    try {
      fabric.registerLane("test-lane", { allowedTools: ["Read"] });
      await fabric.evaluateRequest("Write", {}, "test-lane");
      await fabric.evaluateRequest("Read", {}, "test-lane");

      const entries = fabric.getLedgerEntries();
      expect(entries.length).toBeGreaterThanOrEqual(2);
      expect(entries.some((entry) => entry.action === "deny")).toBe(true);
      expect(entries.some((entry) => entry.action === "allow")).toBe(true);
    } finally {
      fabric.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
