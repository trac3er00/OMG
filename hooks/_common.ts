import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

export function resolveProjectDir(): string {
  return process.env.CLAUDE_PROJECT_DIR || process.cwd();
}

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
    return JSON.parse(readFileSync(path, "utf8")) as T;
  } catch {
    return fallback;
  }
}

export function writeJsonFile(path: string, value: unknown): void {
  ensureParent(path);
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

export async function readStdin(): Promise<string> {
  return await Bun.stdin.text();
}

export async function readJsonFromStdin<T>(fallback: T): Promise<T> {
  try {
    const text = await readStdin();
    if (!text.trim()) {
      return fallback;
    }
    return JSON.parse(text) as T;
  } catch {
    return fallback;
  }
}

export function getFeatureFlag(name: string, defaultValue = true): boolean {
  const key = `OMG_${name.replace(/[^A-Za-z0-9]+/g, "_").toUpperCase()}_ENABLED`;
  const raw = process.env[key];
  if (raw == null || raw === "") {
    return defaultValue;
  }
  return /^(1|true|yes|on)$/i.test(raw);
}

export function ledgerPath(projectDir: string, filename: string): string {
  return join(projectDir, ".omg", "state", "ledger", filename);
}

export function noopHookMain(): void {
  process.exit(0);
}
