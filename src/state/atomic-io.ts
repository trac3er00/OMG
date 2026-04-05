import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { mkdir, rename, unlink, writeFile } from "node:fs/promises";
import { randomBytes } from "node:crypto";
import { dirname, join } from "node:path";

const retryableErrorCodes = new Set(["EBUSY", "EPERM", "EACCES"]);

function sleepSync(ms: number): void {
  const start = Date.now();
  while (Date.now() - start < ms) {
    void 0;
  }
}

function retrySync(fn: () => void, maxAttempts = 3): void {
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      fn();
      return;
    } catch (error) {
      const code =
        error instanceof Error ? (error as { code?: unknown }).code : undefined;
      const shouldRetry =
        typeof code === "string" &&
        retryableErrorCodes.has(code) &&
        attempt < maxAttempts;
      if (!shouldRetry) {
        throw error;
      }
      sleepSync(50 * 2 ** (attempt - 1));
    }
  }
}

function createUniqueTmpPath(dir: string): string {
  for (let attempt = 0; attempt < 16; attempt += 1) {
    const tmpPath = join(dir, `${randomBytes(8).toString("hex")}.tmp`);
    if (!existsSync(tmpPath)) {
      return tmpPath;
    }
  }

  throw new Error(`Unable to generate a unique temp path in ${dir}`);
}

export function atomicWrite(filePath: string, content: string | Buffer): void {
  const dir = dirname(filePath);
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }

  retrySync(() => {
    const tmpPath = createUniqueTmpPath(dir);

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
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function writeFileAtomic(
  filePath: string,
  content: string | Buffer,
): Promise<void> {
  const dir = dirname(filePath);
  await mkdir(dir, { recursive: true });

  const maxAttempts = 3;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    const tmpPath = createUniqueTmpPath(dir);
    try {
      await writeFile(tmpPath, content, { flush: true });
      await rename(tmpPath, filePath);
      return;
    } catch (error) {
      try {
        await unlink(tmpPath);
      } catch {
        void 0;
      }
      const code =
        error instanceof Error ? (error as { code?: unknown }).code : undefined;
      const shouldRetry =
        typeof code === "string" &&
        retryableErrorCodes.has(code) &&
        attempt < maxAttempts;
      if (!shouldRetry) {
        throw error;
      }
      await sleep(50 * 2 ** (attempt - 1));
    }
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
