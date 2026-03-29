import { describe, expect, test } from "bun:test";
import { InstallPlanner } from "./planner.js";

describe("InstallPlanner", () => {
  test("detectHosts returns canonical booleans", async () => {
    const planner = InstallPlanner.create({
      probePath: async (command: string): Promise<boolean> => ["claude", "codex"].includes(command),
      cwd: () => "/workspace/project",
      homeDir: () => "/home/tester",
    });

    const hosts = await planner.detectHosts();

    expect(hosts).toEqual({
      claude: true,
      codex: true,
      gemini: false,
      kimi: false,
    });
    expect(typeof hosts.claude).toBe("boolean");
    expect(typeof hosts.codex).toBe("boolean");
    expect(typeof hosts.gemini).toBe("boolean");
    expect(typeof hosts.kimi).toBe("boolean");
  });

  test("planInstall returns preview for detected hosts", () => {
    const planner = InstallPlanner.create({
      cwd: () => "/workspace/project",
      homeDir: () => "/home/tester",
      probePath: async (): Promise<boolean> => false,
    });

    const plan = planner.planInstall({
      claude: true,
      codex: false,
      gemini: true,
      kimi: true,
    });

    expect(plan.steps.map((step) => step.host)).toEqual(["claude", "gemini", "kimi"]);
    expect(plan.preview).toEqual([
      "- claude: /workspace/project/.mcp.json",
      "- gemini: /home/tester/.gemini/settings.json",
      "- kimi: /home/tester/.kimi/mcp.json",
    ]);
  });
});
