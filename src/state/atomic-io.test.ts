import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { appendJsonLine, atomicWrite, atomicWriteJson, readJsonFile, readJsonLines } from "./atomic-io.js";

function tempPath(name: string): string {
  return join(tmpdir(), `omg-state-${name}-${Date.now()}-${Math.random().toString(16).slice(2)}`);
}

describe("atomic I/O", () => {
  test("atomicWrite writes file content", () => {
    const filePath = tempPath("write.txt");
    atomicWrite(filePath, "hello");
    expect(readFileSync(filePath, "utf8")).toBe("hello");
    rmSync(filePath, { force: true });
  });

  test("atomicWriteJson writes valid JSON", () => {
    const filePath = tempPath("write.json");
    atomicWriteJson(filePath, { status: "ok", count: 42 });
    const parsed = JSON.parse(readFileSync(filePath, "utf8")) as { status: string; count: number };
    expect(parsed.status).toBe("ok");
    expect(parsed.count).toBe(42);
    rmSync(filePath, { force: true });
  });

  test("atomicWrite creates parent directories", () => {
    const base = tempPath("nested");
    const filePath = join(base, "sub", "file.txt");
    atomicWrite(filePath, "content");
    expect(existsSync(filePath)).toBe(true);
    rmSync(base, { force: true, recursive: true });
  });

  test("readJsonFile returns undefined for missing file", () => {
    expect(readJsonFile("/definitely/missing/file.json")).toBeUndefined();
  });

  test("readJsonFile reads valid JSON", () => {
    const filePath = tempPath("read.json");
    writeFileSync(filePath, JSON.stringify({ x: 1 }), "utf8");
    const data = readJsonFile<{ x: number }>(filePath);
    expect(data?.x).toBe(1);
    rmSync(filePath, { force: true });
  });

  test("readJsonLines handles valid and malformed rows", () => {
    const filePath = tempPath("rows.jsonl");
    atomicWrite(filePath, '{"a":1}\nINVALID\n{"a":3}\n');
    const rows = readJsonLines<{ a: number }>(filePath);
    expect(rows).toHaveLength(2);
    expect(rows[0]?.a).toBe(1);
    expect(rows[1]?.a).toBe(3);
    rmSync(filePath, { force: true });
  });

  test("appendJsonLine appends newline-delimited JSON", () => {
    const filePath = tempPath("append.jsonl");
    appendJsonLine(filePath, { id: 1 });
    appendJsonLine(filePath, { id: 2 });
    const rows = readJsonLines<{ id: number }>(filePath);
    expect(rows.map((r) => r.id)).toEqual([1, 2]);
    rmSync(filePath, { force: true });
  });
});
