import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve, relative } from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "..");

export function ensureDir(path: string): void {
  mkdirSync(path, { recursive: true });
}

export function ensureParent(path: string): void {
  ensureDir(dirname(path));
}

export function readJsonFile<T>(path: string, fallback: T): T {
  try {
    if (!existsSync(path)) {
      return fallback;
    }
    const raw = readFileSync(path, "utf8");
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function writeJsonFile(path: string, value: unknown): void {
  ensureParent(path);
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

export function printJson(value: unknown): void {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}

export function ensureProjectDir(): string {
  return process.env.CLAUDE_PROJECT_DIR || process.cwd();
}

export function nowIso(): string {
  return new Date().toISOString();
}

export function nowRunId(): string {
  return nowIso().replace(/[-:.]/g, "").replace("T", "T").replace("Z", "Z");
}

export function relativeToProject(projectDir: string, path: string): string {
  return relative(projectDir, path) || ".";
}

type IdeaShape = {
  goal: string;
  constraints: string[];
  acceptance: string[];
  risk: Record<string, string[]>;
  evidence_required: Record<string, string[]>;
};

export function parseSimpleIdeaYaml(path: string): IdeaShape {
  const idea: IdeaShape = {
    goal: "",
    constraints: [],
    acceptance: [],
    risk: { security: [], performance: [], compatibility: [] },
    evidence_required: { tests: [], security_scans: [], reproducibility: [], artifacts: [] }
  };

  let section = "";
  let subsection = "";
  const raw = readFileSync(path, "utf8");
  for (const line of raw.split(/\r?\n/)) {
    const stripped = line.trim();
    if (!stripped || stripped.startsWith("#")) {
      continue;
    }
    if (stripped.startsWith("goal:")) {
      idea.goal = stripped.slice(5).trim().replace(/^["']|["']$/g, "");
      section = "";
      subsection = "";
      continue;
    }
    if (["constraints:", "acceptance:", "risk:", "evidence_required:"].includes(stripped)) {
      section = stripped.slice(0, -1);
      subsection = "";
      continue;
    }
    if ((section === "risk" || section === "evidence_required") && stripped.endsWith(":") && !stripped.startsWith("- ")) {
      subsection = stripped.slice(0, -1);
      continue;
    }
    if (stripped.startsWith("- ")) {
      const value = stripped.slice(2).trim().replace(/^["']|["']$/g, "");
      if (section === "constraints" || section === "acceptance") {
        (idea[section] as string[]).push(value);
      } else if ((section === "risk" || section === "evidence_required") && subsection) {
        idea[section][subsection] ??= [];
        idea[section][subsection].push(value);
      }
    }
  }
  return idea;
}

export function unique<T>(items: T[]): T[] {
  return [...new Set(items)];
}

export function normalizeWhitespace(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}
