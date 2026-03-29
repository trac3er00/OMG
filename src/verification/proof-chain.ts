import type { ProofVerdict } from "../interfaces/evidence.js";
import type { ProofChainEntry } from "../types/evidence.js";

export interface ChainEntry {
  readonly step: string;
  readonly status: ProofVerdict;
  readonly evidenceType: string;
  readonly details?: unknown;
  readonly timestamp?: string;
}

export class ProofChain {
  readonly runId: string;
  private readonly chainEntries: ChainEntry[] = [];

  constructor(runId: string) {
    this.runId = runId;
  }

  addEntry(entry: Omit<ChainEntry, "timestamp">): void {
    this.chainEntries.push({
      ...entry,
      timestamp: new Date().toISOString(),
    });
  }

  entries(): readonly ChainEntry[] {
    return this.chainEntries;
  }

  overallStatus(): ProofVerdict {
    if (this.chainEntries.length === 0) {
      return "pending";
    }
    if (this.chainEntries.some((entry) => entry.status === "fail")) {
      return "fail";
    }
    if (this.chainEntries.some((entry) => entry.status === "blocked")) {
      return "blocked";
    }
    if (this.chainEntries.every((entry) => entry.status === "pass")) {
      return "pass";
    }
    return "pending";
  }

  toProofChainEntries(): readonly ProofChainEntry[] {
    return this.chainEntries.map((entry) => ({
      step: entry.step,
      evidence_type: entry.evidenceType,
      status: entry.status === "blocked" ? "pending" : entry.status,
      timestamp: entry.timestamp ?? new Date().toISOString(),
      ...(entry.details && typeof entry.details === "object"
        ? { details: entry.details as Record<string, unknown> }
        : {}),
    }));
  }
}
