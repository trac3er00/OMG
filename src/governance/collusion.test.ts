import { describe, test, expect } from "bun:test";
import {
  detectMutualApproval,
  detectGovernanceBypass,
  runCollusionDetection,
  CollusionIncidentSchema,
} from "./collusion.js";
import { type LedgerEntry } from "./ledger.js";

function makeEntry(
  agent: string,
  node: string,
  evidence: string[] = [],
): LedgerEntry {
  return {
    entry_id: `e-${Math.random()}`,
    timestamp: new Date().toISOString(),
    agent_id: agent,
    node_id: node,
    from_state: "planning",
    to_state: "implementing",
    evidence_refs: evidence,
    hash: "abc123",
    previous_hash: "000000",
  };
}

describe("governance/collusion", () => {
  describe("detectMutualApproval", () => {
    test("detects mutual approval without evidence", () => {
      const entries: LedgerEntry[] = [
        makeEntry("agent-a", "task-1"),
        makeEntry("agent-a", "task-2"),
        makeEntry("agent-b", "task-1"),
        makeEntry("agent-b", "task-2"),
      ];
      const incident = detectMutualApproval(entries);
      expect(incident).not.toBeNull();
      expect(incident?.pattern).toBe("mutual_approval_without_evidence");
      expect(incident?.agent_ids).toContain("agent-a");
      expect(incident?.agent_ids).toContain("agent-b");
    });

    test("does NOT flag agents with evidence", () => {
      const entries: LedgerEntry[] = [
        makeEntry("agent-a", "task-1", ["proof.json"]),
        makeEntry("agent-b", "task-1", ["proof.json"]),
      ];
      const incident = detectMutualApproval(entries);
      expect(incident).toBeNull();
    });

    test("single overlap not detected (threshold is 2)", () => {
      const entries: LedgerEntry[] = [
        makeEntry("agent-a", "task-1"),
        makeEntry("agent-b", "task-1"),
      ];
      const incident = detectMutualApproval(entries);
      expect(incident).toBeNull();
    });

    test("incident validates against schema", () => {
      const entries: LedgerEntry[] = [
        makeEntry("a", "t1"),
        makeEntry("a", "t2"),
        makeEntry("b", "t1"),
        makeEntry("b", "t2"),
      ];
      const incident = detectMutualApproval(entries);
      if (incident) {
        expect(CollusionIncidentSchema.safeParse(incident).success).toBe(true);
      }
    });
  });

  describe("detectGovernanceBypass", () => {
    test("detects systematic bypass (3+ times)", () => {
      const entries: LedgerEntry[] = [
        {
          ...makeEntry("agent-x", "t1"),
          from_state: "planning",
          to_state: "deploying",
        },
        {
          ...makeEntry("agent-x", "t2"),
          from_state: "planning",
          to_state: "deploying",
        },
        {
          ...makeEntry("agent-x", "t3"),
          from_state: "planning",
          to_state: "deploying",
        },
      ];
      const incident = detectGovernanceBypass(entries);
      expect(incident).not.toBeNull();
      expect(incident?.pattern).toBe("systematic_governance_bypass");
    });

    test("2 bypasses not flagged (below threshold)", () => {
      const entries: LedgerEntry[] = [
        {
          ...makeEntry("agent-x", "t1"),
          from_state: "planning",
          to_state: "deploying",
        },
        {
          ...makeEntry("agent-x", "t2"),
          from_state: "planning",
          to_state: "deploying",
        },
      ];
      expect(detectGovernanceBypass(entries)).toBeNull();
    });
  });

  describe("runCollusionDetection", () => {
    test("returns no incidents for clean entries", () => {
      const entries = [
        makeEntry("a", "t1", ["proof.json"]),
        makeEntry("b", "t2", ["proof.json"]),
      ];
      const result = runCollusionDetection(entries);
      expect(result.collusion_detected).toBe(false);
      expect(result.incidents.length).toBe(0);
    });

    test("detected collusion has sanction applied", () => {
      const entries: LedgerEntry[] = [
        makeEntry("a", "t1"),
        makeEntry("a", "t2"),
        makeEntry("b", "t1"),
        makeEntry("b", "t2"),
      ];
      const result = runCollusionDetection(entries);
      expect(result.collusion_detected).toBe(true);
      expect(result.incidents[0]?.sanction_applied).toBe(true);
    });

    test("tracks checked entries count", () => {
      const entries = Array.from({ length: 10 }, (_, i) =>
        makeEntry(`a${i}`, `t${i}`, ["e.json"]),
      );
      const result = runCollusionDetection(entries);
      expect(result.checked_entries).toBe(10);
    });
  });
});
