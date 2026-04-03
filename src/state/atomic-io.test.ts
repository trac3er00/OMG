import { describe, expect, mock, test } from "bun:test";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function tempPath(name: string): string {
  return join(
    tmpdir(),
    `omg-state-${name}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
  );
}

async function loadAtomicIo(
  tag: string,
): Promise<typeof import("./atomic-io.js")> {
  return (await import(
    `./atomic-io.js?${tag}`
  )) as typeof import("./atomic-io.js");
}

describe("atomic I/O", () => {
  test("temp file collisions are retried with unique names", async () => {
    const base = tempPath("unique-tmp");
    const collisionHex = "1111111111111111";
    const fallbackHex = "2222222222222222";
    mkdirSync(join(base, `${collisionHex}.tmp`), { recursive: true });

    let calls = 0;
    mock.module("node:crypto", () => ({
      randomBytes(size: number) {
        calls += 1;
        const hex = calls === 1 ? collisionHex : fallbackHex;
        return Buffer.from(hex, "hex").subarray(0, size);
      },
    }));

    const { atomicWrite } = await loadAtomicIo("unique-tmp");
    const filePath = join(base, "file.txt");
    atomicWrite(filePath, "hello");

    expect(readFileSync(filePath, "utf8")).toBe("hello");
    rmSync(base, { force: true, recursive: true });
  });

  test("atomicWrite writes file content", async () => {
    const { atomicWrite } = await loadAtomicIo("write");
    const filePath = tempPath("write.txt");
    atomicWrite(filePath, "hello");
    expect(readFileSync(filePath, "utf8")).toBe("hello");
    rmSync(filePath, { force: true });
  });

  test("writeFileAtomic writes file content asynchronously", async () => {
    const { writeFileAtomic } = await loadAtomicIo("async");
    const filePath = tempPath("async.txt");
    await writeFileAtomic(filePath, "hello async");
    expect(readFileSync(filePath, "utf8")).toBe("hello async");
    rmSync(filePath, { force: true });
  });

  test("atomicWriteJson writes valid JSON", async () => {
    const { atomicWriteJson } = await loadAtomicIo("json");
    const filePath = tempPath("write.json");
    atomicWriteJson(filePath, { status: "ok", count: 42 });
    const parsed = JSON.parse(readFileSync(filePath, "utf8")) as {
      status: string;
      count: number;
    };
    expect(parsed.status).toBe("ok");
    expect(parsed.count).toBe(42);
    rmSync(filePath, { force: true });
  });

  test("atomicWrite creates parent directories", async () => {
    const { atomicWrite } = await loadAtomicIo("dirs");
    const base = tempPath("nested");
    const filePath = join(base, "sub", "file.txt");
    atomicWrite(filePath, "content");
    expect(existsSync(filePath)).toBe(true);
    rmSync(base, { force: true, recursive: true });
  });

  test("readJsonFile returns undefined for missing file", async () => {
    const { readJsonFile } = await loadAtomicIo("missing");
    expect(readJsonFile("/definitely/missing/file.json")).toBeUndefined();
  });

  test("readJsonFile reads valid JSON", async () => {
    const { readJsonFile } = await loadAtomicIo("read-json");
    const filePath = tempPath("read.json");
    writeFileSync(filePath, JSON.stringify({ x: 1 }), "utf8");
    const data = readJsonFile<{ x: number }>(filePath);
    expect(data?.x).toBe(1);
    rmSync(filePath, { force: true });
  });

  test("readJsonLines handles valid and malformed rows", async () => {
    const { atomicWrite, readJsonLines } = await loadAtomicIo("jsonl");
    const filePath = tempPath("rows.jsonl");
    atomicWrite(filePath, '{"a":1}\nINVALID\n{"a":3}\n');
    const rows = readJsonLines<{ a: number }>(filePath);
    expect(rows).toHaveLength(2);
    expect(rows[0]?.a).toBe(1);
    expect(rows[1]?.a).toBe(3);
    rmSync(filePath, { force: true });
  });

  test("appendJsonLine appends newline-delimited JSON", async () => {
    const { appendJsonLine, readJsonLines } = await loadAtomicIo("append");
    const filePath = tempPath("append.jsonl");
    appendJsonLine(filePath, { id: 1 });
    appendJsonLine(filePath, { id: 2 });
    const rows = readJsonLines<{ id: number }>(filePath);
    expect(rows.map((r) => r.id)).toEqual([1, 2]);
    rmSync(filePath, { force: true });
  });
});
