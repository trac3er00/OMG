import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { join } from "node:path";

const DEFAULT_MAX_ENTRIES = 100;
const DEFAULT_CACHE_DIR = ".omg/cache";
const ORDER_FILE = "_lru_order.json";

export interface SessionCacheConfig {
  readonly cacheDir?: string;
  readonly maxEntries?: number;
}

export interface CacheWriteResult {
  readonly hash: string;
  readonly filePath: string;
  readonly written: boolean;
}

export function computeHash(state: unknown): string {
  const serialized = typeof state === "string" ? state : JSON.stringify(state);
  return createHash("sha256").update(serialized).digest("hex");
}

export class SessionCache {
  private readonly cacheDir: string;
  private readonly maxEntries: number;

  constructor(config: SessionCacheConfig = {}) {
    this.cacheDir = config.cacheDir ?? DEFAULT_CACHE_DIR;
    this.maxEntries = config.maxEntries ?? DEFAULT_MAX_ENTRIES;
  }

  private ensureDir(): void {
    if (!existsSync(this.cacheDir)) {
      mkdirSync(this.cacheDir, { recursive: true });
    }
  }

  private hashPath(hash: string): string {
    return join(this.cacheDir, `${hash}.tmp`);
  }

  private orderPath(): string {
    return join(this.cacheDir, ORDER_FILE);
  }

  private readOrder(): string[] {
    const path = this.orderPath();
    if (!existsSync(path)) {
      return [];
    }
    try {
      return JSON.parse(readFileSync(path, "utf8")) as string[];
    } catch {
      return [];
    }
  }

  private writeOrder(order: string[]): void {
    this.ensureDir();
    writeFileSync(this.orderPath(), JSON.stringify(order), "utf8");
  }

  private touchOrder(hash: string): void {
    const order = this.readOrder().filter((h) => h !== hash);
    order.push(hash);
    this.writeOrder(order);
  }

  private removeFromOrder(hash: string): void {
    const order = this.readOrder().filter((h) => h !== hash);
    this.writeOrder(order);
  }

  write(state: unknown): CacheWriteResult {
    this.ensureDir();

    const hash = computeHash(state);
    const filePath = this.hashPath(hash);

    if (existsSync(filePath)) {
      this.touchOrder(hash);
      return { hash, filePath, written: false };
    }

    const serialized =
      typeof state === "string" ? state : JSON.stringify(state);
    writeFileSync(filePath, serialized, "utf8");
    this.touchOrder(hash);
    this.evict();

    return { hash, filePath, written: true };
  }

  read(hash: string): unknown | null {
    const filePath = this.hashPath(hash);
    if (!existsSync(filePath)) {
      return null;
    }

    this.touchOrder(hash);
    const content = readFileSync(filePath, "utf8");

    try {
      return JSON.parse(content) as unknown;
    } catch {
      return content;
    }
  }

  has(hash: string): boolean {
    return existsSync(this.hashPath(hash));
  }

  delete(hash: string): boolean {
    const filePath = this.hashPath(hash);
    if (!existsSync(filePath)) {
      return false;
    }
    unlinkSync(filePath);
    this.removeFromOrder(hash);
    return true;
  }

  evict(): number {
    if (!existsSync(this.cacheDir)) {
      return 0;
    }

    const order = this.readOrder();

    if (order.length <= this.maxEntries) {
      return 0;
    }

    const toRemove = order.length - this.maxEntries;
    const evicted = order.splice(0, toRemove);
    let removed = 0;

    for (const hash of evicted) {
      try {
        const filePath = this.hashPath(hash);
        if (existsSync(filePath)) {
          unlinkSync(filePath);
        }
        removed++;
      } catch {
        void 0;
      }
    }

    this.writeOrder(order);
    return removed;
  }

  clear(): number {
    if (!existsSync(this.cacheDir)) {
      return 0;
    }

    const entries = readdirSync(this.cacheDir).filter((name) =>
      name.endsWith(".tmp"),
    );
    let removed = 0;

    for (const name of entries) {
      try {
        unlinkSync(join(this.cacheDir, name));
        removed++;
      } catch {
        void 0;
      }
    }

    this.writeOrder([]);
    return removed;
  }

  list(): string[] {
    if (!existsSync(this.cacheDir)) {
      return [];
    }

    return readdirSync(this.cacheDir)
      .filter((name) => name.endsWith(".tmp"))
      .map((name) => name.replace(/\.tmp$/, ""))
      .sort();
  }

  size(): number {
    if (!existsSync(this.cacheDir)) {
      return 0;
    }

    return readdirSync(this.cacheDir).filter((name) => name.endsWith(".tmp"))
      .length;
  }
}
