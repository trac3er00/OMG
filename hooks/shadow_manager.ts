import { copyFileSync, existsSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { ensureDir, writeJsonFile } from "./_common.ts";

function shadowRoot(projectDir: string): string {
  return join(projectDir, ".omg", "shadow");
}

function evidenceRoot(projectDir: string): string {
  return join(projectDir, ".omg", "evidence");
}

export function createEvidencePack(
  projectDir: string,
  runId: string,
  options: {
    tests?: unknown[];
    security_scans?: unknown[];
    diff_summary?: Record<string, unknown>;
    reproducibility?: Record<string, unknown>;
    unresolved_risks?: string[];
  } = {}
): string {
  ensureDir(evidenceRoot(projectDir));
  const output = join(evidenceRoot(projectDir), `${runId}.json`);
  writeJsonFile(output, {
    schema: "EvidencePack",
    run_id: runId,
    created_at: new Date().toISOString(),
    tests: options.tests || [],
    security_scans: options.security_scans || [],
    diff_summary: options.diff_summary || {},
    reproducibility: options.reproducibility || {},
    unresolved_risks: options.unresolved_risks || []
  });
  return output;
}

export function hasRecentEvidence(projectDir: string, hours = 24): boolean {
  const base = evidenceRoot(projectDir);
  if (!existsSync(base)) {
    return false;
  }
  const maxAge = hours * 60 * 60 * 1000;
  return readdirSync(base).some((name) => {
    if (!name.endsWith(".json")) {
      return false;
    }
    const age = Date.now() - statSync(join(base, name)).mtimeMs;
    return age <= maxAge;
  });
}

export function recordShadowWrite(projectDir: string, runId: string, filePath: string, source = "tool") {
  const runDir = join(shadowRoot(projectDir), runId);
  const overlayPath = join(runDir, "overlay", relative(projectDir, filePath).replace(/\.\./g, "_up_"));
  ensureDir(join(runDir, "overlay"));
  if (existsSync(filePath)) {
    ensureDir(dirname(overlayPath));
    copyFileSync(filePath, overlayPath);
  }
  const manifestPath = join(runDir, "manifest.json");
  const manifest = existsSync(manifestPath)
    ? JSON.parse(readFileSync(manifestPath, "utf8"))
    : { run_id: runId, created_at: new Date().toISOString(), status: "open", files: [] };
  manifest.files = Array.isArray(manifest.files) ? manifest.files.filter((entry: any) => entry.file !== filePath) : [];
  manifest.files.push({
    file: filePath,
    shadow_file: relative(runDir, overlayPath),
    recorded_at: new Date().toISOString(),
    source
  });
  writeJsonFile(manifestPath, manifest);
  return manifest;
}

export function dropShadow(projectDir: string, runId: string) {
  const runDir = join(shadowRoot(projectDir), runId);
  rmSync(runDir, { recursive: true, force: true });
  return { run_id: runId, dropped: true };
}
