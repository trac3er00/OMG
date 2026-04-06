import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, relative, resolve } from "node:path";

export interface MigrationReport {
  readonly files_affected: string[];
  readonly changes_required: Record<string, unknown>;
  readonly rollback_path: string;
  readonly errors: string[];
}

export interface MigrationOptions {
  readonly from: string;
  readonly to: string;
  readonly projectDir?: string;
  readonly apply?: boolean;
  readonly dryRun?: boolean;
}

const SUPPORTED_TRANSITION = {
  from: "2.3.0",
  to: "3.0.0",
} as const;

export const CANONICAL_STATE_SCHEMA_VERSIONS: Record<string, string> = {
  verification_controller: "1.0.0",
  release_run_coordinator: "1.0.0",
  interaction_journal: "1.0.0",
  context_engine: "1.0.0",
  defense_state: "1.0.0",
  session_health: "1.0.0",
  council_verdicts: "1.0.0",
  rollback_manifest: "1.0.0",
  release_run: "1.0.0",
};

const PRESET_NAMES = new Set([
  "safe",
  "balanced",
  "interop",
  "labs",
  "buffet",
  "production",
  "minimal",
  "standard",
  "full",
  "experimental",
]);

interface PlannedFileChange {
  readonly absolutePath: string;
  readonly nextContent: string;
  readonly reason: string;
}

function readJsonSafe(path: string): Record<string, unknown> | null {
  if (!existsSync(path)) {
    return null;
  }
  try {
    const raw = readFileSync(path, "utf8").trim();
    if (!raw) {
      return {};
    }
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      !Array.isArray(parsed)
    ) {
      return parsed as Record<string, unknown>;
    }
    return null;
  } catch {
    return null;
  }
}

function collectJsonFiles(dir: string): string[] {
  if (!existsSync(dir)) {
    return [];
  }
  const output: string[] = [];
  const stack = [dir];

  while (stack.length > 0) {
    const current = stack.pop()!;
    const entries = readdirSync(current, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(fullPath);
      } else if (entry.isFile() && entry.name.endsWith(".json")) {
        output.push(fullPath);
      }
    }
  }

  output.sort();
  return output;
}

function detectSettingsMigration(
  settingsPath: string,
): PlannedFileChange | null {
  const settings = readJsonSafe(settingsPath);
  if (!settings) {
    return null;
  }

  const currentOmg =
    typeof settings["_omg"] === "object" && settings["_omg"] !== null
      ? (settings["_omg"] as Record<string, unknown>)
      : {};
  const currentPreset =
    typeof currentOmg["preset"] === "string" ? currentOmg["preset"] : undefined;

  if (currentPreset && PRESET_NAMES.has(currentPreset)) {
    return null;
  }

  const nextOmg: Record<string, unknown> = {
    ...currentOmg,
    preset: "standard",
  };
  const next = { ...settings, _omg: nextOmg };

  return {
    absolutePath: settingsPath,
    nextContent: JSON.stringify(next, null, 2) + "\n",
    reason: "normalize _omg.preset to a v3-supported preset",
  };
}

function detectMcpJsonMigration(filePath: string): PlannedFileChange | null {
  const parsed = readJsonSafe(filePath);
  if (!parsed) {
    return null;
  }

  const servers =
    typeof parsed["mcpServers"] === "object" && parsed["mcpServers"] !== null
      ? { ...(parsed["mcpServers"] as Record<string, unknown>) }
      : {};

  if (
    typeof servers["omg-control"] === "object" &&
    servers["omg-control"] !== null
  ) {
    return null;
  }

  servers["omg-control"] = {
    command: "bunx",
    args: ["@trac3r/oh-my-god"],
  };

  const next = {
    ...parsed,
    mcpServers: servers,
  };

  return {
    absolutePath: filePath,
    nextContent: JSON.stringify(next, null, 2) + "\n",
    reason: "ensure omg-control MCP server is registered",
  };
}

function detectCodexTomlMigration(filePath: string): PlannedFileChange | null {
  if (!existsSync(filePath)) {
    return null;
  }
  const content = readFileSync(filePath, "utf8");
  if (content.includes("[mcp_servers.omg-control]")) {
    return null;
  }

  const appendix = [
    "",
    "[mcp_servers.omg-control]",
    'command = "bunx"',
    'args = ["@trac3r/oh-my-god"]',
    "",
  ].join("\n");

  return {
    absolutePath: filePath,
    nextContent: content + appendix,
    reason: "append omg-control MCP server for codex",
  };
}

function atomicWriteText(path: string, content: string): void {
  mkdirSync(dirname(path), { recursive: true });
  const tmpPath = `${path}.tmp-${process.pid}-${Date.now()}`;
  writeFileSync(tmpPath, content, { encoding: "utf8", mode: 0o600 });
  renameSync(tmpPath, path);
}

