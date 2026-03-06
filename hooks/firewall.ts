#!/usr/bin/env bun
import { readJsonFromStdin } from "./_common.ts";
import { evaluateBashCommand } from "./policy_engine.ts";

async function main() {
  const payload = await readJsonFromStdin<any>({});
  const command = String(payload.tool_input?.command || "");
  const decision = evaluateBashCommand(command);
  if (decision.action !== "allow") {
    process.stdout.write(`${JSON.stringify(decision, null, 2)}\n`);
  }
}

if (import.meta.main) {
  try {
    await main();
  } catch {
    process.exit(0);
  }
}
