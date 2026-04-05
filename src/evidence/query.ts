import { EvidenceRegistry, type EvidenceRecord } from "./registry.js";

export class EvidenceQuery {
  private readonly registry: EvidenceRegistry;

  constructor(projectDirOrRegistry: string | EvidenceRegistry) {
    this.registry =
      typeof projectDirOrRegistry === "string"
        ? new EvidenceRegistry(projectDirOrRegistry)
        : projectDirOrRegistry;
  }

  byType(type: string): readonly EvidenceRecord[] {
    return this.registry.findByType(type);
  }

  byRun(runId: string): readonly EvidenceRecord[] {
    return this.registry.findByRun(runId);
  }

  hasAll(requiredTypes: readonly string[]): boolean {
    return this.registry.hasRequired(requiredTypes);
  }

  byDateRange(from: string, to: string): readonly EvidenceRecord[] {
    const fromMs = new Date(from).getTime();
    const toMs = new Date(to).getTime();
    return this.registry.all().filter((r) => {
      if (!r.timestamp) return false;
      const ts = new Date(r.timestamp).getTime();
      return ts >= fromMs && ts <= toMs;
    });
  }
}
