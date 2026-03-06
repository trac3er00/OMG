#!/usr/bin/env bun
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

function stateDir(): string {
  const projectDir = process.env.CLAUDE_PROJECT_DIR || process.cwd();
  return join(projectDir, ".omg", "state", "session-snapshots");
}

function ensureState() {
  mkdirSync(stateDir(), { recursive: true });
}

function main(argv = process.argv.slice(2)) {
  ensureState();
  const [command = "list", name = "snapshot"] = argv;
  const outputPath = join(stateDir(), `${name}.json`);
  if (command === "list" || command === "branches") {
    const names = existsSync(stateDir())
      ? Bun.spawnSync({ cmd: ["bash", "-lc", `find "${stateDir()}" -maxdepth 1 -name '*.json' -print | xargs -n1 basename | sed 's/.json$//'`] })
          .stdout.toString()
          .split(/\r?\n/)
          .filter(Boolean)
      : [];
    process.stdout.write(`${JSON.stringify({ status: "ok", names }, null, 2)}\n`);
    return 0;
  }
  if (command === "switch") {
    process.stdout.write(`${JSON.stringify({ status: "ok", active: name }, null, 2)}\n`);
    return 0;
  }
  if (command === "branch") {
    writeFileSync(outputPath, JSON.stringify({ name, created_at: new Date().toISOString() }, null, 2));
    process.stdout.write(`${JSON.stringify({ status: "ok", path: outputPath }, null, 2)}\n`);
    return 0;
  }
  if (command === "merge-preview" || command === "merge") {
    process.stdout.write(`${JSON.stringify({ status: "ok", command, source: name }, null, 2)}\n`);
    return 0;
  }
  process.stderr.write(`Unknown command: ${command}\n`);
  return 2;
}

if (import.meta.main) {
  process.exit(main());
}
