#!/usr/bin/env bun

/**
 * Pack Validation Script
 * Validates all packs in packs/goals/ and packs/domains/
 * Exit codes: 0 = all valid, 1 = any failures
 */

import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join, basename } from "node:path";
import yaml from "js-yaml";

interface PackValidation {
  path: string;
  name: string;
  valid: boolean;
  errors: string[];
}

interface ValidationResult {
  total: number;
  valid: number;
  invalid: number;
  packs: PackValidation[];
}

const GOALS_DIR = "./packs/goals";
const DOMAINS_DIR = "./packs/domains";
const UNIFIED_DIR = "./packs";
const REQUIRED_FIELDS = ["name", "description"];

function loadYamlFile(filePath: string): unknown {
  const content = readFileSync(filePath, "utf-8");
  return yaml.load(content);
}

function validatePack(packPath: string): PackValidation {
  const errors: string[] = [];

  if (!existsSync(packPath)) {
    return {
      path: packPath,
      name: basename(packPath),
      valid: false,
      errors: [`File not found: ${packPath}`],
    };
  }

  let pack: Record<string, unknown>;
  try {
    pack = loadYamlFile(packPath) as Record<string, unknown>;
  } catch (err) {
    return {
      path: packPath,
      name: basename(packPath),
      valid: false,
      errors: [
        `YAML parse error: ${err instanceof Error ? err.message : String(err)}`,
      ],
    };
  }

  // Check required fields
  for (const field of REQUIRED_FIELDS) {
    if (!pack[field]) {
      errors.push(`Missing required field: ${field}`);
    }
  }

  // Name must be string
  if (typeof pack.name !== "string") {
    errors.push(`Field 'name' must be a string`);
  }

  // Description must be string
  if (typeof pack.description !== "string") {
    errors.push(`Field 'description' must be a string`);
  }

  return {
    path: packPath,
    name: typeof pack.name === "string" ? pack.name : "unknown",
    valid: errors.length === 0,
    errors,
  };
}

function getPackFiles(dir: string): string[] {
  if (!existsSync(dir)) {
    return [];
  }

  const entries = readdirSync(dir, { withFileTypes: true });
  const packFiles: string[] = [];

  for (const entry of entries) {
    if (entry.isDirectory()) {
      const packPath = join(dir, entry.name, "pack.yaml");
      if (existsSync(packPath)) {
        packFiles.push(packPath);
      }
    }
  }

  return packFiles;
}

// Excluded directories in unified packs/ that are not packs themselves
const EXCLUDED_UNIFIED_DIRS = [
  "goals",
  "domains",
  "api-twin",
  "browser",
  "music-omr",
  "vision",
];

function getUnifiedPackFiles(dir: string): string[] {
  if (!existsSync(dir)) {
    return [];
  }

  const entries = readdirSync(dir, { withFileTypes: true });
  const packFiles: string[] = [];

  for (const entry of entries) {
    if (entry.isDirectory() && !EXCLUDED_UNIFIED_DIRS.includes(entry.name)) {
      const packPath = join(dir, entry.name, "pack.yaml");
      if (existsSync(packPath)) {
        packFiles.push(packPath);
      }
    }
  }

  return packFiles;
}

function validateAllPacks(): ValidationResult {
  const goalPacks = getPackFiles(GOALS_DIR);
  const domainPacks = getPackFiles(DOMAINS_DIR);
  const unifiedPacks = getUnifiedPackFiles(UNIFIED_DIR);

  const allPacks = [...goalPacks, ...domainPacks, ...unifiedPacks];
  const results = allPacks.map((packPath) => validatePack(packPath));

  return {
    total: allPacks.length,
    valid: results.filter((r) => r.valid).length,
    invalid: results.filter((r) => !r.valid).length,
    packs: results,
  };
}

function printResults(result: ValidationResult): void {
  console.log("=".repeat(60));
  console.log("PACK VALIDATION RESULTS");
  console.log("=".repeat(60));

  const goalCount = result.packs.filter((p) =>
    p.path.includes("/goals/"),
  ).length;
  const domainCount = result.packs.filter((p) =>
    p.path.includes("/domains/"),
  ).length;
  const unifiedCount = result.packs.filter(
    (p) => !p.path.includes("/goals/") && !p.path.includes("/domains/"),
  ).length;

  console.log(`\nTotal packs checked: ${result.total}`);
  console.log(`  - Goals: ${goalCount}`);
  console.log(`  - Domains: ${domainCount}`);
  console.log(`  - Unified: ${unifiedCount}`);
  console.log(`Valid: ${result.valid} ✓`);
  console.log(`Invalid: ${result.invalid} ✗`);

  if (result.invalid > 0) {
    console.log("\n" + "-".repeat(60));
    console.log("FAILED PACKS:");
    console.log("-".repeat(60));

    for (const pack of result.packs.filter((p) => !p.valid)) {
      console.log(`\n❌ ${pack.path}`);
      for (const error of pack.errors) {
        console.log(`   - ${error}`);
      }
    }
  }

  console.log("\n" + "-".repeat(60));
  console.log("VALID PACKS:");
  console.log("-".repeat(60));

  for (const pack of result.packs.filter((p) => p.valid)) {
    console.log(`✓ ${pack.path}`);
  }

  console.log("\n" + "=".repeat(60));
}

function main(): void {
  const result = validateAllPacks();
  printResults(result);

  if (result.invalid > 0) {
    console.log(
      `\n⚠️  Validation FAILED: ${result.invalid} pack(s) have errors`,
    );
    process.exit(1);
  } else {
    console.log(`\n✅ All packs validated successfully!`);
    process.exit(0);
  }
}

main();
