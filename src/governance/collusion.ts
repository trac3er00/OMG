import { z } from "zod";
import { type LedgerEntry } from "./ledger.js";

export const COLLUSION_DETECTION_VERSION = "1.0.0";
export const EVIDENCE_THRESHOLD = 0.7;

export type CollusionPatternType =
  | "mutual_approval_without_evidence"
  | "systematic_governance_bypass"
  | "coordinated_uniform_decisions";

export const CollusionIncidentSchema = z.object({
  pattern: z.enum([
    "mutual_approval_without_evidence",
    "systematic_governance_bypass",
    "coordinated_uniform_decisions",
  ]),
  agent_ids: z.array(z.string()),
  evidence: z.array(z.string()),
  severity: z.enum(["low", "medium", "high"]),
  detected_at: z.string(),
  sanction_applied: z.boolean(),
  sanction_type: z.string().optional(),
});
export type CollusionIncident = z.infer<typeof CollusionIncidentSchema>;

export interface DetectionResult {
  readonly incidents: readonly CollusionIncident[];
  readonly collusion_detected: boolean;
  readonly checked_entries: number;
}

export function detectMutualApproval(
  entries: readonly LedgerEntry[],
): CollusionIncident | null {
  const approvalMap = new Map<string, Set<string>>();

  for (const entry of entries) {
    if (entry.evidence_refs.length === 0) {
      if (!approvalMap.has(entry.agent_id)) {
        approvalMap.set(entry.agent_id, new Set());
      }
      approvalMap.get(entry.agent_id)!.add(entry.node_id);
    }
  }

  const agents = [...approvalMap.keys()];
  for (let i = 0; i < agents.length; i++) {
    for (let j = i + 1; j < agents.length; j++) {
      const agentA = agents[i]!;
      const agentB = agents[j]!;
      const aNodes = approvalMap.get(agentA)!;
      const bNodes = approvalMap.get(agentB)!;

      const overlap = [...aNodes].filter((n) => bNodes.has(n));
      if (overlap.length >= 2) {
        return CollusionIncidentSchema.parse({
          pattern: "mutual_approval_without_evidence",
          agent_ids: [agentA, agentB],
          evidence: overlap.map((n) => `node:${n}`),
          severity: "high",
          detected_at: new Date().toISOString(),
          sanction_applied: false,
        });
      }
    }
  }
  return null;
}

export function detectGovernanceBypass(
  entries: readonly LedgerEntry[],
): CollusionIncident | null {
  const agentBypassCount = new Map<string, number>();
  for (const entry of entries) {
    if (entry.from_state === "planning" && entry.to_state === "deploying") {
      agentBypassCount.set(
        entry.agent_id,
        (agentBypassCount.get(entry.agent_id) ?? 0) + 1,
      );
    }
  }

  for (const [agentId, count] of agentBypassCount) {
    if (count >= 3) {
      return CollusionIncidentSchema.parse({
        pattern: "systematic_governance_bypass",
        agent_ids: [agentId],
        evidence: Array.from({ length: count }, (_, i) => `bypass-${i + 1}`),
        severity: "high",
        detected_at: new Date().toISOString(),
        sanction_applied: false,
      });
    }
  }
  return null;
}

export function detectCoordinatedDecisions(
  entries: readonly LedgerEntry[],
): CollusionIncident | null {
  const stateMap = new Map<string, string[]>();
  for (const entry of entries) {
    const key = `${entry.from_state}→${entry.to_state}`;
    if (!stateMap.has(key)) stateMap.set(key, []);
    stateMap.get(key)!.push(entry.agent_id);
  }

  for (const [transition, agents] of stateMap) {
    const uniqueAgents = new Set(agents);
    if (uniqueAgents.size >= 3 && agents.length >= uniqueAgents.size * 2) {
      return CollusionIncidentSchema.parse({
        pattern: "coordinated_uniform_decisions",
        agent_ids: [...uniqueAgents],
        evidence: [`transition:${transition}`, `count:${agents.length}`],
        severity: "medium",
        detected_at: new Date().toISOString(),
        sanction_applied: false,
      });
    }
  }
  return null;
}

export function runCollusionDetection(
  entries: readonly LedgerEntry[],
): DetectionResult {
  const incidents: CollusionIncident[] = [];

  const mutual = detectMutualApproval(entries);
  if (mutual)
    incidents.push({
      ...mutual,
      sanction_applied: true,
      sanction_type: "rollback_to_last_verified",
    });

  const bypass = detectGovernanceBypass(entries);
  if (bypass)
    incidents.push({
      ...bypass,
      sanction_applied: true,
      sanction_type: "lock_agent",
    });

  const coordinated = detectCoordinatedDecisions(entries);
  if (coordinated) incidents.push({ ...coordinated, sanction_applied: false });

  return {
    incidents,
    collusion_detected: incidents.length > 0,
    checked_entries: entries.length,
  };
}
