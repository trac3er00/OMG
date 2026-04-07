import { describe, test, expect } from "bun:test";
import { mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  detectMutualApproval,
  detectGovernanceBypass,
  runCollusionDetection,
  CollusionIncidentSchema,
  detectCollusion,
} from "./collusion.js";
import { GovernanceLedger, type LedgerEntry } from "./ledger.js";

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

  describe("enforcement integration", () => {
    test("enforcement", () => {
      const projectDir = join(
        tmpdir(),
        `omg-collusion-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      );
      mkdirSync(join(projectDir, ".omg", "state"), { recursive: true });
      const ledger = new GovernanceLedger(projectDir);

      try {
        ledger.append({
          agent_id: "agent-a",
          node_id: "task-1",
          from_state: "planning",
          to_state: "implementing",
        });
        ledger.append({
          agent_id: "agent-a",
          node_id: "task-2",
          from_state: "planning",
          to_state: "implementing",
        });
        ledger.append({
          agent_id: "agent-b",
          node_id: "task-1",
          from_state: "planning",
          to_state: "implementing",
        });
        ledger.append({
          agent_id: "agent-b",
          node_id: "task-2",
          from_state: "planning",
          to_state: "implementing",
        });

        const result = detectCollusion(["agent-a", "agent-b"], { ledger });
        expect(result.detected).toBe(true);
        expect(result.requiresElevatedApproval).toBe(true);
        expect(result.action).toBe("warn");
      } finally {
        rmSync(projectDir, { recursive: true, force: true });
      }
    });

    test("detection-recorded", () => {
      const projectDir = join(
        tmpdir(),
        `omg-collusion-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      );
      mkdirSync(join(projectDir, ".omg", "state"), { recursive: true });
      const ledger = new GovernanceLedger(projectDir);

      try {
        ledger.append({
          agent_id: "agent-a",
          node_id: "task-1",
          from_state: "planning",
          to_state: "implementing",
        });
        ledger.append({
          agent_id: "agent-a",
          node_id: "task-2",
          from_state: "planning",
          to_state: "implementing",
        });
        ledger.append({
          agent_id: "agent-b",
          node_id: "task-1",
          from_state: "planning",
          to_state: "implementing",
        });
        ledger.append({
          agent_id: "agent-b",
          node_id: "task-2",
          from_state: "planning",
          to_state: "implementing",
        });

        detectCollusion(["agent-a", "agent-b"], {
          ledger,
          taskId: "dispatch-123",
        });

        const entries = ledger.readAll();
        expect(entries.at(-1)?.agent_id).toBe("governance-collusion");
        expect(entries.at(-1)?.node_id).toBe("dispatch-123");
      } finally {
        rmSync(projectDir, { recursive: true, force: true });
      }
    });
  });
});
