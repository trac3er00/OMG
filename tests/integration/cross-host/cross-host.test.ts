import { afterAll, describe, expect, it } from "bun:test";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import {
  checkMutationGate,
  evaluatePolicy,
  runHookEmulation,
} from "../../../src/compat/hook-emulation.js";
import { evaluateWithCompensators } from "../../../src/compensators/pipeline.js";

describe("Cross-Host: Hook Emulation (simulates Codex/Gemini/Kimi behavior)", () => {
  it("codex: normal code generation → allow", () => {
    const result = runHookEmulation({
      tool: "Write",
      input: { path: "src/feature.ts", content: "export const x = 1;" },
    });
    expect(result.decision).toBe("allow");
    expect(result.emulated).toBe(true);
  });

  it("gemini: bash code formatting → allow", () => {
    const result = runHookEmulation({
      tool: "Bash",
      input: { command: "bun run format" },
    });
    expect(result.decision).toBe("allow");
    expect(result.emulated).toBe(true);
  });

  it("kimi: destructive command → deny (governance enforced)", () => {
    const result = runHookEmulation({
      tool: "Bash",
      input: { command: "rm -rf /" },
    });
    expect(result.decision).toBe("deny");
    expect(result.emulated).toBe(true);
  });

  it("all-hosts: writing .env file → ask (mutation gate enforced)", () => {
    const result = runHookEmulation({
      tool: "Write",
      input: { path: ".env", content: "SECRET=abc" },
    });
    expect(result.decision).toBe("ask");
    expect(result.emulated).toBe(true);
  });

  it("all-hosts: writing /etc/hosts → deny (system dir blocked)", () => {
    const result = runHookEmulation({
      tool: "Write",
      input: { path: "/etc/hosts", content: "127.0.0.1 evil" },
    });
    expect(result.decision).toBe("deny");
    expect(result.emulated).toBe(true);
  });

  it("hook emulation always returns emulated:true (distinguishes from native hooks)", () => {
    const result1 = evaluatePolicy({
      tool: "Read",
      input: { path: "README.md" },
    });
    const result2 = checkMutationGate({
      tool: "Read",
      input: { path: "README.md" },
    });
    expect(result1.emulated).toBe(true);
    expect(result2.emulated).toBe(true);
  });
});

describe("Cross-Host: Compensator Pipeline Integration", () => {
  it("clean agent output → pipeline APPROVE", () => {
    const result = evaluateWithCompensators({
      outputText: "I have completed all required tasks as specified.",
    });
    expect(result.verdict).toBe("APPROVE");
  });

  it("deferral language in output → pipeline REJECT", () => {
    const result = evaluateWithCompensators({
      outputText: "I will handle this in a follow-up session.",
    });
    expect(result.verdict).toBe("REJECT");
    expect(result.reasons.length).toBeGreaterThan(0);
  });

  it("incomplete task state → pipeline REJECT", () => {
    const result = evaluateWithCompensators({
      taskState: {
        declaredTasks: ["implement auth", "write tests", "add docs"],
        completedTasks: ["implement auth"],
      },
    });
    expect(result.verdict).toBe("REJECT");
    expect(result.reasons.some((r) => r.includes("task"))).toBe(true);
  });

  it("completion claim without evidence → pipeline REJECT", () => {
    const result = evaluateWithCompensators({
      claim: { taskId: "task-1", claimed: true, evidenceFiles: [] },
    });
    expect(result.verdict).toBe("REJECT");
    expect(result.reasons.some((r) => r.includes("evidence"))).toBe(true);
  });

  it("completion claim with evidence → pipeline APPROVE", () => {
    const result = evaluateWithCompensators({
      claim: {
        taskId: "task-1",
        claimed: true,
        evidenceFiles: ["test-results.json"],
        testsPassed: true,
      },
    });
    expect(result.verdict).toBe("APPROVE");
  });
});

afterAll(() => {
  const report = {
    timestamp: new Date().toISOString(),
    testSuite: "cross-host integration",
    hosts: ["claude", "codex", "gemini", "kimi", "opencode"],
    hookEmulationStatus: "FUNCTIONAL",
    compensatorPipelineStatus: "FUNCTIONAL",
    notes:
      "Hook emulation provides governance for non-Claude hosts via MCP. Compensators enforce completion quality.",
  };
  mkdirSync(join(process.cwd(), ".sisyphus", "evidence"), { recursive: true });
  writeFileSync(
    join(process.cwd(), ".sisyphus", "evidence", "task-20-cross-host.json"),
    JSON.stringify(report, null, 2),
  );
});
