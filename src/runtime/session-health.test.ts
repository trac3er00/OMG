import { describe, expect, test } from "bun:test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SessionHealthProvider } from "./session-health.js";

function makeProjectDir(): string {
  return mkdtempSync(join(tmpdir(), "omg-session-health-"));
}

describe("SessionHealthProvider", () => {
  test("returns healthy by default without drift observations", () => {
    const projectDir = makeProjectDir();
    try {
      const provider = SessionHealthProvider.create(projectDir, 3);
      const health = provider.getHealth("session-1");

      expect(health.status).toBe("healthy");
      expect(health.tool_count).toBe(3);
      expect(health.risk_level).toBe("low");
      expect(health.session_id).toBe("session-1");
      expect(health.drift_detected).toBeUndefined();
    } finally {
      rmSync(projectDir, { recursive: true, force: true });
    }
  });

  test("degrades session when drift is detected", () => {
    const projectDir = makeProjectDir();
    try {
      const provider = SessionHealthProvider.create(projectDir, 1);
      const health = provider.getHealth("session-2", [
        {
          timestamp: 1,
          goal: "build robust parser",
          output: "build robust parser",
        },
        {
          timestamp: 2,
          goal: "build robust parser",
          output: "build robust parser safely",
        },
        {
          timestamp: 3,
          goal: "build robust parser",
          output: "unrelated weather summary",
        },
        {
          timestamp: 4,
          goal: "build robust parser",
          output: "totally different gardening advice",
        },
      ]);

      expect(health.drift_detected).toBe(true);
      expect(health.drift_asi).toBeDefined();
      expect(["degraded", "critical"]).toContain(health.status);
      expect(health.drift_type).toBe("semantic");
    } finally {
      rmSync(projectDir, { recursive: true, force: true });
    }
  });
});
