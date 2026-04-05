/**
 * Runtime contracts: state directory layout, schema versions, run IDs.
 *
 * Mirrors runtime/runtime_contracts.py exactly for state compatibility.
 * All modules must use these paths — never hardcode .omg/state/ locations.
 */

import { join, resolve } from "node:path";
import { randomUUID } from "node:crypto";

// ---------------------------------------------------------------------------
// Module names — the 9 canonical state modules from Python
// ---------------------------------------------------------------------------

/** Supported module names matching Python's _MODULES tuple. */
export type ModuleName =
  | "verification_controller"
  | "release_run_coordinator"
  | "interaction_journal"
  | "context_engine"
  | "defense_state"
  | "session_health"
  | "council_verdicts"
  | "rollback_manifest"
  | "release_run";

// ---------------------------------------------------------------------------
// Schema version tracking (simplified from Python's SchemaVersion TypedDict)
// ---------------------------------------------------------------------------

/** Compact schema version record for migration detection. */
export interface ContractSchemaVersion {
  readonly module: string;
  readonly version: number;
}

/** Current schema version for each module. */
const SCHEMA_VERSION_MAP: Record<ModuleName, number> = {
  verification_controller: 2,
  release_run_coordinator: 1,
  interaction_journal: 1,
  context_engine: 3,
  defense_state: 2,
  session_health: 1,
  council_verdicts: 1,
  rollback_manifest: 1,
  release_run: 1,
};

// ---------------------------------------------------------------------------
// State layout — canonical paths for all modules
// ---------------------------------------------------------------------------

/**
 * Returns the canonical state file/directory paths for all modules.
 * Matches Python's runtime_contracts.default_layout() path structure.
 *
 * @example
 * const layout = defaultLayout("/my/project");
 * const defenseStatePath = layout.defense_state;
 * // "/my/project/.omg/state/defense_state.json"
 */
export function defaultLayout(projectDir: string): Record<ModuleName, string> {
  const stateDir = join(resolve(projectDir), ".omg", "state");

  return {
    verification_controller: join(stateDir, "verification_controller"),
    release_run_coordinator: join(stateDir, "release_run_coordinator"),
    interaction_journal: join(stateDir, "interaction_journal"),
    context_engine: join(stateDir, "context_engine_packet.json"),
    defense_state: join(stateDir, "defense_state.json"),
    session_health: join(stateDir, "session_health.json"),
    council_verdicts: join(stateDir, "council_verdicts"),
    rollback_manifest: join(stateDir, "rollback_manifest.json"),
    release_run: join(stateDir, "release_run"),
  };
}

// ---------------------------------------------------------------------------
// Schema versions
// ---------------------------------------------------------------------------

/**
 * Returns schema metadata for all runtime modules.
 * Used for schema migration detection.
 *
 * @example
 * const versions = schemaVersions();
 * if (versions.defense_state.version > currentVersion) { migrate(); }
 */
export function schemaVersions(): Record<ModuleName, ContractSchemaVersion> {
  const result = {} as Record<ModuleName, ContractSchemaVersion>;

  for (const [moduleName, version] of Object.entries(SCHEMA_VERSION_MAP) as [ModuleName, number][]) {
    result[moduleName] = {
      module: moduleName,
      version,
    };
  }

  return result;
}

// ---------------------------------------------------------------------------
// Run ID generation and normalization
// ---------------------------------------------------------------------------

/**
 * Normalize a run ID to a safe, deterministic format.
 * Mirrors runtime/forge_run_id.py normalization logic.
 *
 * Strips unsafe chars, enforces max length, replaces separators.
 */
export function normalizeRunId(runId: string, maxLength = 128): string {
  if (!runId || typeof runId !== "string") {
    return generateRunId();
  }

  return runId
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]/g, "-")
    .replace(/\.{2,}/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, maxLength);
}

/**
 * Generate a new unique run ID.
 * Format: omg-<uuid-v4-short> (16 hex chars)
 */
export function generateRunId(): string {
  const id = randomUUID().replace(/-/g, "").slice(0, 16);
  return `omg-${id}`;
}

// ---------------------------------------------------------------------------
// Provenance tracking (mirrors merge_writer.py provenance shape)
// ---------------------------------------------------------------------------

/** Provenance record for merge writer tracking. */
export interface ProvenanceRecord {
  readonly runId: string;
  readonly module: ModuleName;
  readonly operation: "write" | "update" | "delete";
  readonly path: string;
  readonly timestamp: string;
  readonly schemaVersion: number;
}

/**
 * Create a provenance record for a state write operation.
 */
export function createProvenance(
  runId: string,
  module: ModuleName,
  operation: ProvenanceRecord["operation"],
  path: string,
): ProvenanceRecord {
  return {
    runId,
    module,
    operation,
    path,
    timestamp: new Date().toISOString(),
    schemaVersion: SCHEMA_VERSION_MAP[module],
  };
}
