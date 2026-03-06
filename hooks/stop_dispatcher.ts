#!/usr/bin/env bun
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { getFeatureFlag, readJsonFromStdin, resolveProjectDir } from "./_common.ts";

type StopData = Record<string, any>;

function recentCommands(data: StopData): string[] {
  return Array.isArray(data?._stop_ctx?.recent_commands) ? data._stop_ctx.recent_commands.map(String) : [];
}

export function checkVerification(data: StopData): string[] {
  if (!getFeatureFlag("STOP_GATE", true)) {
    return [];
  }
  if (!data?._stop_ctx?.has_source_writes) {
    return [];
  }
  const hasVerification = recentCommands(data).some((command) => /\b(bun test|npm test|vitest|jest|cargo test|go test)\b/.test(command));
  return hasVerification ? [] : ["NO verification commands were executed after source writes."];
}

export function checkDiffBudget(_data: StopData, projectDir: string): string[] {
  if (!getFeatureFlag("STOP_GATE", true)) {
    return [];
  }
  const names = Bun.spawnSync({ cmd: ["git", "diff", "--name-only"], cwd: projectDir, stdout: "pipe", stderr: "ignore" });
  const files = names.stdout.toString().split(/\r?\n/).filter(Boolean);
  const stats = Bun.spawnSync({ cmd: ["git", "diff", "--numstat"], cwd: projectDir, stdout: "pipe", stderr: "ignore" });
  const lineCount = stats.stdout
    .toString()
    .split(/\r?\n/)
    .filter(Boolean)
    .reduce((total: number, line: string) => {
      const [added, removed] = line.split("\t");
      return total + Number(added || 0) + Number(removed || 0);
    }, 0);
  return files.length > 3 || lineCount > 150 ? [`Diff exceeds budget (${files.length} files, ${lineCount} lines).`] : [];
}

export function checkRecentFailures(data: StopData): string[] {
  if (!getFeatureFlag("STOP_GATE", true)) {
    return [];
  }
  const entries = Array.isArray(data?._stop_ctx?.recent_entries) ? data._stop_ctx.recent_entries.slice(-3) : [];
  if (entries.length === 3 && entries.every((entry: any) => Number(entry.exit_code ?? 0) !== 0)) {
    return ["Last 3 commands ALL FAILED."];
  }
  return [];
}

export function checkTestExecution(data: StopData): string[] {
  if (!getFeatureFlag("STOP_GATE", true)) {
    return [];
  }
  const changed = Array.isArray(data?._changed_files) ? data._changed_files.map(String) : [];
  const changedTests = changed.some((path) => /(^|\/)(tests?|__tests__)\//.test(path));
  return data?._stop_ctx?.has_material_writes && changedTests && !data?._has_test
    ? ["Tests changed but the test suite was never executed."]
    : [];
}

export function checkTestValidatorCoverage(data: StopData): string[] {
  if (!getFeatureFlag("STOP_GATE", true)) {
    return [];
  }
  const changed = Array.isArray(data?._changed_files) ? data._changed_files.map(String) : [];
  const touchedSource = changed.some((path) => /(^|\/)src\//.test(path) || /\.(ts|tsx|js|jsx)$/.test(path));
  const touchedTests = changed.some((path) => /(^|\/)(tests?|__tests__)\//.test(path) || /\.test\.(ts|tsx|js|jsx)$/.test(path));
  return data?._stop_ctx?.has_source_writes && touchedSource && !touchedTests
    ? ["TEST-VALIDATOR: source changed without matching test updates."]
    : [];
}

export function checkFalseFix(data: StopData): string[] {
  if (!getFeatureFlag("STOP_GATE", true)) {
    return [];
  }
  const changed = Array.isArray(data?._changed_files) ? data._changed_files.map(String) : [];
  if (!data?._stop_ctx?.has_material_writes || changed.length === 0) {
    return [];
  }
  const onlyTestsAndScripts = changed.every((path) => /(^|\/)(tests?|scripts)\//.test(path) || path.endsWith(".md"));
  return onlyTestsAndScripts ? ["FALSE FIX DETECTED: no source files changed."] : [];
}

export function checkWriteFailures(data: StopData): string[] {
  if (!getFeatureFlag("STOP_GATE", true)) {
    return [];
  }
  const entries = Array.isArray(data?._stop_ctx?.recent_entries) ? data._stop_ctx.recent_entries : [];
  const failed = entries.find((entry: any) => (entry.tool === "Write" || entry.tool === "Edit") && entry.success === false);
  return failed ? [`WRITE/EDIT FAILURE DETECTED: ${failed.file}`] : [];
}

export function checkSimplifier(data: StopData): string[] {
  const entries = Array.isArray(data?._stop_ctx?.source_write_entries) ? data._stop_ctx.source_write_entries : [];
  for (const entry of entries) {
    const path = String(entry.file || "");
    if (!path || !existsSync(path)) {
      continue;
    }
    const content = readFileSync(path, "utf8");
    const lines = content.split(/\r?\n/).filter(Boolean);
    if (lines.length === 0) {
      continue;
    }
    const commentLines = lines.filter((line) => line.trim().startsWith("//") || line.trim().startsWith("#")).length;
    if (commentLines / lines.length > 0.4) {
      process.stderr.write(`@simplifier advisory: ${commentLines} comment lines in ${path}\n`);
    }
  }
  return [];
}

export function runStopDispatcher(data: StopData, projectDir = resolveProjectDir()): string[] {
  return [
    ...checkVerification(data),
    ...checkDiffBudget(data, projectDir),
    ...checkRecentFailures(data),
    ...checkTestExecution(data),
    ...checkTestValidatorCoverage(data),
    ...checkFalseFix(data),
    ...checkWriteFailures(data),
    ...checkSimplifier(data)
  ];
}

async function main() {
  const data = await readJsonFromStdin<StopData>({});
  if (data.stop_hook_active) {
    return;
  }
  const projectDir = resolveProjectDir();
  const blocks = runStopDispatcher(data, projectDir);
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
