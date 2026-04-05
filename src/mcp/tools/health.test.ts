import { afterEach, describe, expect, test } from "bun:test";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { SessionHealthProvider } from "../../runtime/session-health.js";
import { createGuideAssertTool, createSessionHealthTool } from "./health.js";

function makeTempProject(): string {
  const dir = mkdtempSync(join(tmpdir(), "omg-health-test-"));
  const stateDir = join(dir, ".omg", "state");
  mkdirSync(stateDir, { recursive: true });
  return dir;
}

const tempDirs: string[] = [];

afterEach(() => {
  for (const dir of tempDirs) {
    try {
      rmSync(dir, { recursive: true, force: true });
    } catch {
      void 0;
    }
  }
  tempDirs.length = 0;
});

describe("omg_get_session_health", () => {
  test("returns all required fields: status, tool_count, risk_level", async () => {
    const projectDir = makeTempProject();
    tempDirs.push(projectDir);

    const provider = SessionHealthProvider.create(projectDir, 5);
    const tool = createSessionHealthTool(provider);

    expect(tool.name).toBe("omg_get_session_health");

    const result = (await tool.handler({})) as Record<string, unknown>;

    expect(result.status).toBeDefined();
    expect(result.tool_count).toBeDefined();
    expect(result.risk_level).toBeDefined();

    expect(typeof result.status).toBe("string");
    expect(typeof result.tool_count).toBe("number");
    expect(typeof result.risk_level).toBe("string");
  });

  test("returns healthy status when no defense state exists", async () => {
    const projectDir = makeTempProject();
    tempDirs.push(projectDir);

    const provider = SessionHealthProvider.create(projectDir, 3);
    const tool = createSessionHealthTool(provider);

    const result = (await tool.handler({})) as Record<string, unknown>;

    expect(result.status).toBe("healthy");
    expect(result.risk_level).toBe("low");
    expect(result.tool_count).toBe(3);
  });

  test("includes session_id when provided", async () => {
    const projectDir = makeTempProject();
    tempDirs.push(projectDir);

    const provider = SessionHealthProvider.create(projectDir);
    const tool = createSessionHealthTool(provider);

    const result = (await tool.handler({ session_id: "ses-123" })) as Record<string, unknown>;

    expect(result.session_id).toBe("ses-123");
  });

  test("omits session_id when not provided", async () => {
    const projectDir = makeTempProject();
    tempDirs.push(projectDir);

    const provider = SessionHealthProvider.create(projectDir);
    const tool = createSessionHealthTool(provider);

    const result = (await tool.handler({})) as Record<string, unknown>;

    expect(result.session_id).toBeUndefined();
  });

  test("reflects critical risk from defense state", async () => {
    const projectDir = makeTempProject();
    tempDirs.push(projectDir);

    const defenseStatePath = join(projectDir, ".omg", "state", "defense_state.json");
    writeFileSync(
      defenseStatePath,
      JSON.stringify({
        riskLevel: "critical",
        injectionHits: 5,
        contaminationScore: 0.9,
        overthinkingScore: 0,
        prematureFixerScore: 0,
        actions: [],
        reasons: [],
        updatedAt: new Date().toISOString(),
      }),
    );

    const provider = SessionHealthProvider.create(projectDir, 10);
    const tool = createSessionHealthTool(provider);

    const result = (await tool.handler({})) as Record<string, unknown>;

    expect(result.status).toBe("critical");
    expect(result.risk_level).toBe("critical");
    expect(result.tool_count).toBe(10);
  });

  test("reflects degraded status for high risk", async () => {
    const projectDir = makeTempProject();
    tempDirs.push(projectDir);

    const defenseStatePath = join(projectDir, ".omg", "state", "defense_state.json");
    writeFileSync(
      defenseStatePath,
      JSON.stringify({
        riskLevel: "high",
        injectionHits: 1,
        contaminationScore: 0.5,
        overthinkingScore: 0,
        prematureFixerScore: 0,
        actions: [],
        reasons: [],
        updatedAt: new Date().toISOString(),
      }),
    );

    const provider = SessionHealthProvider.create(projectDir, 7);
    const tool = createSessionHealthTool(provider);

    const result = (await tool.handler({})) as Record<string, unknown>;

    expect(result.status).toBe("degraded");
    expect(result.risk_level).toBe("high");
  });
});

describe("omg_guide_assert", () => {
  test("passes for clean assertion", async () => {
    const tool = createGuideAssertTool();
    expect(tool.name).toBe("omg_guide_assert");

    const result = (await tool.handler({
      assertion: "All tests pass and coverage is above 80%",
    })) as Record<string, unknown>;

    expect(result.passed).toBe(true);
    expect(result.message).toBe("Assertion accepted");
  });

  test("fails for assertion containing TODO marker", async () => {
    const tool = createGuideAssertTool();

    const result = (await tool.handler({
      assertion: "Feature is complete TODO: add error handling",
    })) as Record<string, unknown>;

    expect(result.passed).toBe(false);
    expect(typeof result.message).toBe("string");
  });

  test("fails for assertion containing FIXME", async () => {
    const tool = createGuideAssertTool();

    const result = (await tool.handler({
      assertion: "Implementation is done FIXME later",
    })) as Record<string, unknown>;

    expect(result.passed).toBe(false);
  });

  test("fails when evidence is empty object", async () => {
    const tool = createGuideAssertTool();

    const result = (await tool.handler({
      assertion: "Build succeeded",
      evidence: {},
    })) as Record<string, unknown>;

    expect(result.passed).toBe(false);
    expect(result.message).toContain("empty");
  });

  test("passes when evidence has keys", async () => {
    const tool = createGuideAssertTool();

    const result = (await tool.handler({
      assertion: "Build succeeded",
      evidence: { build_log: "ok", test_count: 42 },
    })) as Record<string, unknown>;

    expect(result.passed).toBe(true);
  });

  test("throws on missing assertion", async () => {
    const tool = createGuideAssertTool();

    await expect(tool.handler({})).rejects.toThrow("assertion must be a non-empty string");
  });

  test("throws on empty assertion", async () => {
    const tool = createGuideAssertTool();

    await expect(tool.handler({ assertion: "  " })).rejects.toThrow("assertion must be a non-empty string");
  });

  test("throws on invalid evidence type", async () => {
    const tool = createGuideAssertTool();

    await expect(
      tool.handler({ assertion: "valid", evidence: "not-an-object" }),
    ).rejects.toThrow("evidence must be an object");
  });
});
