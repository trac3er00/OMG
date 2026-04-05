import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { AuditTrail } from "./audit-trail.js";

describe("AuditTrail", () => {
  test("record entry and verify signature", () => {
    const projectDir = join(tmpdir(), `audit-trail-${Date.now()}`);
    const trail = AuditTrail.create({ projectDir, secret: "test-secret" });

    const entry = trail.record({
      actor: "control-plane",
      action: "session.start",
      details: { runId: "run-123" },
    });

    expect(trail.verify(entry)).toBe(true);

    const auditPath = join(projectDir, ".omg", "state", "ledger", "audit.jsonl");
    expect(existsSync(auditPath)).toBe(true);
    const lines = readFileSync(auditPath, "utf8").trim().split("\n");
    expect(lines.length).toBe(1);

    rmSync(projectDir, { recursive: true, force: true });
  });

  test("tampered entry fails verification", () => {
    const projectDir = join(tmpdir(), `audit-trail-tamper-${Date.now()}`);
    const trail = AuditTrail.create({ projectDir, secret: "test-secret" });

    const entry = trail.record({ actor: "agent", action: "mutation.approve" });
    const tampered = {
      ...entry,
      action: "mutation.deny",
    };

    expect(trail.verify(tampered)).toBe(false);

    rmSync(projectDir, { recursive: true, force: true });
  });
});
