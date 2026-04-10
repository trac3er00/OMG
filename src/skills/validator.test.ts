import { describe, expect, test } from "bun:test";
import { resolve } from "node:path";

import {
  findImplementation,
  loadRegistry,
  scanOmgDescriptors,
  validateSkills,
} from "./validator.js";

const PROJECT_ROOT = resolve(import.meta.dir, "../..");

describe("loadRegistry", () => {
  test("loads skills from registry/skills.json", () => {
    const skills = loadRegistry(PROJECT_ROOT);
    expect(skills.length).toBeGreaterThan(0);
    expect(skills[0]).toHaveProperty("id");
    expect(skills[0]).toHaveProperty("name");
    expect(skills[0]).toHaveProperty("provider");
  });

  test("returns empty array for missing registry", () => {
    const skills = loadRegistry("/nonexistent/path");
    expect(skills).toEqual([]);
  });
});

describe("scanOmgDescriptors", () => {
  test("finds OMG skill directories with descriptors", () => {
    const descriptors = scanOmgDescriptors(PROJECT_ROOT);
    expect(descriptors.size).toBeGreaterThan(0);

    const controlPlane = descriptors.get("control-plane");
    expect(controlPlane).toBeDefined();
    expect(controlPlane!.hasSkillMd).toBe(true);
    expect(controlPlane!.hasOpenaiYaml).toBe(true);
    expect(controlPlane!.name).toBe("omg-control-plane");
  });

  test("returns empty map for missing directory", () => {
    const descriptors = scanOmgDescriptors("/nonexistent/path");
    expect(descriptors.size).toBe(0);
  });

  test("parses frontmatter from SKILL.md", () => {
    const descriptors = scanOmgDescriptors(PROJECT_ROOT);
    const claimJudge = descriptors.get("claim-judge");
    expect(claimJudge).toBeDefined();
    expect(claimJudge!.name).toBe("omg-claim-judge");
    expect(claimJudge!.description.length).toBeGreaterThan(0);
  });
});

describe("findImplementation", () => {
  test("finds known implementation for claim-judge", () => {
    const result = findImplementation(PROJECT_ROOT, "claim-judge");
    expect(result.impl).toBe("src/verification/claim-judge.ts");
    expect(result.test).toBe("src/verification/claim-judge.test.ts");
  });

  test("finds known implementation for proof-gate", () => {
    const result = findImplementation(PROJECT_ROOT, "proof-gate");
    expect(result.impl).toBe("src/verification/proof-gate.ts");
    expect(result.test).toBe("src/verification/proof-gate.test.ts");
  });

  test("finds known implementation for test-intent-lock", () => {
    const result = findImplementation(PROJECT_ROOT, "test-intent-lock");
    expect(result.impl).toBe("src/verification/test-intent-lock.ts");
    expect(result.test).toBe("src/verification/test-intent-lock.test.ts");
  });

  test("returns empty for unknown skill without matching files", () => {
    const result = findImplementation(PROJECT_ROOT, "nonexistent-skill");
    expect(result.impl).toBeUndefined();
    expect(result.test).toBeUndefined();
  });
});

describe("validateSkills", () => {
  test("produces report with correct schema", async () => {
    const report = await validateSkills(PROJECT_ROOT, { runTests: false });
    expect(report.schema).toBe("SkillValidationReport");
    expect(report.timestamp).toBeTruthy();
    expect(report.total).toBeGreaterThan(0);
    expect(report.validated + report.stub + report.missing).toBe(report.total);
  });

  test("includes both OMG and registry skills", async () => {
    const report = await validateSkills(PROJECT_ROOT, { runTests: false });
    const omgSkills = report.details.filter((d) => d.source === "omg");
    const registrySkills = report.details.filter(
      (d) => d.source === "registry",
    );
    expect(omgSkills.length).toBeGreaterThan(0);
    expect(registrySkills.length).toBeGreaterThan(0);
  });

  test("marks skills with descriptor+impl+test as validated", async () => {
    const report = await validateSkills(PROJECT_ROOT, { runTests: false });
    const claimJudge = report.details.find((d) => d.id === "omg/claim-judge");
    expect(claimJudge).toBeDefined();
    expect(claimJudge!.status).toBe("validated");
    expect(claimJudge!.descriptor.found).toBe(true);
    expect(claimJudge!.implementation.found).toBe(true);
    expect(claimJudge!.tests.found).toBe(true);
  });

  test("marks descriptor-only skills as stub", async () => {
    const report = await validateSkills(PROJECT_ROOT, { runTests: false });
    const stubs = report.details.filter((d) => d.status === "stub");
    expect(stubs.length).toBeGreaterThan(0);
    for (const stub of stubs) {
      expect(stub.descriptor.found).toBe(true);
    }
  });

  test("has at least 3 validated skills (no test execution)", async () => {
    const report = await validateSkills(PROJECT_ROOT, { runTests: false });
    expect(report.validated).toBeGreaterThanOrEqual(3);
  });

  test("all entries have required fields", async () => {
    const report = await validateSkills(PROJECT_ROOT, { runTests: false });
    for (const entry of report.details) {
      expect(entry.id).toBeTruthy();
      expect(entry.name).toBeTruthy();
      expect(["registry", "omg", "both"]).toContain(entry.source);
      expect(["validated", "stub", "missing"]).toContain(entry.status);
      expect(typeof entry.descriptor.found).toBe("boolean");
      expect(typeof entry.implementation.found).toBe("boolean");
      expect(typeof entry.tests.found).toBe("boolean");
    }
  });

  test("returns empty for nonexistent project root", async () => {
    const report = await validateSkills("/nonexistent/path", {
      runTests: false,
    });
    expect(report.total).toBe(0);
  });
});
