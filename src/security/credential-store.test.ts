import { describe, test, expect } from "bun:test";
import { CredentialStore } from "./credential-store.js";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { rmSync, readFileSync } from "node:fs";

describe("CredentialStore", () => {
  function mkStore(): { store: CredentialStore; dir: string } {
    const dir = join(tmpdir(), `omg-cred-test-${Date.now()}-${Math.random().toString(36).slice(2)}`);
    const store = new CredentialStore({ projectDir: dir, passphrase: "test-passphrase" });
    return { store, dir };
  }

  test("set and get credential", async () => {
    const { store, dir } = mkStore();
    try {
      await store.set("OPENAI_API_KEY", "sk-test-value-123");
      const val = await store.get("OPENAI_API_KEY");
      expect(val).toBe("sk-test-value-123");
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("raw file is encrypted (not plaintext)", async () => {
    const { store, dir } = mkStore();
    try {
      await store.set("MY_SECRET", "super-secret-value");
      const rawPath = store.getStorePath();
      const raw = readFileSync(rawPath, "utf8");
      expect(raw).not.toContain("super-secret-value");
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("get returns null for missing key", async () => {
    const { store, dir } = mkStore();
    try {
      const val = await store.get("NONEXISTENT_KEY");
      expect(val).toBeNull();
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("delete removes credential", async () => {
    const { store, dir } = mkStore();
    try {
      await store.set("TO_DELETE", "value");
      await store.delete("TO_DELETE");
      expect(await store.get("TO_DELETE")).toBeNull();
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("list returns all keys", async () => {
    const { store, dir } = mkStore();
    try {
      await store.set("KEY_A", "val_a");
      await store.set("KEY_B", "val_b");
      const keys = await store.list();
      expect(keys).toContain("KEY_A");
      expect(keys).toContain("KEY_B");
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("wrong passphrase returns empty store", async () => {
    const { store, dir } = mkStore();
    try {
      await store.set("SECRET", "value");
      store.close();

      const wrongStore = new CredentialStore({ projectDir: dir, passphrase: "wrong-passphrase" });
      const val = await wrongStore.get("SECRET");
      expect(val).toBeNull();
      wrongStore.close();
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("multiple set/get roundtrips", async () => {
    const { store, dir } = mkStore();
    try {
      await store.set("A", "value-a");
      await store.set("B", "value-b");
      await store.set("C", "value-c");
      expect(await store.get("A")).toBe("value-a");
      expect(await store.get("B")).toBe("value-b");
      expect(await store.get("C")).toBe("value-c");
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("overwrite existing credential", async () => {
    const { store, dir } = mkStore();
    try {
      await store.set("KEY", "old-value");
      await store.set("KEY", "new-value");
      expect(await store.get("KEY")).toBe("new-value");
    } finally {
      store.close();
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
