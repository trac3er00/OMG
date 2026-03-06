#!/usr/bin/env bun
import { join } from "node:path";
import { readJsonFromStdin, resolveProjectDir, writeJsonFile } from "./_common.ts";

async function main() {
  const payload = await readJsonFromStdin<any>({});
  writeJsonFile(join(resolveProjectDir(), ".omg", "state", "session-start.json"), {
    ts: new Date().toISOString(),
    payload
  });
}

if (import.meta.main) {
  try {
    await main();
  } catch {
    process.exit(0);
  }
}
