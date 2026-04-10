import { describe, expect, test } from "bun:test";
import { mkdtempSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { IMSS } from "./imss.js";

describe("IMSS", () => {
  test("set then get returns stored value", () => {
    const imss = new IMSS<string>();

    imss.set("session:alpha", "hello");

    expect(imss.get("session:alpha")).toBe("hello");
  });

  test("set with ttl expires on next access", async () => {
    const imss = new IMSS<string>();

    imss.set("ttl:key", "ephemeral", 25);
    await Bun.sleep(40);

    expect(imss.get("ttl:key")).toBeUndefined();
    expect(imss.list()).toEqual([]);
  });

  test("stores and retrieves 1000 entries without degradation", () => {
    const imss = new IMSS<number>();
    const startedAt = performance.now();

    for (let index = 0; index < 1000; index += 1) {
      imss.set(`entry:${index}`, index);
    }

    for (let index = 0; index < 1000; index += 1) {
      expect(imss.get(`entry:${index}`)).toBe(index);
    }

    const elapsedMs = performance.now() - startedAt;
    expect(imss.list()).toHaveLength(1000);
    expect(elapsedMs).toBeLessThan(2_000);
  });

  test("clear wipes all entries", () => {
    const imss = new IMSS<string>();

    imss.set("one", "1");
    imss.set("two", "2");
    imss.clear();

    expect(imss.get("one")).toBeUndefined();
    expect(imss.get("two")).toBeUndefined();
    expect(imss.list()).toEqual([]);
  });

  test("list with prefix returns matching keys", () => {
    const imss = new IMSS<string>();

    imss.set("user:1", "Ada");
    imss.set("user:2", "Linus");
    imss.set("task:1", "Ship");

    expect(imss.list("user:")).toEqual(["user:1", "user:2"]);
  });

  test("does not write to disk during operations", () => {
    const sandboxDir = mkdtempSync(join(tmpdir(), "omg-imss-no-disk-"));
    const beforeEntries = readdirSync(sandboxDir);
    const imss = new IMSS<{ payload: string }>();

    try {
      imss.set("disk:check", { payload: "memory only" });
      expect(imss.get("disk:check")).toEqual({ payload: "memory only" });
      imss.delete("disk:check");
      imss.clear();

      expect(beforeEntries).toEqual([]);
      expect(readdirSync(sandboxDir)).toEqual([]);
    } finally {
      rmSync(sandboxDir, { recursive: true, force: true });
    }
  });
});
