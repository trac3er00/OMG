/**
 * Skill system inventory simulation suite.
 *
 * Validates registry/skills.json structure, provider coverage,
 * Kimi skill presence, and skill file existence on disk.
 * Complements skill-coverage.ts (which tests runtime tool exercise)
 * by focusing on static registry integrity and file-system layout.
 */

import { readFileSync, existsSync } from "node:fs";
import { join, resolve } from "node:path";

// ── Types ────────────────────────────────────────────────────────

export interface SkillEntry {
  readonly id: string;
  readonly name: string;
  readonly description: string;
  readonly category: string;
  readonly provider: string;
  readonly path: string;
  readonly keywords: readonly string[];
  readonly version: string;
  readonly enabled: boolean;
}

export interface RegistryFile {
  readonly schema_version: string;
  readonly registry_version: string;
  readonly skills: readonly SkillEntry[];
}

export interface SkillSystemCheck {
  readonly name: string;
  readonly passed: boolean;
  readonly detail: string;
}

export interface SkillSystemResult {
  readonly totalSkills: number;
  readonly totalProviders: number;
  readonly kimiSkillsFound: number;
  readonly allKimiSkillsPresent: boolean;
  readonly checks: readonly SkillSystemCheck[];
  readonly passed: boolean;
  readonly duration_ms: number;
}

// ── Constants ────────────────────────────────────────────────────

const EXPECTED_PROVIDERS = [
  "universal",
  "claude",
  "codex",
  "opencode",
  "gemini",
  "kimi",
] as const;

const KIMI_SKILL_IDS = [
  "@kimi/long-context",
  "@kimi/web-search",
  "@kimi/code-generation",
  "@kimi/moonshot",
] as const;

const REQUIRED_FIELDS: ReadonlyArray<keyof SkillEntry> = [
  "id",
  "name",
  "description",
  "provider",
  "path",
];

// ── Helpers ──────────────────────────────────────────────────────

function findRoot(): string {
  // Walk up to find registry/skills.json
  let dir = resolve(process.cwd());
  for (let i = 0; i < 5; i++) {
    if (existsSync(join(dir, "registry", "skills.json"))) return dir;
    dir = resolve(dir, "..");
  }
  return process.cwd();
}

function loadRegistry(root: string): RegistryFile | null {
  const registryPath = join(root, "registry", "skills.json");
  if (!existsSync(registryPath)) return null;
  const raw = readFileSync(registryPath, "utf-8");
  return JSON.parse(raw) as RegistryFile;
}

// ── Suite ────────────────────────────────────────────────────────

