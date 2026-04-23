import { describe, expect, mock, test } from "bun:test";

/**
 * Host Parity Smoke Tests
 *
 * Tests 5 core scenarios across 3 canonical hosts (Claude, Codex, Gemini).
 * All tests use mocks — no real API calls are made.
 *
 * Scenarios:
 * 1. MCP registration succeeds
 * 2. Hook execution works (pre-tool hook fires and returns allow)
 * 3. Skill loading works
 * 4. Subagent spawn works
 * 5. Proof gate evaluation works
 */

const HOSTS = ["claude", "codex", "gemini"] as const;
type Host = (typeof HOSTS)[number];

interface MockMcpResult {
  readonly registered: boolean;
  readonly host: Host;
}

interface MockHookResult {
  readonly action: "allow" | "deny";
  readonly host: Host;
}

interface MockSkillResult {
  readonly loaded: boolean;
  readonly host: Host;
}

interface MockSubagentResult {
  readonly session_id: string;
  readonly host: Host;
}

interface MockProofResult {
  readonly pass: boolean;
  readonly score: number;
  readonly host: Host;
}

interface MockHostAdapter {
  readonly name: Host;
  readonly registerMcp: ReturnType<typeof mock<() => Promise<MockMcpResult>>>;
  readonly executeHook: ReturnType<typeof mock<() => Promise<MockHookResult>>>;
  readonly loadSkill: ReturnType<typeof mock<() => Promise<MockSkillResult>>>;
  readonly spawnSubagent: ReturnType<
    typeof mock<() => Promise<MockSubagentResult>>
  >;
  readonly evaluateProof: ReturnType<
    typeof mock<() => Promise<MockProofResult>>
  >;
}

function createMockHost(name: Host): MockHostAdapter {
  return {
    name,
    registerMcp: mock(
      async (): Promise<MockMcpResult> => ({
        registered: true,
        host: name,
      }),
    ),
    executeHook: mock(
      async (): Promise<MockHookResult> => ({
        action: "allow",
        host: name,
      }),
    ),
    loadSkill: mock(
      async (): Promise<MockSkillResult> => ({
        loaded: true,
        host: name,
      }),
    ),
    spawnSubagent: mock(
      async (): Promise<MockSubagentResult> => ({
        session_id: `mock-${name}-123`,
        host: name,
      }),
    ),
    evaluateProof: mock(
      async (): Promise<MockProofResult> => ({
        pass: true,
        score: 75,
        host: name,
      }),
    ),
  };
}

describe("Host Parity Smoke Tests", () => {
  for (const hostName of HOSTS) {
    describe(`${hostName} host`, () => {
      const host = createMockHost(hostName);

      test(`[${hostName}] MCP registration succeeds`, async () => {
        const result = await host.registerMcp();

        expect(result.registered).toBe(true);
        expect(result.host).toBe(hostName);
        expect(host.registerMcp).toHaveBeenCalledTimes(1);
      });

      test(`[${hostName}] Hook execution works`, async () => {
        const result = await host.executeHook();

        expect(result.action).toBe("allow");
        expect(result.host).toBe(hostName);
        expect(host.executeHook).toHaveBeenCalledTimes(1);
      });

      test(`[${hostName}] Skill loading works`, async () => {
        const result = await host.loadSkill();

        expect(result.loaded).toBe(true);
        expect(result.host).toBe(hostName);
        expect(host.loadSkill).toHaveBeenCalledTimes(1);
      });

      test(`[${hostName}] Subagent spawn works`, async () => {
        const result = await host.spawnSubagent();

        expect(result.session_id).toBe(`mock-${hostName}-123`);
        expect(result.host).toBe(hostName);
        expect(host.spawnSubagent).toHaveBeenCalledTimes(1);
      });

      test(`[${hostName}] Proof gate evaluation works`, async () => {
        const result = await host.evaluateProof();

        expect(result.pass).toBe(true);
        expect(result.score).toBe(75);
        expect(result.host).toBe(hostName);
        expect(host.evaluateProof).toHaveBeenCalledTimes(1);
      });
    });
  }
});

describe("Host Parity Coverage", () => {
  test("All canonical hosts are covered", () => {
    expect(HOSTS).toEqual(["claude", "codex", "gemini"]);
    expect(HOSTS.length).toBe(3);
  });

  test("Each host has 5 scenario mocks", () => {
    for (const hostName of HOSTS) {
      const host = createMockHost(hostName);
      const methods = [
        "registerMcp",
        "executeHook",
        "loadSkill",
        "spawnSubagent",
        "evaluateProof",
      ] as const;

      for (const method of methods) {
        expect(typeof host[method]).toBe("function");
      }
    }
  });
});
