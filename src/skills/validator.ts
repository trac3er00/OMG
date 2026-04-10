#!/usr/bin/env bun

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const DEFAULT_ROOT = resolve(__dirname, "../..");

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SkillDescriptor {
  readonly name: string;
  readonly description: string;
  readonly hasSkillMd: boolean;
  readonly hasOpenaiYaml: boolean;
}

export interface SkillValidationEntry {
  readonly id: string;
  readonly name: string;
  readonly source: "registry" | "omg" | "both";
  readonly status: "validated" | "stub" | "missing";
  readonly descriptor: { readonly found: boolean; readonly path: string };
  readonly implementation: {
    readonly found: boolean;
    readonly path?: string;
  };
  readonly tests: {
    readonly found: boolean;
    readonly path?: string;
    readonly passed?: boolean;
  };
}

export interface ValidationReport {
  readonly schema: "SkillValidationReport";
  readonly timestamp: string;
  readonly total: number;
  readonly validated: number;
  readonly stub: number;
  readonly missing: number;
  readonly details: readonly SkillValidationEntry[];
}

// ---------------------------------------------------------------------------
// Known skill-to-implementation mappings
// ---------------------------------------------------------------------------

const IMPLEMENTATION_MAP: Readonly<
  Record<string, { readonly impl: string; readonly test?: string }>
> = {
  "claim-judge": {
    impl: "src/verification/claim-judge.ts",
    test: "src/verification/claim-judge.test.ts",
  },
  "proof-gate": {
    impl: "src/verification/proof-gate.ts",
    test: "src/verification/proof-gate.test.ts",
  },
  "test-intent-lock": {
    impl: "src/verification/test-intent-lock.ts",
    test: "src/verification/test-intent-lock.test.ts",
  },
  "control-plane": {
    impl: "src/mcp/server.ts",
  },
  "eval-gate": {
    impl: "src/eval/runner.ts",
  },
  "delta-classifier": {
    impl: "src/runtime/contract-compiler/validation.ts",
  },
};

// ---------------------------------------------------------------------------
// Registry loading
// ---------------------------------------------------------------------------

interface RegistrySkillEntry {
  readonly id: string;
  readonly name: string;
  readonly description: string;
  readonly category: string;
  readonly provider: string;
  readonly path: string;
  readonly enabled: boolean;
}

export function loadRegistry(root: string): readonly RegistrySkillEntry[] {
  const registryPath = join(root, "registry/skills.json");
  if (!existsSync(registryPath)) return [];
  const raw = readFileSync(registryPath, "utf8");
  const parsed: { skills?: RegistrySkillEntry[] } = JSON.parse(raw);
  return parsed.skills ?? [];
}

// ---------------------------------------------------------------------------
// OMG descriptor scanning
// ---------------------------------------------------------------------------

export function scanOmgDescriptors(root: string): Map<string, SkillDescriptor> {
  const skillsDir = join(root, ".agents/skills/omg");
  if (!existsSync(skillsDir)) return new Map();

  const entries = readdirSync(skillsDir, { withFileTypes: true });
  const descriptors = new Map<string, SkillDescriptor>();

  for (const entry of entries) {
    if (!entry.isDirectory()) continue;

    const skillPath = join(skillsDir, entry.name);
    const hasSkillMd = existsSync(join(skillPath, "SKILL.md"));
    const hasOpenaiYaml = existsSync(join(skillPath, "openai.yaml"));

    let name = entry.name;
    let description = "";

    if (hasSkillMd) {
      const contents = readFileSync(join(skillPath, "SKILL.md"), "utf8");
      const nameMatch = contents.match(/^name:\s*(.+)$/m);
      const descMatch = contents.match(/^description:\s*"?(.*?)"?\s*$/m);
      if (nameMatch?.[1]) name = nameMatch[1].trim();
      if (descMatch?.[1]) description = descMatch[1].trim();
    }

    descriptors.set(entry.name, {
      name,
      description,
      hasSkillMd,
      hasOpenaiYaml,
    });
  }

  return descriptors;
}

// ---------------------------------------------------------------------------
// Implementation discovery
// ---------------------------------------------------------------------------