export async function runSkillSystemSuite(): Promise<SkillSystemResult> {
  const start = performance.now();
  const root = findRoot();
  const checks: SkillSystemCheck[] = [];

  // 1. Registry exists
  const registryPath = join(root, "registry", "skills.json");
  const registryExists = existsSync(registryPath);
  checks.push({
    name: "registry_exists",
    passed: registryExists,
    detail: registryExists
      ? `Found at ${registryPath}`
      : "registry/skills.json not found",
  });

  if (!registryExists) {
    return {
      totalSkills: 0,
      totalProviders: 0,
      kimiSkillsFound: 0,
      allKimiSkillsPresent: false,
      checks,
      passed: false,
      duration_ms: Math.round(performance.now() - start),
    };
  }

  const registry = loadRegistry(root)!;
  const skills = registry.skills;

  // 2. Schema version present
  checks.push({
    name: "schema_version",
    passed: !!registry.schema_version,
    detail: `schema_version=${registry.schema_version}`,
  });

  // 3. Skills count
  checks.push({
    name: "skills_count_minimum",
    passed: skills.length >= 20,
    detail: `${skills.length} skills found (min 20)`,
  });

  // 4. All required fields present
  const incompleteSkills: string[] = [];
  for (const skill of skills) {
    const missing = REQUIRED_FIELDS.filter(
      (f) => !(f in skill) || !skill[f],
    );
    if (missing.length > 0) {
      incompleteSkills.push(`${skill.id}: missing ${missing.join(",")}`);
    }
  }
  checks.push({
    name: "required_fields",
    passed: incompleteSkills.length === 0,
    detail:
      incompleteSkills.length === 0
        ? "All skills have required fields"
        : `Incomplete: ${incompleteSkills.join("; ")}`,
  });

  // 5. Unique IDs
  const ids = skills.map((s) => s.id);
  const uniqueIds = new Set(ids);
  checks.push({
    name: "unique_ids",
    passed: ids.length === uniqueIds.size,
    detail:
      ids.length === uniqueIds.size
        ? `${ids.length} unique IDs`
        : `Duplicates detected: ${ids.length} total, ${uniqueIds.size} unique`,
  });

  // 6. All expected providers present
  const providers = new Set(skills.map((s) => s.provider));
  const missingProviders = EXPECTED_PROVIDERS.filter((p) => !providers.has(p));
  checks.push({
    name: "all_providers_present",
    passed: missingProviders.length === 0,
    detail:
      missingProviders.length === 0
        ? `All ${EXPECTED_PROVIDERS.length} providers present`
        : `Missing providers: ${missingProviders.join(", ")}`,
  });

  // 7. Kimi skills in registry
  const kimiSkills = skills.filter((s) => s.id.startsWith("@kimi/"));
  const kimiIds = new Set(kimiSkills.map((s) => s.id));
  const missingKimi = KIMI_SKILL_IDS.filter((id) => !kimiIds.has(id));
  const allKimiPresent = missingKimi.length === 0;
  checks.push({
    name: "kimi_skills_registered",
    passed: allKimiPresent,
    detail: allKimiPresent
      ? `All ${KIMI_SKILL_IDS.length} Kimi skills found`
      : `Missing Kimi skills: ${missingKimi.join(", ")}`,
  });

  // 8. Provider SKILL.md files exist
  const missingSkillMd: string[] = [];
  for (const provider of EXPECTED_PROVIDERS) {
    const mdPath = join(root, "skills", provider, "SKILL.md");
    if (!existsSync(mdPath)) {
      missingSkillMd.push(provider);
    }
  }
  checks.push({
    name: "provider_skill_md_files",
    passed: missingSkillMd.length === 0,
    detail:
      missingSkillMd.length === 0
        ? "All provider SKILL.md files present"
        : `Missing SKILL.md for: ${missingSkillMd.join(", ")}`,
  });

  // 9. Kimi SKILL.md references all skills
  const kimiMdPath = join(root, "skills", "kimi", "SKILL.md");
  let kimiMdRefsAll = false;
  if (existsSync(kimiMdPath)) {
    const content = readFileSync(kimiMdPath, "utf-8");
    const shortNames = KIMI_SKILL_IDS.map((id) => id.split("/")[1]);
    kimiMdRefsAll = shortNames.every((name) => content.includes(name));
  }
  checks.push({
    name: "kimi_skill_md_complete",
    passed: kimiMdRefsAll,
    detail: kimiMdRefsAll
      ? "Kimi SKILL.md references all 4 skills"
      : "Kimi SKILL.md missing skill references",
  });

  // 10. Paths follow convention
  const badPaths = skills.filter((s) => !s.path.startsWith("skills/"));
  checks.push({
    name: "path_convention",
    passed: badPaths.length === 0,
    detail:
      badPaths.length === 0
        ? "All paths follow skills/ convention"
        : `Bad paths: ${badPaths.map((s) => `${s.id}=${s.path}`).join(", ")}`,
  });

  // 11. Runtime skill_registry.py exists
  const runtimePath = join(root, "runtime", "skill_registry.py");
  checks.push({
    name: "runtime_module_exists",
    passed: existsSync(runtimePath),
    detail: existsSync(runtimePath)
      ? "runtime/skill_registry.py present"
      : "runtime/skill_registry.py not found",
  });

  const allPassed = checks.every((c) => c.passed);

  return {
    totalSkills: skills.length,
    totalProviders: providers.size,
    kimiSkillsFound: kimiSkills.length,
    allKimiSkillsPresent: allKimiPresent,
    checks,
    passed: allPassed,
    duration_ms: Math.round(performance.now() - start),
  };
}

// ── CLI entry ────────────────────────────────────────────────────

if (import.meta.main) {
  const result = await runSkillSystemSuite();
  console.log(
    `\nSkill System Suite: ${result.passed ? "PASS" : "FAIL"} (${result.duration_ms}ms)`,
  );
  console.log(`  Skills: ${result.totalSkills}`);
  console.log(`  Providers: ${result.totalProviders}`);
  console.log(`  Kimi skills: ${result.kimiSkillsFound}/4`);
  console.log(`\nChecks:`);
  for (const check of result.checks) {
    const icon = check.passed ? "✓" : "✗";
    console.log(`  ${icon} ${check.name}: ${check.detail}`);
  }
  process.exit(result.passed ? 0 : 1);
}
