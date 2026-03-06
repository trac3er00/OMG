#!/usr/bin/env bun
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";

function readJson(path: string): Record<string, any> {
  if (!existsSync(path)) {
    return {};
  }
  return JSON.parse(readFileSync(path, "utf8"));
}

function unique<T>(items: T[]): T[] {
  return [...new Set(items)];
}

function mergeHooks(target: Record<string, any>, source: Record<string, any>) {
  const merged: Record<string, any[]> = { ...target };
  for (const [event, entries] of Object.entries(source)) {
    const current = Array.isArray(merged[event]) ? merged[event] : [];
    const next = Array.isArray(entries) ? entries : [];
    const serialized = new Set(current.map((entry) => JSON.stringify(entry)));
    for (const entry of next) {
      const key = JSON.stringify(entry);
      if (!serialized.has(key)) {
        current.push(entry);
        serialized.add(key);
      }
    }
    merged[event] = current;
  }
  return merged;
}

function mergeSettings(target: Record<string, any>, source: Record<string, any>) {
  return {
    ...target,
    ...source,
    permissions: {
      allow: unique([...(target.permissions?.allow || []), ...(source.permissions?.allow || [])]),
      ask: unique([...(target.permissions?.ask || []), ...(source.permissions?.ask || [])]),
      deny: unique([...(target.permissions?.deny || []), ...(source.permissions?.deny || [])])
    },
    hooks: mergeHooks(target.hooks || {}, source.hooks || {})
  };
}

function main(argv = process.argv.slice(2)) {
  const [targetPath, sourcePath] = argv;
  if (!targetPath || !sourcePath) {
    process.stderr.write("Usage: settings-merge.ts <target> <source>\n");
    return 2;
  }
  const merged = mergeSettings(readJson(targetPath), readJson(sourcePath));
  if (argv.includes("--dry-run")) {
    process.stdout.write(`${JSON.stringify(merged, null, 2)}\n`);
    return 0;
  }
  Bun.write(targetPath, JSON.stringify(merged, null, 2));
  return 0;
}

if (import.meta.main) {
  process.exit(main());
}
