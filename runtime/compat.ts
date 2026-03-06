import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { ensureDir, ensureParent, nowIso, ROOT_DIR } from "./common.ts";
import { dispatchTeam, executeCcgMode } from "./team_router.ts";

export const DEFAULT_CONTRACT_SNAPSHOT_PATH = "runtime/omg_compat_contract_snapshot.json";
export const DEFAULT_GAP_REPORT_PATH = ".omg/evidence/omg-compat-gap.json";

type CompatContract = {
  skill: string;
  route: string;
  maturity: string;
  [key: string]: unknown;
};

function snapshotPath(): string {
  return resolve(ROOT_DIR, DEFAULT_CONTRACT_SNAPSHOT_PATH);
}

function loadContracts(): CompatContract[] {
  const raw = JSON.parse(readFileSync(snapshotPath(), "utf8")) as { contracts?: CompatContract[] };
  return Array.isArray(raw.contracts) ? raw.contracts : [];
}

const CONTRACTS = loadContracts();
const CONTRACT_MAP = new Map(CONTRACTS.map((contract) => [contract.skill.toLowerCase(), contract]));
const ALIAS_MAP = new Map<string, string>([
  ["team", "omg-teams"],
  ["teams", "omg-teams"],
  ["release", "release"],
  ["ship", "release"],
  ["plan", "plan"],
  ["ccg", "ccg"]
]);

function normalizeSkill(skill: string): string {
  const lowered = skill.trim().toLowerCase();
  return ALIAS_MAP.get(lowered) || lowered;
}

export function listCompatSkills(): string[] {
  return CONTRACTS.map((contract) => contract.skill).sort();
}

export function listCompatSkillContracts(): CompatContract[] {
  return [...CONTRACTS].sort((left, right) => left.skill.localeCompare(right.skill));
}

export function getCompatSkillContract(skill: string): CompatContract | null {
  return CONTRACT_MAP.get(normalizeSkill(skill)) || null;
}

export function buildContractSnapshotPayload(options: { includeGeneratedAt?: boolean } = {}) {
  const payload: Record<string, unknown> = {
    schema: "OmgCompatContractSnapshot",
    contract_version: "2.0.0",
    count: CONTRACTS.length,
    contracts: listCompatSkillContracts()
  };
  if (options.includeGeneratedAt) {
    payload.generated_at = nowIso();
  }
  return payload;
}

export function buildCompatGapReport(projectDir?: string) {
  const maturity_counts: Record<string, number> = {};
  for (const contract of CONTRACTS) {
    const maturity = String(contract.maturity || "unknown");
    maturity_counts[maturity] = (maturity_counts[maturity] || 0) + 1;
  }
  return {
    schema: "OmgCompatGapReport",
    generated_at: nowIso(),
    project_dir: projectDir || "",
    total_skills: CONTRACTS.length,
    maturity_counts,
    missing_routes: CONTRACTS.filter((contract) => !contract.route).map((contract) => contract.skill)
  };
}

function writeArtifact(path: string, payload: unknown): string {
  ensureParent(path);
  writeFileSync(path, `${typeof payload === "string" ? payload : JSON.stringify(payload, null, 2)}\n`, "utf8");
  return path;
}

export function dispatchCompatSkill(input: {
  skill: string;
  problem?: string;
  context?: string;
  files?: string[];
  expected_outcome?: string;
  project_dir?: string;
}) {
  const normalized = normalizeSkill(input.skill);
  const contract = getCompatSkillContract(normalized);
  if (!contract) {
    return {
      schema: "OmgCompatResult",
      status: "error",
      message: `Unknown skill: ${input.skill}`,
      supported_skills: listCompatSkills()
    };
  }

  const route = String(contract.route || "");
  if (route === "teams") {
    return {
      schema: "OmgCompatResult",
      status: "ok",
      skill: normalized,
      routed_to: "teams",
      route,
      result: dispatchTeam({
        target: "auto",
        problem: input.problem || `compat route for ${normalized}`,
        context: input.context || "",
        files: input.files || [],
        expected_outcome: input.expected_outcome || ""
      })
    };
  }

  if (route === "ccg") {
    return {
      schema: "OmgCompatResult",
      status: "ok",
      skill: normalized,
      routed_to: "ccg",
      route,
      result: executeCcgMode({
        problem: input.problem || `compat route for ${normalized}`,
        context: input.context || "",
        files: input.files || []
      })
    };
  }

  if (route === "runtime_ship" || normalized === "release") {
    const projectDir = input.project_dir || process.cwd();
    const artifact = join(projectDir, ".omg", "evidence", "release-draft.md");
    writeArtifact(
      artifact,
      `# OMG Release Draft\n\n- Skill: \`${normalized}\`\n- Problem: ${input.problem || "n/a"}\n- Generated: ${nowIso()}\n`
    );
    return {
      schema: "OmgCompatResult",
      status: "ok",
      skill: normalized,
      routed_to: "runtime_ship",
      route,
      artifacts: [artifact]
    };
  }

  const projectDir = input.project_dir || process.cwd();
  const artifact = join(projectDir, ".omg", "evidence", `compat-${normalized}.json`);
  writeArtifact(artifact, {
    schema: "OmgCompatArtifact",
    generated_at: nowIso(),
    skill: normalized,
    route,
    problem: input.problem || ""
  });
  return {
    schema: "OmgCompatResult",
    status: "ok",
    skill: normalized,
    routed_to: route || "native",
    route,
    artifacts: [artifact]
  };
}
