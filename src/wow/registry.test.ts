import { describe, expect, test } from "bun:test";
import { flows, getFlow } from "./registry.js";

describe("WowFlow Registry", () => {
  test("has exactly 5 flows", () => {
    expect(Object.keys(flows).length).toBe(5);
  });

  test("each flow has required fields", () => {
    for (const flow of Object.values(flows)) {
      expect(typeof flow.name).toBe("string");
      expect(typeof flow.description).toBe("string");
      expect(typeof flow.expectedArtifact).toBe("string");
      expect(typeof flow.proofFloor).toBe("number");
      expect(typeof flow.timeout).toBe("number");
      expect(Array.isArray(flow.toolAllowlist)).toBe(true);
      expect(typeof flow.deployable).toBe("boolean");
    }
  });

  test('getFlow("landing") returns landing flow', () => {
    const flow = getFlow("landing");
    expect(flow).toBeDefined();
    expect(flow?.name).toBe("landing");
  });

  test('getFlow("unknown") returns undefined', () => {
    expect(getFlow("unknown")).toBeUndefined();
  });

  test("deployable flows: landing, saas, admin (3)", () => {
    const deployable = Object.values(flows).filter((f) => f.deployable);
    expect(deployable.map((f) => f.name).sort()).toEqual([
      "admin",
      "landing",
      "saas",
    ]);
  });

  test("non-deployable: bot, refactor (2)", () => {
    const nonDeployable = Object.values(flows).filter((f) => !f.deployable);
    expect(nonDeployable.map((f) => f.name).sort()).toEqual([
      "bot",
      "refactor",
    ]);
  });
});
