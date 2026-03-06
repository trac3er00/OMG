#!/usr/bin/env bun
import { readJsonFromStdin } from "./_common.ts";
import { runStopDispatcher } from "./stop_dispatcher.ts";

async function main() {
  const payload = await readJsonFromStdin<any>({});
  if (payload.stop_hook_active) {
    return;
  }
  const blocks = runStopDispatcher(payload);
  if (blocks.length > 0) {
    process.stdout.write(`${JSON.stringify({ status: "blocked", blocks }, null, 2)}\n`);
  }
}

if (import.meta.main) {
  try {
    await main();
  } catch {
    process.exit(0);
  }
}
