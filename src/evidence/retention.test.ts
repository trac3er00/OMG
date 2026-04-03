import { describe, test, expect } from "bun:test";
import {
  RETENTION_VERSION,
  DEFAULT_RETENTION_POLICIES,
  getRetentionConfig,
  RetentionPolicySchema,
} from "./retention.js";

describe("evidence/retention", () => {
  test("RETENTION_VERSION is 1.0.0", () => {
    expect(RETENTION_VERSION).toBe("1.0.0");
  });

  describe("DEFAULT_RETENTION_POLICIES", () => {
    test("covers all major evidence types", () => {
      const types = DEFAULT_RETENTION_POLICIES.map((p) => p.evidence_type);
      expect(types).toContain("governance_ledger");
      expect(types).toContain("reliability_metrics");
      expect(types).toContain("checkpoint_state");
      expect(types).toContain("debate_transcripts");
    });

    test("governance_ledger uses archive-only strategy", () => {
      const govPolicy = DEFAULT_RETENTION_POLICIES.find(
        (p) => p.evidence_type === "governance_ledger",
      );
      expect(govPolicy?.archive_strategy).toBe("archive");
      expect(govPolicy?.retention_days).toBeGreaterThanOrEqual(365);
    });

    test("all policies validate against schema", () => {
      for (const policy of DEFAULT_RETENTION_POLICIES) {
        expect(RetentionPolicySchema.safeParse(policy).success).toBe(true);
      }
    });

    test("at least 7 evidence types covered", () => {
      expect(DEFAULT_RETENTION_POLICIES.length).toBeGreaterThanOrEqual(7);
    });
  });

  describe("getRetentionConfig", () => {
    test("returns all default policies", () => {
      const config = getRetentionConfig();
      expect(config.length).toBe(DEFAULT_RETENTION_POLICIES.length);
    });
  });
});
