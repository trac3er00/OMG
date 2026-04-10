import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdirSync, rmSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import {
  GovernanceLedger,
  LedgerEntrySchema,
  LEDGER_VERSION,
} from "./ledger.js";

const TEST_DIR = "/tmp/omg-ledger-test";

beforeEach(() => {
  rmSync(TEST_DIR, { recursive: true, force: true });
  mkdirSync(join(TEST_DIR, ".omg", "state"), { recursive: true });
});
afterEach(() => rmSync(TEST_DIR, { recursive: true, force: true }));

describe("governance/ledger", () => {
  test("LEDGER_VERSION is 1.0.0", () => {
    expect(LEDGER_VERSION).toBe("1.0.0");
  });

  describe("GovernanceLedger.append", () => {
    test("creates first entry with genesis previous_hash", () => {
      const ledger = new GovernanceLedger(TEST_DIR);
      const entry = ledger.append({
        agent_id: "agent-a",
        node_id: "task-1",
        from_state: "planning",
        to_state: "implementing",
      });
      expect(entry.previous_hash).toBe("0000000000000000");
      expect(entry.hash).toBeDefined();
      expect(LedgerEntrySchema.safeParse(entry).success).toBe(true);
    });

    test("second entry chains from first entry's hash", () => {
      const ledger = new GovernanceLedger(TEST_DIR);
      const e1 = ledger.append({
        agent_id: "agent-a",
        node_id: "t1",
        from_state: "planning",
        to_state: "implementing",
      });
      const e2 = ledger.append({
        agent_id: "agent-a",
        node_id: "t1",
        from_state: "implementing",
        to_state: "reviewing",
      });
      expect(e2.previous_hash).toBe(e1.hash);
    });

    test("entries are persisted to JSONL file", () => {
      const ledger = new GovernanceLedger(TEST_DIR);
      ledger.append({
        agent_id: "a",
        node_id: "t1",
        from_state: "planning",
        to_state: "implementing",
      });
      ledger.append({
        agent_id: "a",
        node_id: "t1",
        from_state: "implementing",
        to_state: "reviewing",
      });
      const entries = ledger.readAll();
      expect(entries.length).toBe(2);
    });

    test("entry round-trip matches persisted JSONL record", () => {
      const ledger = new GovernanceLedger(TEST_DIR);
      const written = ledger.append({
        agent_id: "agent-a",
        node_id: "task-round-trip",
        from_state: "planning",
        to_state: "implementing",
        evidence_refs: ["proof:test"],
      });

      const [readBack] = ledger.readAll();
      expect(readBack).toEqual(written);
    });
  });

  describe("GovernanceLedger.verifyIntegrity", () => {
    test("valid ledger passes integrity check", () => {
      const ledger = new GovernanceLedger(TEST_DIR);
      for (let i = 0; i < 5; i++) {
        ledger.append({
          agent_id: "agent-a",
          node_id: `t${i}`,
          from_state: "planning",
          to_state: "implementing",
        });
      }
      const result = ledger.verifyIntegrity();
      expect(result.valid).toBe(true);
    });

    test("tampered entry is detected", () => {
      const ledger = new GovernanceLedger(TEST_DIR);
      ledger.append({
        agent_id: "agent-a",
        node_id: "t1",
        from_state: "planning",
        to_state: "implementing",
      });
      ledger.append({
        agent_id: "agent-a",
        node_id: "t2",
        from_state: "implementing",
        to_state: "reviewing",
      });

      const ledgerPath = join(
        TEST_DIR,
        ".omg",
        "state",
        "governance-ledger.jsonl",
      );
      const lines = readFileSync(ledgerPath, "utf8")
        .split("\n")
        .filter(Boolean);
      const entry1 = JSON.parse(lines[0]!);
      entry1.agent_id = "tampered-agent";
      lines[0] = JSON.stringify(entry1);
      writeFileSync(ledgerPath, lines.join("\n") + "\n");

      const result = new GovernanceLedger(TEST_DIR).verifyIntegrity();
      expect(result.valid).toBe(false);
      expect(result.tampered_index).toBeDefined();
    });

    test("empty ledger passes integrity check", () => {
      const ledger = new GovernanceLedger(TEST_DIR);
      expect(ledger.verifyIntegrity().valid).toBe(true);
    });
  });

  describe("GovernanceLedger.readAll", () => {
    test("returns empty array when no ledger file", () => {
      const ledger = new GovernanceLedger(TEST_DIR);
      expect(ledger.readAll()).toEqual([]);
    });

    test("returns all entries in order", () => {
      const ledger = new GovernanceLedger(TEST_DIR);
      ledger.append({
        agent_id: "a",
        node_id: "t1",
        from_state: "planning",
        to_state: "implementing",
      });
      ledger.append({
        agent_id: "a",
        node_id: "t1",
        from_state: "implementing",
        to_state: "reviewing",
      });
      const entries = ledger.readAll();
      expect(entries.length).toBe(2);
      expect(entries[0]?.to_state).toBe("implementing");
      expect(entries[1]?.to_state).toBe("reviewing");
    });
  });
});
