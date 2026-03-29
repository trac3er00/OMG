import { describe, test, expect } from "bun:test";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { rmSync } from "node:fs";
import { MemoryStore, MemoryStoreFullError } from "./memory-store.js";

function tmpStore(namespace = "test"): { store: MemoryStore; dir: string } {
  const dir = join(tmpdir(), `omg-memory-test-${Date.now()}-${Math.random().toString(16).slice(2)}`);
  const store = new MemoryStore({ projectDir: dir, namespace });
  return { store, dir };
}

describe("MemoryStore CRUD", () => {
  test("write and read roundtrip", async () => {
    const { store, dir } = tmpStore();
    try {
      await store.write("key1", { content: "hello world", tags: ["test"] });
      const entry = await store.read("key1");
      expect(entry).not.toBeNull();
      expect(entry?.content).toBe("hello world");
      expect(entry?.tags).toEqual(["test"]);
      expect(entry?.namespace).toBe("test");
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("read returns null for missing key", async () => {
    const { store, dir } = tmpStore();
    try {
      const entry = await store.read("nonexistent");
      expect(entry).toBeNull();
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("delete removes entry", async () => {
    const { store, dir } = tmpStore();
    try {
      await store.write("key1", { content: "delete me" });
      const deleted = await store.delete("key1");
      expect(deleted).toBe(true);
      expect(await store.read("key1")).toBeNull();
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("delete returns false for missing key", async () => {
    const { store, dir } = tmpStore();
    try {
      expect(await store.delete("nonexistent")).toBe(false);
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("listKeys returns all keys in namespace", async () => {
    const { store, dir } = tmpStore();
    try {
      await store.write("a", { content: "first" });
      await store.write("b", { content: "second" });
      await store.write("c", { content: "third" });
      const keys = await store.listKeys();
      expect(keys).toHaveLength(3);
      expect(keys).toEqual(["a", "b", "c"]);
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("listKeys with prefix filters correctly", async () => {
    const { store, dir } = tmpStore();
    try {
      await store.write("user:1", { content: "user one" });
      await store.write("user:2", { content: "user two" });
      await store.write("task:1", { content: "task one" });
      const userKeys = await store.listKeys("user:");
      expect(userKeys).toHaveLength(2);
      expect(userKeys.every((k) => k.startsWith("user:"))).toBe(true);
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("PII Redaction", () => {
  test("email addresses are redacted", async () => {
    const { store, dir } = tmpStore();
    try {
      await store.write("pii-test", { content: "contact user@example.com for help" });
      const entry = await store.read("pii-test");
      expect(entry?.content).not.toContain("user@example.com");
      expect(entry?.content).toContain("[REDACTED:EMAIL]");
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("phone numbers are redacted", async () => {
    const { store, dir } = tmpStore();
    try {
      await store.write("phone-test", { content: "call 555-123-4567 today" });
      const entry = await store.read("phone-test");
      expect(entry?.content).not.toContain("555-123-4567");
      expect(entry?.content).toContain("[REDACTED:PHONE]");
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("ssn patterns are redacted", async () => {
    const { store, dir } = tmpStore();
    try {
      await store.write("ssn-test", { content: "ssn 123-45-6789" });
      const entry = await store.read("ssn-test");
      expect(entry?.content).not.toContain("123-45-6789");
      expect(entry?.content).toContain("[REDACTED:SSN]");
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("non-PII content is preserved", async () => {
    const { store, dir } = tmpStore();
    try {
      await store.write("clean", { content: "normal content without PII" });
      const entry = await store.read("clean");
      expect(entry?.content).toBe("normal content without PII");
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("Encryption", () => {
  test("content stored encrypted in SQLite", async () => {
    const { store, dir } = tmpStore();
    try {
      const secret = "super secret value";
      await store.write("encrypted-key", { content: secret });

      const rawDb = store.getRawDb();
      const row = rawDb.get<{ content: string }>(
        "SELECT content FROM memories WHERE key = ? AND namespace = ?",
        ["encrypted-key", "test"],
      );

      expect(row?.content).toBeDefined();
      expect(row?.content).not.toBe(secret);
      expect(() => JSON.parse(row!.content)).not.toThrow();

      const entry = await store.read("encrypted-key");
      expect(entry?.content).toBe(secret);
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("FTS5 Search", () => {
  test("search finds matching content", async () => {
    const { store, dir } = tmpStore();
    try {
      await store.write("doc1", { content: "orchestration agent routing" });
      await store.write("doc2", { content: "security firewall protection" });
      await store.write("doc3", { content: "agent dispatch management" });

      const results = await store.search("agent");
      expect(results.length).toBeGreaterThan(0);
      expect(results.some((r) => r.key === "doc1" || r.key === "doc3")).toBe(true);
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("search with no results returns empty array", async () => {
    const { store, dir } = tmpStore();
    try {
      await store.write("doc1", { content: "some content" });
      const results = await store.search("xyznonexistentterm");
      expect(results).toHaveLength(0);
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("malformed FTS query returns empty array", async () => {
    const { store, dir } = tmpStore();
    try {
      await store.write("doc1", { content: "content" });
      const results = await store.search("\"");
      expect(results).toHaveLength(0);
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("Namespace isolation", () => {
  test("different namespaces are isolated", async () => {
    const dir = join(tmpdir(), `omg-ns-test-${Date.now()}`);
    const store1 = new MemoryStore({ projectDir: dir, namespace: "ns1" });
    const store2 = new MemoryStore({ projectDir: dir, namespace: "ns2" });

    try {
      await store1.write("shared-key", { content: "from ns1" });
      const fromNs2 = await store2.read("shared-key");
      expect(fromNs2).toBeNull();

      const ns1Keys = await store1.listKeys();
      const ns2Keys = await store2.listKeys();
      expect(ns1Keys).toContain("shared-key");
      expect(ns2Keys).not.toContain("shared-key");
    } finally {
      store1.close();
      store2.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("Capacity limit", () => {
  test("throws when namespace exceeds limit", async () => {
    const { store, dir } = tmpStore();
    try {
      const now = new Date().toISOString();
      store.getRawDb().run(
        `
        WITH RECURSIVE seq(n) AS (
          SELECT 0
          UNION ALL
          SELECT n + 1 FROM seq WHERE n < 9999
        )
        INSERT INTO memories (key, namespace, content, tags_json, run_id, source_cli, created_at, updated_at)
        SELECT 'k' || n, ?, '{}', '[]', NULL, NULL, ?, ? FROM seq
        `,
        ["test", now, now],
      );
      await expect(store.write("overflow", { content: "boom" })).rejects.toThrow(MemoryStoreFullError);
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
