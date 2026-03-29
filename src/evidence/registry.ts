import { appendJsonLine, readJsonLines } from "../state/atomic-io.js";
import { StateResolver } from "../state/state-resolver.js";
import { join } from "node:path";

export interface EvidenceRecord {
  readonly type: string;
  readonly runId: string;
  readonly path: string;
  readonly valid: boolean;
  readonly timestamp?: string;
  readonly metadata?: Readonly<Record<string, unknown>>;
}

export class EvidenceRegistry {
  private readonly registryPath: string;
  private readonly cache: EvidenceRecord[] = [];

  constructor(projectDir: string) {
    const resolver = new StateResolver(projectDir);
    this.registryPath = resolver.resolve(join("ledger", "evidence-registry.jsonl"));
    this.cache.push(...readJsonLines<EvidenceRecord>(this.registryPath));
  }

  register(record: Omit<EvidenceRecord, "timestamp">): void {
    const full: EvidenceRecord = { ...record, timestamp: new Date().toISOString() };
    this.cache.push(full);
    appendJsonLine(this.registryPath, full);
  }

  findByType(type: string): readonly EvidenceRecord[] {
    return this.cache.filter((r) => r.type === type);
  }

  findByRun(runId: string): readonly EvidenceRecord[] {
    return this.cache.filter((r) => r.runId === runId);
  }

  hasRequired(requiredTypes: readonly string[]): boolean {
    const available = new Set(this.cache.map((r) => r.type));
    return requiredTypes.every((t) => available.has(t));
  }

  all(): readonly EvidenceRecord[] {
    return this.cache;
  }
}
