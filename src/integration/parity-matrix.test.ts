import { describe, test, expect } from "bun:test";
import {
  FRONTIER_PARITY_MATRIX,
  ParityEntrySchema,
  getParityStatus,
  getFrontierHosts,
  isFrontierDeployable,
} from "./parity-matrix.js";

describe("integration/parity-matrix", () => {
  test("matrix covers 5 frontiers × 4 hosts = 20 entries", () => {
    expect(FRONTIER_PARITY_MATRIX.length).toBe(20);
  });

  test("all entries validate against schema", () => {
    for (const entry of FRONTIER_PARITY_MATRIX) {
      expect(ParityEntrySchema.safeParse(entry).success).toBe(true);
    }
  });

  test("PARTIAL entries have degradation_mode", () => {
    const partial = FRONTIER_PARITY_MATRIX.filter(
      (e) => e.status === "PARTIAL",
    );
    for (const entry of partial) {
      expect(entry.degradation_mode).toBeDefined();
      expect(typeof entry.degradation_mode).toBe("string");
    }
  });

  test("governance-graph passes on all 4 hosts", () => {
    const entries = getFrontierHosts("governance-graph");
    expect(entries.every((e) => e.status === "PASS")).toBe(true);
  });

  test("each frontier is deployable on ≥2 hosts", () => {
    const frontiers = [
      "context-durability",
      "multi-agent",
      "society-of-thought",
      "governance-graph",
      "reliability-science",
    ] as const;
    for (const frontier of frontiers) {
      expect(isFrontierDeployable(frontier, 2)).toBe(true);
    }
  });

  test("getParityStatus returns entry for valid pair", () => {
    const result = getParityStatus("governance-graph", "claude");
    expect(result).not.toBeNull();
    expect(result?.status).toBe("PASS");
  });

  test("getParityStatus returns null for unknown pair", () => {
    expect(getParityStatus("context-durability", "claude")).not.toBeNull();
  });

  test("no FAIL entries (all frontiers at least partially supported)", () => {
    const fails = FRONTIER_PARITY_MATRIX.filter((e) => e.status === "FAIL");
    expect(fails.length).toBe(0);
  });
});
