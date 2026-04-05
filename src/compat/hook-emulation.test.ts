import { describe, expect, it } from "bun:test";

import {
  checkMutationGate,
  evaluatePolicy,
  runHookEmulation,
  type HookEmulationInput,
} from "./hook-emulation";

describe("hook emulation policy", () => {
  it("allows normal Bash command", () => {
    const result = evaluatePolicy({ tool: "Bash", input: { command: "ls -la" } });
    expect(result.decision).toBe("allow");
  });

  it("denies destructive rm -rf / command", () => {
    const result = evaluatePolicy({ tool: "Bash", input: { command: "rm -rf /" } });
    expect(result.decision).toBe("deny");
  });

  it("asks for writing .env file", () => {
    const result = evaluatePolicy({ tool: "Write", input: { path: "/tmp/.env" } });
    expect(result.decision).toBe("ask");
  });

  it("asks for printenv command", () => {
    const result = evaluatePolicy({ tool: "Bash", input: { command: "printenv" } });
    expect(result.decision).toBe("ask");
  });
});

describe("hook emulation mutation gate", () => {
  it("denies writes under /etc", () => {
    const result = checkMutationGate({ tool: "Write", input: { path: "/etc/passwd" } });
    expect(result.decision).toBe("deny");
  });

  it("asks for .git/hooks modification", () => {
    const result = checkMutationGate({
      tool: "Write",
      input: { path: "/repo/.git/hooks/pre-commit" },
    });
    expect(result.decision).toBe("ask");
  });
});

describe("runHookEmulation", () => {
  it("returns the most restrictive decision", () => {
    const input: HookEmulationInput = {
      tool: "Write",
      input: { path: "/etc/secret.env" },
    };

    const result = runHookEmulation(input);
    expect(result.decision).toBe("deny");
  });

  it("always marks results as emulated", () => {
    const results = [
      evaluatePolicy({ tool: "Bash", input: { command: "ls" } }),
      evaluatePolicy({ tool: "Bash", input: { command: "printenv" } }),
      evaluatePolicy({ tool: "Write", input: { path: "/tmp/.env" } }),
      checkMutationGate({ tool: "Write", input: { path: "/etc/passwd" } }),
      checkMutationGate({ tool: "Write", input: { path: "/repo/.git/hooks/pre-commit" } }),
      runHookEmulation({ tool: "Bash", input: { command: "rm -rf /" } }),
    ];

    for (const result of results) {
      expect(result.emulated).toBe(true);
    }
  });
});
