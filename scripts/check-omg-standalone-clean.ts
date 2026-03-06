#!/usr/bin/env bun
import { spawnSync } from "bun";

if (import.meta.main) {
  const proc = spawnSync({
    cmd: ["bun", "scripts/check-runtime-clean.ts"],
    cwd: process.cwd(),
    stdout: "inherit",
    stderr: "inherit"
  });
  process.exit(proc.exitCode);
}
