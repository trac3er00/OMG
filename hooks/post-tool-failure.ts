#!/usr/bin/env bun
import { join } from "node:path";
import { readJsonFromStdin, resolveProjectDir, writeJsonFile } from "./_common.ts";

async function main() {
  const payload = await readJsonFromStdin<any>({});
  const output = join(resolveProjectDir(), ".omg", "state", "last-tool-error.json");
  writeJsonFile(output, {
    ts: new Date().toISOString(),
    tool: payload.tool_name || "",
    tool_input: payload.tool_input || {},
    tool_response: payload.tool_response || {}
  });
}

if (import.meta.main) {
  try {
    await main();
  } catch {
    process.exit(0);
  }
}
