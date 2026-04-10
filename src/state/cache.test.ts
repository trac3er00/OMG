import { describe, expect, test, beforeEach, afterEach } from "bun:test";
import { mkdtempSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { SessionCache, computeHash } from "./cache.js";

function makeTmpCache(maxEntries = 100): {
  cache: SessionCache;
  dir: string;
} {
  const dir = mkdtempSync(join(tmpdir(), "omg-cache-"));
  const cacheDir = join(dir, "cache");
  return { cache: new SessionCache({ cacheDir, maxEntries }), dir };
}

describe("SessionCache", () => {
  let cache: SessionCache;
  let dir: string;

  beforeEach(() => {
    const ctx = makeTmpCache();
    cache = ctx.cache;
    dir = ctx.dir;
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  test("computeHash returns consistent SHA-256 hex", () => {
    const state = { session: "alpha", step: 3 };
    const hash1 = computeHash(state);
    const hash2 = computeHash(state);

    expect(hash1).toBe(hash2);
    expect(hash1).toHaveLength(64);
    expect(/^[a-f0-9]{64}$/.test(hash1)).toBe(true);
  });

  test("computeHash differs for different state", () => {
    const h1 = computeHash({ a: 1 });
    const h2 = computeHash({ a: 2 });

    expect(h1).not.toBe(h2);
  });

  test("write creates .tmp file in cache dir", () => {
    const state = { session: "s1", data: [1, 2, 3] };
    const result = cache.write(state);

    expect(result.written).toBe(true);
    expect(result.hash).toHaveLength(64);
    expect(existsSync(result.filePath)).toBe(true);
    expect(result.filePath.endsWith(".tmp")).toBe(true);
  });

  test("write same state twice is idempotent", () => {
    const state = { id: "dup" };
    const r1 = cache.write(state);
    const r2 = cache.write(state);

    expect(r1.hash).toBe(r2.hash);
    expect(r1.written).toBe(true);
    expect(r2.written).toBe(false);
  });

  test("read returns cached state on hash hit", () => {
    const state = { context: "hello", tokens: 42 };
    const { hash } = cache.write(state);
    const retrieved = cache.read(hash);

    expect(retrieved).toEqual(state);
  });

  test("read returns null on hash miss", () => {
    const result = cache.read(
      "0000000000000000000000000000000000000000000000000000000000000000",
    );

    expect(result).toBeNull();
  });

  test("modified state produces cache miss", () => {
    const stateV1 = { version: 1, data: "original" };
    const stateV2 = { version: 2, data: "modified" };

    const { hash: h1 } = cache.write(stateV1);
    const h2 = computeHash(stateV2);

    expect(h1).not.toBe(h2);
    expect(cache.read(h1)).toEqual(stateV1);
    expect(cache.read(h2)).toBeNull();
  });

  test("has returns true for cached, false for missing", () => {
    const { hash } = cache.write({ key: "exists" });

    expect(cache.has(hash)).toBe(true);
    expect(cache.has("deadbeef".repeat(8))).toBe(false);
  });

  test("delete removes cached entry", () => {
    const { hash } = cache.write({ temp: true });

    expect(cache.delete(hash)).toBe(true);
    expect(cache.read(hash)).toBeNull();
    expect(cache.delete(hash)).toBe(false);
  });

  test("list returns all cached hashes sorted", () => {
    cache.write({ a: 1 });
    cache.write({ b: 2 });
    cache.write({ c: 3 });

    const hashes = cache.list();

    expect(hashes).toHaveLength(3);
    expect(hashes).toEqual([...hashes].sort());
  });

  test("size returns count of cached entries", () => {
    expect(cache.size()).toBe(0);

    cache.write({ x: 1 });
    cache.write({ y: 2 });

    expect(cache.size()).toBe(2);
  });

  test("clear removes all cached entries", () => {
    cache.write({ one: 1 });
    cache.write({ two: 2 });

    const removed = cache.clear();

    expect(removed).toBe(2);
    expect(cache.size()).toBe(0);
  });

  test("string state is cached as-is", () => {
    const state = "raw session string data";
    const { hash } = cache.write(state);
    const retrieved = cache.read(hash);

    expect(retrieved).toBe(state);
  });
});

describe("SessionCache LRU eviction", () => {
  test("evicts oldest entries when exceeding maxEntries", () => {
    const ctx = makeTmpCache(3);
    const cache = ctx.cache;

    try {
      const hashes: string[] = [];

      for (let i = 0; i < 5; i++) {
        const { hash } = cache.write({ entry: i, pad: `v${i}` });
        hashes.push(hash);
      }

      expect(cache.size()).toBe(3);

      expect(cache.has(hashes[3])).toBe(true);
      expect(cache.has(hashes[4])).toBe(true);
    } finally {
      rmSync(ctx.dir, { recursive: true, force: true });
    }
  });

  test("evict on empty cache is no-op", () => {
    const ctx = makeTmpCache(5);

    try {
      expect(ctx.cache.evict()).toBe(0);
    } finally {
      rmSync(ctx.dir, { recursive: true, force: true });
    }
  });

  test("evict returns count of removed entries", () => {
    const ctx = makeTmpCache(2);
    const cache = ctx.cache;

    try {
      cache.write({ a: 1 });
      cache.write({ b: 2 });
      cache.write({ c: 3 });
      cache.write({ d: 4 });

      expect(cache.size()).toBe(2);
    } finally {
      rmSync(ctx.dir, { recursive: true, force: true });
    }
  });
});
