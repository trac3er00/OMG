#!/usr/bin/env bun
import { appendFileSync } from "node:fs";
import { ledgerPath, readJsonFromStdin, resolveProjectDir, ensureParent } from "./_common.ts";

async function main() {
  const payload = await readJsonFromStdin<any>({});
  const projectDir = resolveProjectDir();
  const path = ledgerPath(projectDir, "tool-ledger.jsonl");
  const record = {
    ts: new Date().toISOString(),
    tool: payload.tool_name || "",
    file: payload.tool_input?.file_path || payload.tool_input?.filePath || "",
    command: payload.tool_input?.command || "",
    success: payload.tool_response?.success,
    exit_code: payload.tool_response?.exitCode ?? payload.tool_response?.exit_code
  };
  ensureParent(path);
  appendFileSync(path, `${JSON.stringify(record)}\n`, "utf8");
}

if (import.meta.main) {
  try {
    await main();
  } catch {
    process.exit(0);
  }
}
