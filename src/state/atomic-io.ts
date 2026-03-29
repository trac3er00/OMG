import { appendFileSync, existsSync, mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { randomBytes } from "node:crypto";
import { dirname, join } from "node:path";

export function atomicWrite(filePath: string, content: string | Buffer): void {
  const dir = dirname(filePath);
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }

  const tmpPath = join(dir, `${randomBytes(8).toString("hex")}.tmp`);

  try {
    writeFileSync(tmpPath, content, { flush: true });
    renameSync(tmpPath, filePath);
  } catch (error) {
    try {
      unlinkSync(tmpPath);
    } catch {
      void 0;
    }
    throw error;
  }
}

export function readJsonFile<T = unknown>(filePath: string): T | undefined {
  if (!existsSync(filePath)) {
    return undefined;
  }
  const content = readFileSync(filePath, "utf8");
  return JSON.parse(content) as T;
}

export function atomicWriteJson(filePath: string, data: unknown): void {
  atomicWrite(filePath, JSON.stringify(data, null, 2));
}

export function readJsonLines<T = unknown>(filePath: string): T[] {
  if (!existsSync(filePath)) {
    return [];
  }

  const content = readFileSync(filePath, "utf8");
  const rows: T[] = [];
  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) {
      continue;
    }
    try {
      rows.push(JSON.parse(trimmed) as T);
    } catch {
      void 0;
    }
  }
  return rows;
}

export function appendJsonLine(filePath: string, data: unknown): void {
  const dir = dirname(filePath);
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
  appendFileSync(filePath, `${JSON.stringify(data)}\n`, "utf8");
}
