import { describe, test, expect } from "bun:test";
import {
  EVIDENCE_SCHEMA_VERSION,
  LEGACY_SCHEMA_VERSION,
  migrateArtifact,
  validateEvidenceArtifact,
  validateArtifactByType,
} from "./schema-registry.js";

describe("schema-registry", () => {
  test("EVIDENCE_SCHEMA_VERSION is 1.0.0", () => {
    expect(EVIDENCE_SCHEMA_VERSION).toBe("1.0.0");
  });

  test("LEGACY_SCHEMA_VERSION is 0.9.0", () => {
    expect(LEGACY_SCHEMA_VERSION).toBe("0.9.0");
  });

  describe("validateEvidenceArtifact", () => {
    test("valid artifact with schema_version passes", () => {
      const artifact = { schema_version: "1.0.0", artifact_type: "junit" };
      const result = validateEvidenceArtifact(artifact);
      expect(result.valid).toBe(true);
      expect(result.error).toBeUndefined();
    });

    test("artifact without schema_version uses default 0.9.0 and passes", () => {
      const artifact = { artifact_type: "coverage" };
      const result = validateEvidenceArtifact(artifact);
      expect(result.valid).toBe(true);
    });

    test("invalid schema_version (not semver) fails", () => {
      const artifact = { schema_version: "not-semver", artifact_type: "junit" };
      const result = validateEvidenceArtifact(artifact);
      expect(result.valid).toBe(false);
      expect(result.error).toBeDefined();
    });

    test("artifact missing artifact_type fails", () => {
      const artifact = { schema_version: "1.0.0" };
      const result = validateEvidenceArtifact(artifact);
      expect(result.valid).toBe(false);
    });
  });

  describe("migrateArtifact", () => {
    test("artifact without schema_version gets LEGACY_SCHEMA_VERSION", () => {
      const artifact = { artifact_type: "junit", parsed: true };
      const migrated = migrateArtifact(artifact);
      expect(migrated.schema_version).toBe("0.9.0");
    });

    test("artifact with existing schema_version keeps it", () => {
      const artifact = { artifact_type: "junit", schema_version: "1.0.0" };
      const migrated = migrateArtifact(artifact);
      expect(migrated.schema_version).toBe("1.0.0");
    });

    test("artifact without artifact_type gets 'unknown'", () => {
      const artifact = { some_field: "value" };
      const migrated = migrateArtifact(artifact);
      expect(migrated.artifact_type).toBe("unknown");
    });

    test("throws on non-object input", () => {
      expect(() => migrateArtifact("string")).toThrow();
      expect(() => migrateArtifact(null)).toThrow();
      expect(() => migrateArtifact(42)).toThrow();
    });
  });

  describe("validateArtifactByType", () => {
    test("valid JUnit artifact passes", () => {
      const artifact = {
        schema_version: "1.0.0",
        artifact_type: "junit",
        parsed: true,
        summary: {
          tests: 10,
          failures: 0,
          errors: 0,
          time: 1.5,
          failureMessages: [],
        },
      };
      const result = validateArtifactByType(artifact);
      expect(result.valid).toBe(true);
    });

    test("JUnit artifact missing required fields fails", () => {
      const artifact = {
        schema_version: "1.0.0",
        artifact_type: "junit",
        // missing 'parsed' and 'summary'
      };
      const result = validateArtifactByType(artifact);
      expect(result.valid).toBe(false);
    });

    test("valid coverage artifact passes", () => {
      const artifact = {
        schema_version: "1.0.0",
        artifact_type: "coverage",
        line_rate: 0.85,
      };
      const result = validateArtifactByType(artifact);
      expect(result.valid).toBe(true);
    });

    test("coverage artifact with out-of-range line_rate fails", () => {
      const artifact = {
        schema_version: "1.0.0",
        artifact_type: "coverage",
        line_rate: 1.5, // > 1.0 is invalid
      };
      const result = validateArtifactByType(artifact);
      expect(result.valid).toBe(false);
    });

    test("valid claim_judge artifact passes", () => {
      const artifact = {
        schema_version: "1.0.0",
        artifact_type: "claim_judge",
        verdict: "accept",
        confidence: 0.92,
        reasons: ["evidence_sufficient"],
      };
      const result = validateArtifactByType(artifact);
      expect(result.valid).toBe(true);
    });

    test("claim_judge artifact with invalid verdict fails", () => {
      const artifact = {
        schema_version: "1.0.0",
        artifact_type: "claim_judge",
        verdict: "INVALID_VERDICT",
        confidence: 0.5,
        reasons: [],
      };
      const result = validateArtifactByType(artifact);
      expect(result.valid).toBe(false);
    });

    test("unknown artifact type passes base validation", () => {
      const artifact = {
        schema_version: "1.0.0",
        artifact_type: "some_future_type",
      };
      const result = validateArtifactByType(artifact);
      expect(result.valid).toBe(true);
    });

    test("proof_gate artifact with pass status passes", () => {
      const artifact = {
        schema_version: "1.0.0",
        artifact_type: "proof_gate",
        status: "pass",
        blockers: [],
      };
      const result = validateArtifactByType(artifact);
      expect(result.valid).toBe(true);
    });

    test("old artifact without schema_version migrates and validates", () => {
      // Simulate a legacy artifact from before versioning was added
      const legacyArtifact = {
        artifact_type: "coverage",
        line_rate: 0.72,
        // no schema_version field
      };
      const result = validateArtifactByType(legacyArtifact);
      expect(result.valid).toBe(true);
    });
  });
});
