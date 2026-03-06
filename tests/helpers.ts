import { spawnSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

export const ROOT_DIR = resolve(import.meta.dir, "..");

export function tempDir(prefix: string): string {
  return mkdtempSync(join(tmpdir(), prefix));
}

export function run(
  cmd: string[],
  options: { cwd?: string; env?: Record<string, string>; stdin?: string } = {}
) {
  const result = spawnSync(cmd[0], cmd.slice(1), {
    cwd: options.cwd || ROOT_DIR,
    input: options.stdin || "",
    env: { ...process.env, ...(options.env || {}) },
    encoding: "utf8"
  });
  return {
    exitCode: result.status ?? 1,
    stdout: result.stdout || "",
    stderr: result.stderr || ""
  };
}

export function stdoutJson(proc: ReturnType<typeof run>) {
  return JSON.parse(proc.stdout);
}
