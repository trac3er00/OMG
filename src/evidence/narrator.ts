import type { EvidenceRecord } from "./registry.js";

export class EvidenceNarrator {
  narrate(evidence: readonly EvidenceRecord[]): string {
    if (evidence.length === 0) return "No evidence available.";

    const byType = new Map<string, EvidenceRecord[]>();
    for (const e of evidence) {
      const existing = byType.get(e.type) ?? [];
      existing.push(e);
      byType.set(e.type, existing);
    }

    const lines: string[] = [`Evidence summary (${evidence.length} items):`];
    for (const [type, records] of byType) {
      const valid = records.filter((r) => r.valid).length;
      lines.push(`  - ${type}: ${valid}/${records.length} valid`);
    }
    return lines.join("\n");
  }

  narrateMissing(missing: readonly string[]): string {
    if (missing.length === 0) return "All required evidence is present.";
    return `Cannot confirm done - missing: ${missing.join(", ")}`;
  }
}
