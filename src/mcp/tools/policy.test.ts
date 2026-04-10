import { describe, expect, test } from "bun:test";
import { evaluatePolicy } from "../../security/policy-engine.js";
import { checkMutationAllowed } from "../../security/mutation-gate.js";
import {
  scoreTrustChange,
  getTrustDecision,
} from "../../security/trust-review.js";
import type { ToolFabricResult } from "../../governance/tool-fabric.js";
import {
  createPolicyEvaluateTool,
  createMutationGateTool,
  createToolFabricRequestTool,
  createTrustReviewTool,
} from "./policy.js";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

describe("omg_policy_evaluate", () => {
  const tool = createPolicyEvaluateTool({ evaluatePolicy });

  test("has correct registration shape", () => {
    expect(tool.name).toBe("omg_policy_evaluate");
    expect(tool.description).toBeTruthy();
    expect(tool.inputSchema).toBeDefined();
    expect(typeof tool.handler).toBe("function");
  });

  test("allows innocuous bash command", async () => {
    const result = await tool.handler({
      tool: "Bash",
      input: { command: "ls" },
    });
    expect(isRecord(result)).toBe(true);
    if (isRecord(result)) {
      expect(result.action).toBe("allow");
      expect(typeof result.reason).toBe("string");
    }
  });

  test("blocks destructive bash command", async () => {
    const result = await tool.handler({
      tool: "Bash",
      input: { command: "rm -rf /" },
    });
    expect(isRecord(result)).toBe(true);
    if (isRecord(result)) {
      expect(result.action).toBe("block");
      expect(typeof result.reason).toBe("string");
    }
  });

  test("blocks secret file access", async () => {
    const result = await tool.handler({
      tool: "Read",
      input: { file_path: ".env" },
    });
    expect(isRecord(result)).toBe(true);
    if (isRecord(result)) {
      expect(result.action).toBe("block");
    }
  });

  test("allows safe file access", async () => {
    const result = await tool.handler({
      tool: "Read",
      input: { file_path: "src/index.ts" },
    });
    expect(isRecord(result)).toBe(true);
    if (isRecord(result)) {
      expect(result.action).toBe("allow");
    }
  });
});

describe("omg_mutation_gate", () => {
  const tool = createMutationGateTool({
    checkMutationAllowed,
    projectDir: "/tmp/omg-test",
  });

  test("has correct registration shape", () => {
    expect(tool.name).toBe("omg_mutation_gate");
    expect(tool.description).toBeTruthy();
    expect(tool.inputSchema).toBeDefined();
    expect(typeof tool.handler).toBe("function");
  });

  test("allows non-mutation-capable tool", async () => {
    const result = await tool.handler({ tool: "Read" });
    expect(isRecord(result)).toBe(true);
    if (isRecord(result)) {
      expect(result.allowed).toBe(true);
    }
  });

  test("blocks dangerous bash mutation", async () => {
    const result = await tool.handler({
      tool: "Bash",
      command: "rm -rf /",
    });
    expect(isRecord(result)).toBe(true);
    if (isRecord(result)) {
      expect(result.allowed).toBe(false);
      expect(typeof result.reason).toBe("string");
    }
  });

  test("deny result is a hard block rather than a warning", async () => {
    const result = await tool.handler({
      tool: "Write",
      file_path: ".env",
      run_id: "hard-block-check",
    });

    expect(isRecord(result)).toBe(true);
    if (isRecord(result)) {
      expect(result.allowed).toBe(false);
      expect(result.reason).toContain("Blocked:");
    }
  });

  test("blocks mutation to critical file", async () => {
    const result = await tool.handler({
      tool: "Write",
      file_path: ".env",
    });
    expect(isRecord(result)).toBe(true);
    if (isRecord(result)) {
      expect(result.allowed).toBe(false);
    }
  });

  test("allows safe write", async () => {
    const result = await tool.handler({
      tool: "Write",
      file_path: "src/index.ts",
      run_id: "test-run",
    });
    expect(isRecord(result)).toBe(true);
    if (isRecord(result)) {
      expect(result.allowed).toBe(true);
    }
  });
});

describe("omg_tool_fabric_request", () => {
  function mockEvaluateRequest(
    tool: string,
    _args: Record<string, unknown>,
    lane?: string,
  ): Promise<ToolFabricResult> {
    const effectiveLane = lane ?? "default";
    const timestamp = new Date().toISOString();

    if (tool === "BlockedTool") {
      return Promise.resolve({
        action: "deny",
        reason: `Tool '${tool}' not allowed in lane '${effectiveLane}'`,
        lane: effectiveLane,
        tool,
        timestamp,
      });
    }
    return Promise.resolve({
      action: "allow",
      reason: `Tool '${tool}' allowed in lane '${effectiveLane}'`,
      lane: effectiveLane,
      tool,
      timestamp,
    });
  }

  const tool = createToolFabricRequestTool({
    evaluateRequest: mockEvaluateRequest,
  });

  test("has correct registration shape", () => {
    expect(tool.name).toBe("omg_tool_fabric_request");
    expect(tool.description).toBeTruthy();
    expect(tool.inputSchema).toBeDefined();
    expect(typeof tool.handler).toBe("function");
  });

  test("allows tool in default lane", async () => {
    const result = await tool.handler({ tool: "Bash" });
    expect(isRecord(result)).toBe(true);
    if (isRecord(result)) {
      expect(result.allowed).toBe(true);
      expect(result.lane).toBe("default");
    }
  });

  test("denies blocked tool", async () => {
    const result = await tool.handler({
      tool: "BlockedTool",
      lane: "restricted",
    });
    expect(isRecord(result)).toBe(true);
    if (isRecord(result)) {
      expect(result.allowed).toBe(false);
      expect(result.lane).toBe("restricted");
    }
  });

  test("default lane passthrough remains allowed without explicit approval lane", async () => {
    const result = await tool.handler({ tool: "Bash" });
    expect(isRecord(result)).toBe(true);
    if (isRecord(result)) {
      expect(result.allowed).toBe(true);
      expect(result.lane).toBe("default");
    }
  });
});

describe("omg_trust_review", () => {
  const tool = createTrustReviewTool({ scoreTrustChange, getTrustDecision });

  test("has correct registration shape", () => {
    expect(tool.name).toBe("omg_trust_review");
    expect(tool.description).toBeTruthy();
    expect(tool.inputSchema).toBeDefined();
    expect(typeof tool.handler).toBe("function");
  });

  test("allows low-risk config changes", async () => {
    const result = await tool.handler({
      config_changes: { description_changed: 1 },
    });
    expect(isRecord(result)).toBe(true);
    if (isRecord(result)) {
      expect(result.decision).toBe("allow");
      expect(typeof result.score).toBe("number");
      expect(result.score).toBeLessThan(45);
    }
  });

  test("denies high-risk config changes", async () => {
    const result = await tool.handler({
      config_changes: { permission_scope_expanded: 3, env_permission_added: 3 },
    });
    expect(isRecord(result)).toBe(true);
    if (isRecord(result)) {
      expect(result.decision).toBe("deny");
      expect(typeof result.score).toBe("number");
      expect(result.score).toBeGreaterThanOrEqual(80);
    }
  });

  test("asks for medium-risk config changes", async () => {
    const result = await tool.handler({
      config_changes: { mcp_server_added: 1 },
    });
    expect(isRecord(result)).toBe(true);
    if (isRecord(result)) {
      expect(result.decision).toBe("ask");
      expect(typeof result.score).toBe("number");
    }
  });
});
