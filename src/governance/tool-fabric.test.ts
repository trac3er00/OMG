import { describe, expect, test } from "bun:test";
import { rmSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ToolFabric } from "./tool-fabric.js";

describe("ToolFabric", () => {
  function mkFabric() {
    const dir = join(
      tmpdir(),
      `fabric-test-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    );
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

  test("ledger round-trip preserves persisted decision", async () => {
    const { fabric, dir } = mkFabric();
    try {
      fabric.registerLane("restricted", { allowedTools: ["Read"] });
      const decision = await fabric.evaluateRequest(
        "Read",
        { sample: true },
        "restricted",
      );

      const [persisted] = fabric.getLedgerEntries();
      expect(persisted).toEqual({ ...decision, args: { sample: true } });
    } finally {
      fabric.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("ledger write errors propagate instead of being swallowed", async () => {
    const dir = join(
      tmpdir(),
      `fabric-test-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    );
    const fabric = new ToolFabric(dir, {
      appendLedgerLine: () => {
        throw new Error("ledger write failed");
      },
    });

    try {
      await expect(fabric.evaluateRequest("Read", {})).rejects.toThrow(
        "ledger write failed",
      );
    } finally {
      fabric.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("malformed ledger entries throw on read instead of being ignored", () => {
    const { fabric, dir } = mkFabric();
    const ledgerDir = join(dir, ".omg", "state", "ledger");
    const ledgerPath = join(ledgerDir, "tool-fabric.jsonl");

    try {
      mkdirSync(ledgerDir, { recursive: true });
      writeFileSync(ledgerPath, '{"action":"allow"}\nnot-json\n', "utf8");

      expect(() => fabric.getLedgerEntries()).toThrow(
        "Failed to parse tool fabric ledger entry 2",
      );
    } finally {
      fabric.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("default lane remains passthrough and executes unapproved tools", async () => {
    const { fabric, dir } = mkFabric();
    const executions: string[] = [];

    try {
      const result = await fabric.executeTool(
        "Write",
        { payload: true },
        "default",
        async (tool) => {
          executions.push(tool);
          return { ok: true };
        },
      );

      expect(result.decision.action).toBe("allow");
      expect(result.output).toEqual({ ok: true });
      expect(executions).toEqual(["Write"]);
    } finally {
      fabric.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("restricted lane deny blocks executor dispatch", async () => {
    const { fabric, dir } = mkFabric();
    const executions: string[] = [];

    try {
      fabric.registerLane("restricted", { allowedTools: ["Read"] });

      const result = await fabric.executeTool(
        "Write",
        {},
        "restricted",
        async (tool) => {
          executions.push(tool);
          return { ok: true };
        },
      );

      expect(result.decision.action).toBe("deny");
      expect(result.output).toBeUndefined();
      expect(executions).toEqual([]);
    } finally {
      fabric.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
