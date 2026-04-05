import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { AuditTrail, HMAC_KEY_FILENAME } from "./audit-trail.js";

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

    const auditPath = join(
      projectDir,
      ".omg",
      "state",
      "ledger",
      "audit.jsonl",
    );
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

  test("hmac key persists across restarts", () => {
    const projectDir = join(tmpdir(), `audit-persist-${Date.now()}`);

    const trail1 = AuditTrail.create({ projectDir });
    const entry = trail1.record({ actor: "agent", action: "persist.test" });

    const keyPath = join(projectDir, ".omg", "state", HMAC_KEY_FILENAME);
    expect(existsSync(keyPath)).toBe(true);

    const keyContent = readFileSync(keyPath, "utf8").trim();
    expect(keyContent).toHaveLength(64);

    const trail2 = AuditTrail.create({ projectDir });
    expect(trail2.verify(entry)).toBe(true);

    rmSync(projectDir, { recursive: true, force: true });
  });

  test("env var override takes precedence over key file", () => {
    const projectDir = join(tmpdir(), `audit-env-${Date.now()}`);
    const envSecret = "env-override-secret-hex-value-for-testing";

    const saved = process.env.OMG_AUDIT_HMAC_SECRET;
    process.env.OMG_AUDIT_HMAC_SECRET = envSecret;
    try {
      const trail = AuditTrail.create({ projectDir });
      const entry = trail.record({ actor: "agent", action: "env.test" });

      const trail2 = AuditTrail.create({ projectDir });
      expect(trail2.verify(entry)).toBe(true);

      const trailWithFile = AuditTrail.create({
        projectDir,
        secret: "different",
      });
      expect(trailWithFile.verify(entry)).toBe(false);
    } finally {
      if (saved === undefined) {
        delete process.env.OMG_AUDIT_HMAC_SECRET;
      } else {
        process.env.OMG_AUDIT_HMAC_SECRET = saved;
      }
    }

    rmSync(projectDir, { recursive: true, force: true });
  });

  test("key file has restrictive permissions (0600)", () => {
    const projectDir = join(tmpdir(), `audit-perms-${Date.now()}`);

    AuditTrail.create({ projectDir });

    const keyPath = join(projectDir, ".omg", "state", HMAC_KEY_FILENAME);
    const stats = statSync(keyPath);
    const mode = stats.mode & 0o777;
    expect(mode).toBe(0o600);

    rmSync(projectDir, { recursive: true, force: true });
  });

  test("rotateKey backs up old key and generates new one", () => {
    const projectDir = join(tmpdir(), `audit-rotate-${Date.now()}`);

    AuditTrail.create({ projectDir });
    const keyPath = join(projectDir, ".omg", "state", HMAC_KEY_FILENAME);
    const originalKey = readFileSync(keyPath, "utf8").trim();

    const result = AuditTrail.rotateKey({ projectDir });

    expect(result.keyPath).toBe(keyPath);
    expect(result.backupPath).not.toBeNull();
    expect(existsSync(result.backupPath!)).toBe(true);

    const newKey = readFileSync(keyPath, "utf8").trim();
    expect(newKey).not.toBe(originalKey);
    expect(newKey).toHaveLength(64);

    const backedUpKey = readFileSync(result.backupPath!, "utf8").trim();
    expect(backedUpKey).toBe(originalKey);

    rmSync(projectDir, { recursive: true, force: true });
  });
});
