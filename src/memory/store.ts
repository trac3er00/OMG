import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const DEFAULT_MEMORY_FILE = ".omg/memory/memory.json";
const MISSING = Symbol("missing-memory-value");

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizeKey(key: string): string[] {
  return key
    .split(".")
    .map((segment) => segment.trim())
    .filter(Boolean);
}

function readJsonFile(filePath: string): Record<string, unknown> {
  if (!existsSync(filePath)) {
    return {};
  }

  try {
    const raw = readFileSync(filePath, "utf8");
    const parsed = JSON.parse(raw) as unknown;
    return isPlainObject(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function writeJsonFile(
  filePath: string,
  value: Record<string, unknown>,
): void {
  mkdirSync(dirname(filePath), { recursive: true });
  writeFileSync(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function setNestedValue(
  target: Record<string, unknown>,
  key: string,
  value: unknown,
): void {
  const segments = normalizeKey(key);
  if (!segments.length) {
    throw new Error("Memory key must not be empty.");
  }

  let cursor: Record<string, unknown> = target;
  for (const segment of segments.slice(0, -1)) {
    const next = cursor[segment];
    if (!isPlainObject(next)) {
      cursor[segment] = {};
    }
    cursor = cursor[segment] as Record<string, unknown>;
  }

  cursor[segments[segments.length - 1] as string] = value;
}

function getNestedValue(target: Record<string, unknown>, key: string): unknown {
  const segments = normalizeKey(key);
  if (!segments.length) {
    return MISSING;
  }

  let cursor: unknown = target;
  for (const segment of segments) {
    if (!isPlainObject(cursor) || !(segment in cursor)) {
      return MISSING;
    }
    cursor = cursor[segment];
  }

  return cursor;
}

export class MemoryStore {
  readonly filePath: string;

  constructor(baseDir = process.cwd()) {
    this.filePath = resolve(baseDir, DEFAULT_MEMORY_FILE);
  }

  set(key: string, value: unknown): void {
    const data = this.list();
    setNestedValue(data, key, value);
    writeJsonFile(this.filePath, data);
  }

  get(key: string): unknown {
    const value = getNestedValue(this.list(), key);
    return value === MISSING ? undefined : value;
  }

  list(): Record<string, unknown> {
    return readJsonFile(this.filePath);
  }
}
