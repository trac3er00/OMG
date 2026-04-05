import { z } from "zod";
import {
  readdirSync,
  readFileSync,
  statSync,
  renameSync,
  mkdirSync,
  existsSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { join, basename } from "node:path";
import { gzipSync } from "node:zlib";
import { readJsonLines } from "../state/atomic-io.js";
import type { EvidenceRecord } from "./registry.js";

export const RETENTION_VERSION = "1.0.0";

export type RetentionAction = "archive" | "delete" | "keep";

export const RetentionPolicySchema = z.object({
  evidence_type: z.string(),
  retention_days: z.number().int().positive(),
  archive_strategy: z.enum(["archive", "delete"]),
  note: z.string().optional(),
});
export type RetentionPolicy = z.infer<typeof RetentionPolicySchema>;

export const DEFAULT_RETENTION_POLICIES: RetentionPolicy[] = [
  {
    evidence_type: "reliability_metrics",
    retention_days: 90,
    archive_strategy: "archive",
  },
  {
    evidence_type: "governance_ledger",
    retention_days: 365,
    archive_strategy: "archive",
    note: "append-only, archive only, never delete",
  },
  {
    evidence_type: "debate_transcripts",
    retention_days: 30,
    archive_strategy: "delete",
  },
  {
    evidence_type: "checkpoint_state",
    retention_days: 7,
    archive_strategy: "archive",
  },
  {
    evidence_type: "reproducibility",
    retention_days: 30,
    archive_strategy: "archive",
  },
  {
    evidence_type: "failure_reports",
    retention_days: 60,
    archive_strategy: "archive",
  },
  {
    evidence_type: "claim_judge",
    retention_days: 90,
    archive_strategy: "archive",
  },
  {
    evidence_type: "proof_gate",
    retention_days: 90,
    archive_strategy: "archive",
  },
];

export function applyRetentionPolicy(
  directory: string,
  policy: RetentionPolicy,
  archiveDir: string,
  now = Date.now(),
): { archived: number; deleted: number; kept: number } {
  if (!existsSync(directory)) return { archived: 0, deleted: 0, kept: 0 };

  let archived = 0;
  let deleted = 0;
  let kept = 0;
  const cutoffMs = policy.retention_days * 24 * 60 * 60 * 1000;

  const files = readdirSync(directory).filter(
    (f) => f.endsWith(".json") || f.endsWith(".jsonl"),
  );
  for (const file of files) {
    const filePath = join(directory, file);
    const stat = statSync(filePath);
    const ageMs = now - stat.mtimeMs;

    if (ageMs > cutoffMs) {
      if (policy.archive_strategy === "archive") {
        mkdirSync(archiveDir, { recursive: true });
        renameSync(filePath, join(archiveDir, file));
        archived++;
      } else {
        try {
          require("node:fs").unlinkSync(filePath);
          deleted++;
        } catch {
          archived++;
        }
      }
    } else {
      kept++;
    }
  }
  return { archived, deleted, kept };
}

export function getRetentionConfig(): RetentionPolicy[] {
  return DEFAULT_RETENTION_POLICIES;
}

export function parseDuration(spec: string): number {
  const match = spec.match(/^(\d+)(d|h|m)$/);
  if (!match)
    throw new Error(
      `Invalid duration format: "${spec}" (expected e.g. "30d", "24h", "60m")`,
    );
  const value = parseInt(match[1]!, 10);
  const unit = match[2]!;
  switch (unit) {
    case "d":
      return value * 24 * 60 * 60 * 1000;
    case "h":
      return value * 60 * 60 * 1000;
    case "m":
      return value * 60 * 1000;
    default:
      throw new Error(`Unknown duration unit: ${unit}`);
  }
}

export function compressFileSync(srcPath: string, destPath: string): void {
  const content = readFileSync(srcPath);
  const compressed = gzipSync(content);
  const destDir = join(destPath, "..");
  if (!existsSync(destDir)) mkdirSync(destDir, { recursive: true });
  writeFileSync(destPath, compressed);
}

export interface PruneOptions {
  evidenceDir: string;
  archiveDir: string;
  olderThanMs: number;
  now?: number;
}

export interface PruneResult {
  archived: string[];
  skipped: string[];
  totalSize: number;
}

export function pruneEvidence(options: PruneOptions): PruneResult {
  const { evidenceDir, archiveDir, olderThanMs, now = Date.now() } = options;
  const result: PruneResult = { archived: [], skipped: [], totalSize: 0 };

  if (!existsSync(evidenceDir)) return result;

  mkdirSync(archiveDir, { recursive: true });

  const files = readdirSync(evidenceDir).filter(
    (f) => f.endsWith(".json") || f.endsWith(".jsonl") || f.endsWith(".txt"),
  );

  for (const file of files) {
    const filePath = join(evidenceDir, file);
    const stat = statSync(filePath);
    const ageMs = now - stat.mtimeMs;

    if (ageMs > olderThanMs) {
      const archiveName = `${basename(file)}.gz`;
      const archivePath = join(archiveDir, archiveName);
      compressFileSync(filePath, archivePath);
      unlinkSync(filePath);
      result.archived.push(file);
      result.totalSize += stat.size;
    } else {
      result.skipped.push(file);
    }
  }

  return result;
}

export type EvidenceType =
  | "security"
  | "test"
  | "build"
  | "governance"
  | "planning";

export const EVIDENCE_TYPES: readonly EvidenceType[] = [
  "security",
  "test",
  "build",
  "governance",
  "planning",
] as const;

export interface QueryOptions {
  registryPath: string;
  sinceMs?: number;
  type?: string;
  now?: number;
}

export interface QueryResult {
  records: EvidenceRecord[];
  total: number;
  filtered: number;
}

export function queryEvidence(options: QueryOptions): QueryResult {
  const { registryPath, sinceMs, type, now = Date.now() } = options;

  const allRecords = readJsonLines<EvidenceRecord>(registryPath);
  let filtered = allRecords;

  if (type) {
    filtered = filtered.filter((r) => r.type === type);
  }

  if (sinceMs !== undefined) {
    const cutoff = now - sinceMs;
    filtered = filtered.filter((r) => {
      if (!r.timestamp) return false;
      return new Date(r.timestamp).getTime() >= cutoff;
    });
  }

  return {
    records: filtered,
    total: allRecords.length,
    filtered: filtered.length,
  };
}
