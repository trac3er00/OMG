import { z } from "zod";
import { createHash } from "node:crypto";
import {
  appendFileSync,
  readFileSync,
  existsSync,
  mkdirSync,
  renameSync,
} from "node:fs";
import { join, dirname } from "node:path";

export const LEDGER_VERSION = "1.0.0";
export const LEDGER_MAX_BYTES = 10 * 1024 * 1024;
const GENESIS_HASH = "0000000000000000";

export const LedgerEntrySchema = z.object({
  entry_id: z.string(),
  timestamp: z.string(),
  agent_id: z.string(),
  node_id: z.string(),
  from_state: z.string(),
  to_state: z.string(),
  evidence_refs: z.array(z.string()),
  hash: z.string(),
  previous_hash: z.string(),
});
export type LedgerEntry = z.infer<typeof LedgerEntrySchema>;

function hashEntry(entry: Omit<LedgerEntry, "hash">): string {
  const content = JSON.stringify({
    entry_id: entry.entry_id,
    timestamp: entry.timestamp,
    agent_id: entry.agent_id,
    node_id: entry.node_id,
    from_state: entry.from_state,
    to_state: entry.to_state,
    evidence_refs: entry.evidence_refs,
    previous_hash: entry.previous_hash,
  });
  return createHash("sha256").update(content).digest("hex").slice(0, 32);
}

export class GovernanceLedger {
  private readonly ledgerPath: string;
  private readonly archivePath: string;
  private lastHash: string = GENESIS_HASH;
  private entryCount = 0;

  constructor(projectDir: string) {
    this.ledgerPath = join(
      projectDir,
      ".omg",
      "state",
      "governance-ledger.jsonl",
    );
    this.archivePath = join(
      projectDir,
      ".omg",
      "state",
      "governance-ledger-archive.jsonl",
    );
    this.loadLastHash();
  }

  append(opts: {
    agent_id: string;
    node_id: string;
    from_state: string;
    to_state: string;
    evidence_refs?: string[];
  }): LedgerEntry {
    const entry_id = `entry-${Date.now()}-${this.entryCount++}`;
    const entryWithoutHash = {
      entry_id,
      timestamp: new Date().toISOString(),
      agent_id: opts.agent_id,
      node_id: opts.node_id,
      from_state: opts.from_state,
      to_state: opts.to_state,
      evidence_refs: opts.evidence_refs ?? [],
      previous_hash: this.lastHash,
    };

    const hash = hashEntry(entryWithoutHash);
    const entry = LedgerEntrySchema.parse({ ...entryWithoutHash, hash });

    mkdirSync(dirname(this.ledgerPath), { recursive: true });
    appendFileSync(this.ledgerPath, JSON.stringify(entry) + "\n");
    this.lastHash = hash;
    this.checkRotation();

    return entry;
  }

  verifyIntegrity(): { valid: boolean; tampered_index?: number } {
    if (!existsSync(this.ledgerPath)) return { valid: true };

    const lines = readFileSync(this.ledgerPath, "utf8")
      .trim()
      .split("\n")
      .filter(Boolean);
    let prevHash = GENESIS_HASH;

    for (let i = 0; i < lines.length; i++) {
      const entry = JSON.parse(lines[i]!) as LedgerEntry;
      if (entry.previous_hash !== prevHash) {
        return { valid: false, tampered_index: i };
      }
      const expectedHash = hashEntry({
        entry_id: entry.entry_id,
        timestamp: entry.timestamp,
        agent_id: entry.agent_id,
        node_id: entry.node_id,
        from_state: entry.from_state,
        to_state: entry.to_state,
        evidence_refs: entry.evidence_refs,
        previous_hash: entry.previous_hash,
      });
      if (expectedHash !== entry.hash) {
        return { valid: false, tampered_index: i };
      }
      prevHash = entry.hash;
    }

    return { valid: true };
  }

  readAll(): LedgerEntry[] {
    if (!existsSync(this.ledgerPath)) return [];
    return readFileSync(this.ledgerPath, "utf8")
      .trim()
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line) as LedgerEntry);
  }

  private loadLastHash(): void {
    if (!existsSync(this.ledgerPath)) return;
    const lines = readFileSync(this.ledgerPath, "utf8")
      .trim()
      .split("\n")
      .filter(Boolean);
    if (lines.length === 0) return;
    const lastLine = lines[lines.length - 1]!;
    const last = JSON.parse(lastLine) as LedgerEntry;
    this.lastHash = last.hash;
    this.entryCount = lines.length;
  }

  private checkRotation(): void {
    if (!existsSync(this.ledgerPath)) return;
    const size = readFileSync(this.ledgerPath).byteLength;
    if (size >= LEDGER_MAX_BYTES) {
      renameSync(this.ledgerPath, this.archivePath);
      this.lastHash = GENESIS_HASH;
    }
  }
}
