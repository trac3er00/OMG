import { z } from "zod";
import {
  readdirSync,
  statSync,
  renameSync,
  mkdirSync,
  existsSync,
} from "node:fs";
import { join } from "node:path";

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
