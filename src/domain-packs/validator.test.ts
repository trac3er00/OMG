import { describe, test, expect } from "bun:test";
import {
  DOMAIN_PACKS,
  PACK_REQUIREMENTS,
  validatePackStructure,
  runValidationPipeline,
  type DomainPack,
} from "./validator";

function mockFs(existingPaths: string[]): { exists: (p: string) => boolean } {
  const pathSet = new Set(existingPaths);
  return { exists: (p: string) => pathSet.has(p) };
}

describe("validatePackStructure", () => {
  test("valid pack — all required files present → structureValid=true, score=100", () => {
    const fs = mockFs([
      "/project/package.json",
      "/project/src/index.ts",
      "/project/src",
    ]);

    const result = validatePackStructure("saas", "/project", fs);

    expect(result.structureValid).toBe(true);
    expect(result.qualityScore).toBe(100);
    expect(result.hasPackageJson).toBe(true);
    expect(result.hasEntryPoint).toBe(true);
    expect(result.issues).toHaveLength(0);
    expect(result.pack).toBe("saas");
  });

  test("missing files → issues listed, score reduced", () => {
    const fs = mockFs(["/project/package.json"]);

    const result = validatePackStructure("saas", "/project", fs);

    expect(result.structureValid).toBe(false);
    expect(result.hasPackageJson).toBe(true);
    expect(result.issues.length).toBeGreaterThan(0);
    expect(result.issues).toContain("Missing required file: src/index.ts");
    expect(result.issues).toContain("Missing required directory: src");
    expect(result.qualityScore).toBeLessThan(100);
  });

  test("quality threshold — score >= 80 for valid pack", () => {
    const fs = mockFs(["/project/package.json", "/project/index.html"]);

    const result = validatePackStructure("landing", "/project", fs);

    expect(result.qualityScore).toBeGreaterThanOrEqual(80);
    expect(result.structureValid).toBe(true);
  });

  test("quality score floors at 0 for heavily broken packs", () => {
    const fs = mockFs([]);

    const result = validatePackStructure("api", "/project", fs);

    expect(result.qualityScore).toBeGreaterThanOrEqual(0);
    expect(result.structureValid).toBe(false);
  });

  test("landing pack has entry point via index.html", () => {
    const fs = mockFs(["/project/package.json", "/project/index.html"]);

    const result = validatePackStructure("landing", "/project", fs);

    expect(result.hasEntryPoint).toBe(true);
  });

  test("bot pack detects missing entry point file correctly", () => {
    const fs = mockFs(["/project/package.json", "/project/src"]);

    const result = validatePackStructure("bot", "/project", fs);

    expect(result.structureValid).toBe(false);
    expect(result.issues).toContain("Missing required file: src/bot.ts");
  });
});

describe("PACK_REQUIREMENTS", () => {
  test("all 7 domain packs have requirements defined", () => {
    expect(DOMAIN_PACKS).toHaveLength(7);

    for (const pack of DOMAIN_PACKS) {
      const reqs = PACK_REQUIREMENTS[pack];
      expect(reqs).toBeDefined();
      expect(reqs.requiredFiles).toBeInstanceOf(Array);
      expect(reqs.requiredDirs).toBeInstanceOf(Array);
      expect(reqs.minQualityScore).toBe(80);
    }
  });

  test("every pack requires package.json", () => {
    for (const pack of DOMAIN_PACKS) {
      expect(PACK_REQUIREMENTS[pack].requiredFiles).toContain("package.json");
    }
  });
});

describe("runValidationPipeline", () => {
  test("processes multiple packs", () => {
    const fs = mockFs([
      "/saas/package.json",
      "/saas/src/index.ts",
      "/saas/src",
      "/api/package.json",
      "/api/src/server.ts",
      "/api/src",
    ]);

    const results = runValidationPipeline(
      { saas: "/saas", api: "/api" } as Partial<Record<DomainPack, string>>,
      fs,
    );

    expect(results).toHaveLength(2);
    expect(results[0].pack).toBe("saas");
    expect(results[0].structureValid).toBe(true);
    expect(results[1].pack).toBe("api");
    expect(results[1].structureValid).toBe(true);
  });

  test("skips packs without project paths", () => {
    const fs = mockFs(["/cli/package.json", "/cli/src/cli.ts", "/cli/src"]);

    const results = runValidationPipeline(
      { cli: "/cli" } as Partial<Record<DomainPack, string>>,
      fs,
    );

    expect(results).toHaveLength(1);
    expect(results[0].pack).toBe("cli");
  });

  test("returns empty array for empty input", () => {
    const fs = mockFs([]);
    const results = runValidationPipeline({}, fs);
    expect(results).toHaveLength(0);
  });
});
