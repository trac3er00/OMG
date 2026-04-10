import { describe, expect, test } from "bun:test";
import { rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DSS, MemoryStoreFullError } from "./dss.js";

function tmpProjectDir(): string {
  return join(
    tmpdir(),
    `omg-dss-test-${Date.now()}-${Math.random().toString(16).slice(2)}`,
  );
}

describe("DSS", () => {
  test("persists entries across process restart simulation", async () => {
    const dir = tmpProjectDir();
    const writer = new DSS({ projectDir: dir, namespace: "tier2" });

    try {
      const expected = new Map<string, string>();

      for (let index = 0; index < 50; index += 1) {
        const key = `entry-${index.toString().padStart(2, "0")}`;
        const value = `value-${index}`;
        expected.set(key, value);
        await writer.set(key, value, { tags: ["persistent"] });
      }
    } finally {
      writer.close();
    }

    const reader = new DSS({ projectDir: dir, namespace: "tier2" });
    try {
      const entries = await reader.list<string>();
      expect(entries).toHaveLength(50);

      for (const entry of entries) {
        const suffix = Number(entry.key.split("-").at(-1));
        expect(entry.value).toBe(`value-${suffix}`);
        expect(entry.tags).toEqual(["persistent"]);
      }
    } finally {
      reader.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("stores ciphertext at rest and decrypts on read", async () => {
    const dir = tmpProjectDir();
    const dss = new DSS({ projectDir: dir, namespace: "tier2" });

    try {
      const plaintext = "super secret cross-session memory";
      await dss.set("cipher-check", plaintext);

      const row = dss
        .getRawDb()
        .get<{
          content: string;
        }>("SELECT content FROM memories WHERE key = ? AND namespace = ?", ["cipher-check", "tier2"]);

      expect(row?.content).toBeDefined();
      expect(row?.content).not.toContain(plaintext);
      expect(() => JSON.parse(row!.content)).not.toThrow();

      const entry = await dss.get<string>("cipher-check");
      expect(entry?.value).toBe(plaintext);
    } finally {
      dss.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("redacts PII before storage and returns masked values", async () => {
    const dir = tmpProjectDir();
    const dss = new DSS({ projectDir: dir, namespace: "tier2" });

    try {
      await dss.set("pii", {
        email: "user@example.com",
        phone: "555-123-4567",
        note: "ssn 123-45-6789",
      });

      const row = dss
        .getRawDb()
        .get<{
          content: string;
        }>("SELECT content FROM memories WHERE key = ? AND namespace = ?", ["pii", "tier2"]);

      expect(row?.content).not.toContain("user@example.com");
      expect(row?.content).not.toContain("555-123-4567");
      expect(row?.content).not.toContain("123-45-6789");

      const entry = await dss.get<{
        email: string;
        phone: string;
        note: string;
      }>("pii");
      expect(entry?.value).toEqual({
        email: "[REDACTED:EMAIL]",
        phone: "[REDACTED:PHONE]",
        note: "ssn [REDACTED:SSN]",
      });
    } finally {
      dss.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("compact preserves data integrity", async () => {
    const dir = tmpProjectDir();
    const dss = new DSS({ projectDir: dir, namespace: "tier2" });

    try {
      await dss.set("keep-1", { value: 1 });
      await dss.set("keep-2", { value: 2 });
      await dss.set("drop", { value: 3 });
      await dss.delete("drop");

      const before = await dss.export<{ value: number }>();
      await dss.compact();
      const after = await dss.export<{ value: number }>();

      expect(after).toEqual(before);

      const memoryRows = dss
        .getRawDb()
        .get<{
          count: number;
        }>("SELECT COUNT(*) AS count FROM memories WHERE namespace = ?", ["tier2"]);
      const ftsRows = dss
        .getRawDb()
        .get<{
          count: number;
        }>("SELECT COUNT(*) AS count FROM memories_fts WHERE namespace = ?", ["tier2"]);

      expect(memoryRows?.count).toBe(2);
      expect(ftsRows?.count).toBe(2);
    } finally {
      dss.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("respects configurable capacity limit", async () => {
    const dir = tmpProjectDir();
    const dss = new DSS({
      projectDir: dir,
      namespace: "tier2",
      capacityLimit: 2,
    });

    try {
      await dss.set("one", "1");
      await dss.set("two", "2");
      await expect(dss.set("three", "3")).rejects.toThrow(MemoryStoreFullError);
    } finally {
      dss.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
