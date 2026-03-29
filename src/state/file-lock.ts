import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { lock } from "proper-lockfile";

export interface LockOptions {
  readonly retries?: number | { retries: number; minTimeout: number; maxTimeout: number };
  readonly stale?: number;
}

export type ReleaseFn = () => Promise<void>;

export async function acquireLock(filePath: string, options: LockOptions = {}): Promise<ReleaseFn> {
  const parent = dirname(filePath);
  if (!existsSync(parent)) {
    mkdirSync(parent, { recursive: true });
  }
  if (!existsSync(filePath)) {
    writeFileSync(filePath, "", "utf8");
  }

  return lock(filePath, {
    retries: options.retries ?? { retries: 3, minTimeout: 50, maxTimeout: 200 },
    stale: options.stale ?? 10_000,
  });
}

export async function withLock<T>(filePath: string, fn: () => Promise<T>, options: LockOptions = {}): Promise<T> {
  const release = await acquireLock(filePath, options);
  try {
    return await fn();
  } finally {
    await release();
  }
}
