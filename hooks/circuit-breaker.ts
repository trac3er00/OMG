#!/usr/bin/env bun
import { readJsonFile, readJsonFromStdin, writeJsonFile, ledgerPath, resolveProjectDir, ensureDir } from "./_common.ts";

type TrackerEntry = {
  count: number;
  last_failure: string;
  errors: string[];
};

type Tracker = Record<string, TrackerEntry>;

function normalizeCommand(command: string): string {
  return command
    .trim()
    .replace(/\s+/g, " ")
    .replace(/\bnpm run test\b/g, "npm test")
    .replace(/\bpnpm\b/g, "npm")
    .replace(/\byarn\b/g, "npm")
    .replace(/\bbunx\b/g, "")
    .replace(/\bbun\s+run\s+test\b/g, "bun test")
    .trim();
}

function patternFor(payload: any): string {
  const tool = String(payload.tool_name || "");
  if (tool === "Bash") {
    return `Bash:${normalizeCommand(String(payload.tool_input?.command || ""))}`;
  }
  if (tool === "Write" || tool === "Edit" || tool === "MultiEdit") {
    return `${tool}:${String(payload.tool_input?.file_path || payload.tool_input?.filePath || "")}`;
  }
  return tool;
}

function loadTracker(projectDir: string): Tracker {
  return readJsonFile(ledgerPath(projectDir, "failure-tracker.json"), {});
}

function saveTracker(projectDir: string, tracker: Tracker): void {
  ensureDir(ledgerPath(projectDir, "."));
  writeJsonFile(ledgerPath(projectDir, "failure-tracker.json"), tracker);
}

function isFailure(payload: any): { failed: boolean; error: string } {
  const tool = String(payload.tool_name || "");
  if (tool === "Bash") {
    const exitCode = Number(payload.tool_response?.exitCode ?? payload.tool_response?.exit_code ?? 0);
    return {
      failed: exitCode !== 0,
      error: String(payload.tool_response?.stderr || payload.tool_response?.stdout || `exit ${exitCode}`)
    };
  }
  if (tool === "Write" || tool === "Edit" || tool === "MultiEdit") {
    const success = payload.tool_response?.success;
    return { failed: success === false, error: "write failed" };
  }
  return { failed: false, error: "" };
}

export function handleCircuitBreaker(payload: any, projectDir = resolveProjectDir()): void {
  const pattern = patternFor(payload);
  if (!pattern) {
    return;
  }
  const tracker = loadTracker(projectDir);
  const { failed, error } = isFailure(payload);

  if (failed) {
    const entry = tracker[pattern] || { count: 0, last_failure: "", errors: [] };
    entry.count += 1;
    entry.last_failure = new Date().toISOString();
    entry.errors = [...entry.errors.slice(-4), error].filter(Boolean);
    tracker[pattern] = entry;
    saveTracker(projectDir, tracker);
    if (entry.count === 3) {
      process.stderr.write(`CIRCUIT BREAKER WARNING: repeated failure for ${pattern}\n`);
    }
    if (entry.count >= 5) {
      process.stderr.write(`CIRCUIT BREAKER ESCALATE: ${pattern} failed ${entry.count} times\n`);
    }
    return;
  }

  if (tracker[pattern]) {
    delete tracker[pattern];
    saveTracker(projectDir, tracker);
  }
}

async function main() {
  const payload = await readJsonFromStdin<any>({});
  try {
    handleCircuitBreaker(payload);
  } catch {
    // Hooks must never crash the host flow.
  }
}

if (import.meta.main) {
  await main();
}
