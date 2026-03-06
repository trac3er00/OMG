#!/usr/bin/env bun
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { resolveProjectDir } from "./_common.ts";

const ALLOWLIST = [/^bun test\b/, /^npm test\b/, /^vitest\b/, /^jest\b/];

if (import.meta.main) {
  try {
    const configPath = join(resolveProjectDir(), ".omg", "quality-gate.json");
    if (!existsSync(configPath)) {
      process.exit(0);
    }
    const payload = JSON.parse(readFileSync(configPath, "utf8"));
    const command = String(payload.test || payload.lint || "");
    if (command && !ALLOWLIST.some((pattern) => pattern.test(command))) {
      process.stdout.write(
        `${JSON.stringify({ status: "blocked", reason: `BLOCKED quality command: ${command}` }, null, 2)}\n`
      );
    }
  } catch {
    process.exit(0);
  }
}