function backupFile(
  path: string,
  backupRoot: string,
  projectDir: string,
): void {
  const rel = relative(projectDir, path);
  const backupPath = join(backupRoot, rel);
  mkdirSync(dirname(backupPath), { recursive: true });
  copyFileSync(path, backupPath);
}

export function migrateConfig(options: MigrationOptions): MigrationReport {
  const projectDir = resolve(options.projectDir ?? process.cwd());
  const apply = options.apply === true;
  const dryRun = options.dryRun !== false;
  const errors: string[] = [];

  if (
    options.from !== SUPPORTED_TRANSITION.from ||
    options.to !== SUPPORTED_TRANSITION.to
  ) {
    return {
      files_affected: [],
      changes_required: {},
      rollback_path: "",
      errors: [
        `unsupported transition ${options.from} -> ${options.to}; supported transition is ${SUPPORTED_TRANSITION.from} -> ${SUPPORTED_TRANSITION.to}`,
      ],
    };
  }

  if (apply && dryRun) {
    return {
      files_affected: [],
      changes_required: {},
      rollback_path: "",
      errors: ["choose one mode: --apply or --dry-run"],
    };
  }

  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const rollbackPath = join(
    projectDir,
    ".omg",
    "backups",
    "migrations",
    `${options.from}-to-${options.to}-${stamp}`,
  );

  const plannedChanges: PlannedFileChange[] = [];
  const changesRequired: Record<string, unknown> = {
    transition: `${options.from}->${options.to}`,
    canonical_state_schemas: CANONICAL_STATE_SCHEMA_VERSIONS,
    state_inventory: {},
    config_updates: {},
  };

  const settingsPath = join(projectDir, "settings.json");
  const mcpPath = join(projectDir, ".mcp.json");
  const geminiPath = join(projectDir, ".gemini", "settings.json");
  const kimiPath = join(projectDir, ".kimi", "mcp.json");
  const codexPath = join(projectDir, ".codex", "config.toml");
  const presetMatrixPath = join(projectDir, "preset-matrix.json");
  const stateDir = join(projectDir, ".omg", "state");

  const stateInventory: Record<string, unknown> = {};
  for (const path of collectJsonFiles(stateDir)) {
    const parsed = readJsonSafe(path);
    const moduleName = relative(stateDir, path);
    if (!parsed) {
      stateInventory[moduleName] = { status: "invalid_json" };
      continue;
    }

    const schemaName =
      typeof parsed["schema"] === "string" ? parsed["schema"] : null;
    const schemaVersion =
      typeof parsed["schema_version"] === "string"
        ? parsed["schema_version"]
        : null;
    stateInventory[moduleName] = {
      schema: schemaName,
      schema_version: schemaVersion,
      expected_modules: Object.keys(CANONICAL_STATE_SCHEMA_VERSIONS),
    };
  }
  changesRequired["state_inventory"] = stateInventory;

  const maybeSettings = detectSettingsMigration(settingsPath);
  if (maybeSettings) {
    plannedChanges.push(maybeSettings);
  }

  for (const mcpFile of [mcpPath, geminiPath, kimiPath]) {
    const change = detectMcpJsonMigration(mcpFile);
    if (change) {
      plannedChanges.push(change);
    }
  }

  const codexChange = detectCodexTomlMigration(codexPath);
  if (codexChange) {
    plannedChanges.push(codexChange);
  }

  if (existsSync(presetMatrixPath)) {
    const presetRaw = readJsonSafe(presetMatrixPath);
    changesRequired["preset_config"] = {
      path: relative(projectDir, presetMatrixPath),
      status: presetRaw ? "detected" : "invalid_json",
    };
  } else {
    changesRequired["preset_config"] = {
      path: relative(projectDir, presetMatrixPath),
      status: "missing",
    };
  }

  for (const change of plannedChanges) {
    const relPath = relative(projectDir, change.absolutePath);
    (changesRequired["config_updates"] as Record<string, unknown>)[relPath] = {
      action: "update",
      reason: change.reason,
    };
  }

  if (apply) {
    try {
      mkdirSync(rollbackPath, { recursive: true });
      for (const change of plannedChanges) {
        if (existsSync(change.absolutePath)) {
          backupFile(change.absolutePath, rollbackPath, projectDir);
        }
        atomicWriteText(change.absolutePath, change.nextContent);
      }
    } catch (error) {
      errors.push(error instanceof Error ? error.message : String(error));
    }
  }

  const filesAffected = plannedChanges.map((change) =>
    relative(projectDir, change.absolutePath),
  );

  return {
    files_affected: filesAffected,
    changes_required: changesRequired,
    rollback_path: rollbackPath,
    errors,
  };
}
