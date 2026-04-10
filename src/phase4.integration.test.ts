import { describe, expect, test } from "bun:test";
import { DOMAIN_PACKS, validatePackStructure } from "./domain-packs/validator";
import { detectPlatform } from "./platform/compat";
import { GovernanceGraphRuntime } from "./governance/graph";

function mockFs(existingPaths: string[]): { exists: (p: string) => boolean } {
  const pathSet = new Set(existingPaths);
  return { exists: (p: string) => pathSet.has(p) };
}

describe("phase4 integration", () => {
  test("provider-registry", () => {
    expect(DOMAIN_PACKS).toHaveLength(7);
    expect(DOMAIN_PACKS).toEqual([
      "saas",
      "landing",
      "ecommerce",
      "api",
      "bot",
      "admin",
      "cli",
    ]);
  });

  test("platform-compat", () => {
    const valid = ["linux", "darwin", "win32", "unknown"];
    expect(valid).toContain(detectPlatform());
  });

  test("soft-block-mode", () => {
    const runtime = new GovernanceGraphRuntime("/tmp/omg-phase4-integration");
    expect(runtime.getEnforcementMode()).toBe("soft-block");
  });

  test("validator-pipeline", () => {
    const result = validatePackStructure(
      "saas",
      "/project",
      mockFs([
        "/project/package.json",
        "/project/src/index.ts",
        "/project/src",
      ]),
    );

    expect(result).toHaveProperty("pack");
    expect(result).toHaveProperty("structureValid");
    expect(result).toHaveProperty("hasPackageJson");
    expect(result).toHaveProperty("hasEntryPoint");
    expect(result).toHaveProperty("qualityScore");
    expect(result).toHaveProperty("issues");
    expect(result.pack).toBe("saas");
    expect(result.structureValid).toBe(true);
  });
});
