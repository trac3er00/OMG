import { describe, expect, it } from "bun:test";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { MemoryStore } from "./store.js";

describe("src/memory/MemoryStore", () => {
  it("persists nested values in .omg/memory/memory.json", () => {
    const dir = mkdtempSync(join(tmpdir(), "universal-memory-"));

    try {
      const store = new MemoryStore(dir);
      store.set("user.theme", "dark");
      store.set("team.review.required", true);

      expect(store.get("user.theme")).toBe("dark");
      expect(store.get("team.review.required")).toBe(true);
      expect(store.list()).toEqual({
        user: { theme: "dark" },
        team: { review: { required: true } },
      });
      expect(existsSync(join(dir, ".omg", "memory", "memory.json"))).toBe(true);
      expect(
        JSON.parse(readFileSync(join(dir, ".omg", "memory", "memory.json"), "utf8")),
      ).toEqual(store.list());
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
