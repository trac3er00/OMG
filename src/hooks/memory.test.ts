import { describe, expect, test } from "bun:test";
import type { MemoryDeps } from "./memory.js";

type RecordedCall = { path: string; content: string };

function makeDeps(existing = false) {
  const writes: RecordedCall[] = [];
  const appends: RecordedCall[] = [];
  const deps: MemoryDeps = {
    readFile: async () => "",
    writeFile: async (path, content) => {
      writes.push({ path, content });
    },
    appendFile: async (path, content) => {
      appends.push({ path, content });
    },
    exists: async () => existing,
    mkdirp: async () => {},
    listDir: async () => [],
    remove: async () => {},
  };

  return { deps, writes, appends };
}

async function loadMemoryModule(tag: string) {
  return await import(`./memory.ts?${tag}=${Date.now()}-${Math.random()}`);
}

function compressLikeSpec(content: string, maxChars: number): string {
  if (content.length <= maxChars) return content;
  const keepChars = Math.floor(maxChars * 0.8);
  const head = content.slice(0, Math.floor(keepChars * 0.6));
  const tail = content.slice(content.length - Math.floor(keepChars * 0.4));
  return `${head}\n[...compressed: ${content.length - keepChars} chars removed...]\n${tail}`;
}

describe("hooks/memory", () => {
  test("short content is stored as-is", async () => {
    delete process.env["OMG_MEMORY_MAX_CHARS"];
    const { MemoryHook } = await loadMemoryModule("short");
    const { deps, writes, appends } = makeDeps(false);
    const hook = new MemoryHook("/tmp/project", deps);
    const content = "short learning note";

    await hook.recordLearning("short-key", content);

    expect(writes).toHaveLength(1);
    expect(writes[0].content).toBe(content);
    expect(appends).toHaveLength(0);
  });

  test("long content is compressed with marker", async () => {
    delete process.env["OMG_MEMORY_MAX_CHARS"];
    const { MemoryHook } = await loadMemoryModule("long");
    const { deps, writes } = makeDeps(false);
    const hook = new MemoryHook("/tmp/project", deps);
    const content = `${"a".repeat(1200)}${"b".repeat(1200)}`;

    await hook.recordLearning("long-key", content);

    const expected = compressLikeSpec(content, 2000);
    expect(writes).toHaveLength(1);
    expect(writes[0].content).toBe(expected);
    expect(writes[0].content).toContain("[...compressed:");
  });

  test("compression logs an info event", async () => {
    delete process.env["OMG_MEMORY_MAX_CHARS"];
    const { MemoryHook } = await loadMemoryModule("log");
    const { deps } = makeDeps(false);
    const hook = new MemoryHook("/tmp/project", deps);
    const content = `${"x".repeat(1500)}${"y".repeat(1500)}`;
    const logs: string[] = [];
    const originalInfo = console.info;

    console.info = (...args: unknown[]) => {
      logs.push(args.map((value) => String(value)).join(" "));
    };

    try {
      await hook.recordLearning("log-key", content);
    } finally {
      console.info = originalInfo;
    }

    expect(
      logs.some((line) => line.includes("[memory] content compressed from")),
    ).toBe(true);
  });

  test("OMG_MEMORY_MAX_CHARS is respected", async () => {
    const original = process.env["OMG_MEMORY_MAX_CHARS"];
    process.env["OMG_MEMORY_MAX_CHARS"] = "100";
    const { MemoryHook } = await loadMemoryModule("env");
    const { deps, writes } = makeDeps(false);
    const hook = new MemoryHook("/tmp/project", deps);
    const content = `${"h".repeat(75)}${"t".repeat(75)}`;

    try {
      await hook.recordLearning("env-key", content);
    } finally {
      if (original === undefined) {
        delete process.env["OMG_MEMORY_MAX_CHARS"];
      } else {
        process.env["OMG_MEMORY_MAX_CHARS"] = original;
      }
    }

    expect(writes).toHaveLength(1);
    expect(writes[0].content).toBe(compressLikeSpec(content, 100));
  });
});