export function findImplementation(
  root: string,
  skillName: string,
): { impl?: string; test?: string } {
  const known = IMPLEMENTATION_MAP[skillName];
  if (known) {
    const implExists = existsSync(join(root, known.impl));
    const testPath = known.test;
    const testExists = testPath ? existsSync(join(root, testPath)) : false;
    const result: { impl?: string; test?: string } = {};
    if (implExists) result.impl = known.impl;
    if (testExists && testPath) result.test = testPath;
    return result;
  }

  const searchDirs = [
    "src/verification",
    "src/orchestration",
    "src/mcp",
    "src/runtime",
    "src/eval",
    "src/cli/commands",
    "src/governance",
  ];

  for (const dir of searchDirs) {
    const dirPath = join(root, dir);
    if (!existsSync(dirPath)) continue;

    const files = readdirSync(dirPath);
    const normalized = skillName.replace(/-/g, "_");
    const implFile = files.find(
      (f) => f === `${skillName}.ts` || f === `${normalized}.ts`,
    );
    const testFile = files.find(
      (f) => f === `${skillName}.test.ts` || f === `${normalized}.test.ts`,
    );

    if (implFile) {
      const result: { impl?: string; test?: string } = {
        impl: join(dir, implFile),
      };
      if (testFile) result.test = join(dir, testFile);
      return result;
    }
  }

  return {};
}

// ---------------------------------------------------------------------------
// Test runner
// ---------------------------------------------------------------------------

async function runTestFile(root: string, testPath: string): Promise<boolean> {
  try {
    const bunPath = join(process.env.HOME ?? "", ".bun/bin/bun");
    const bin = existsSync(bunPath) ? bunPath : "bun";

    const proc = Bun.spawn([bin, "test", testPath], {
      cwd: root,
      stdout: "pipe",
      stderr: "pipe",
      env: {
        ...process.env,
        PATH: `${process.env.HOME}/.bun/bin:${process.env.PATH}`,
      },
    });

    const exitCode = await proc.exited;
    return exitCode === 0;
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Core validator
// ---------------------------------------------------------------------------

export async function validateSkills(
  root: string = DEFAULT_ROOT,
  options: { runTests?: boolean } = {},
): Promise<ValidationReport> {
  const { runTests = true } = options;

  const registrySkills = loadRegistry(root);
  const omgDescriptors = scanOmgDescriptors(root);

  const details: SkillValidationEntry[] = [];
  const processedIds = new Set<string>();

  for (const [dirName, descriptor] of omgDescriptors) {
    const { impl, test } = findImplementation(root, dirName);

    let testPassed: boolean | undefined;
    if (runTests && test) {
      testPassed = await runTestFile(root, test);
    }

    const hasDescriptor = descriptor.hasSkillMd || descriptor.hasOpenaiYaml;
    const hasImpl = Boolean(impl);
    const hasTest = Boolean(test);

    let status: "validated" | "stub" | "missing";
    if (hasDescriptor && hasImpl && hasTest) {
      status = runTests ? (testPassed ? "validated" : "stub") : "validated";
    } else if (hasDescriptor) {
      status = "stub";
    } else {
      status = "missing";
    }

    const id = `omg/${dirName}`;
    processedIds.add(id);

    const entry: SkillValidationEntry = {
      id,
      name: descriptor.name,
      source: "omg",
      status,
      descriptor: {
        found: hasDescriptor,
        path: `.agents/skills/omg/${dirName}`,
      },
      implementation: { found: hasImpl, ...(impl ? { path: impl } : {}) },
      tests: {
        found: hasTest,
        ...(test ? { path: test } : {}),
        ...(testPassed !== undefined ? { passed: testPassed } : {}),
      },
    };
    details.push(entry);
  }

  for (const skill of registrySkills) {
    const registryId = skill.id;
    if (processedIds.has(registryId)) continue;

    const descriptorPath = join(root, skill.path);
    const hasDescriptor = existsSync(descriptorPath);

    details.push({
      id: registryId,
      name: skill.name,
      source: "registry",
      status: hasDescriptor ? "stub" : "missing",
      descriptor: { found: hasDescriptor, path: skill.path },
      implementation: { found: false },
      tests: { found: false },
    });

    processedIds.add(registryId);
  }

  details.sort((a, b) => a.id.localeCompare(b.id));

  const validated = details.filter((d) => d.status === "validated").length;
  const stub = details.filter((d) => d.status === "stub").length;
  const missing = details.filter((d) => d.status === "missing").length;

  return {
    schema: "SkillValidationReport",
    timestamp: new Date().toISOString(),
    total: details.length,
    validated,
    stub,
    missing,
    details,
  };
}

// ---------------------------------------------------------------------------
// CLI entry point
// ---------------------------------------------------------------------------

if (import.meta.main) {
  const skipTests = process.argv.includes("--no-tests");
  const report = await validateSkills(DEFAULT_ROOT, {
    runTests: !skipTests,
  });
  console.log(JSON.stringify(report, null, 2));
}
