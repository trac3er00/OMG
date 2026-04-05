import { describe, test, expect } from "bun:test";
import { join } from "node:path";
import { tmpdir } from "node:os";
import {
  mkdirSync,
  writeFileSync,
  existsSync,
  readFileSync,
  rmSync,
  utimesSync,
} from "node:fs";
import { gunzipSync } from "node:zlib";
import {
  RETENTION_VERSION,
  DEFAULT_RETENTION_POLICIES,
  getRetentionConfig,
  RetentionPolicySchema,
  parseDuration,
  compressFileSync,
  pruneEvidence,
  queryEvidence,
  EVIDENCE_TYPES,
} from "./retention.js";
import { appendJsonLine } from "../state/atomic-io.js";

function tmpDir(label: string): string {
  return join(
    tmpdir(),
    `ev-${label}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
  );
}

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

describe("parseDuration", () => {
  test("parses days", () => {
    expect(parseDuration("30d")).toBe(30 * 24 * 60 * 60 * 1000);
  });

  test("parses hours", () => {
    expect(parseDuration("24h")).toBe(24 * 60 * 60 * 1000);
  });

  test("parses minutes", () => {
    expect(parseDuration("60m")).toBe(60 * 60 * 1000);
  });

  test("throws on invalid format", () => {
    expect(() => parseDuration("abc")).toThrow("Invalid duration format");
  });

  test("throws on empty string", () => {
    expect(() => parseDuration("")).toThrow("Invalid duration format");
  });
});

describe("compressFileSync", () => {
  test("creates gzipped file that decompresses to original", () => {
    const dir = tmpDir("compress");
    mkdirSync(dir, { recursive: true });
    try {
      const src = join(dir, "test.json");
      const dest = join(dir, "test.json.gz");
      const content = JSON.stringify({ test: true, data: "hello world" });
      writeFileSync(src, content);

      compressFileSync(src, dest);

      expect(existsSync(dest)).toBe(true);
      const decompressed = gunzipSync(readFileSync(dest)).toString();
      expect(decompressed).toBe(content);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("pruneEvidence", () => {
  test("archives old evidence files with gzip compression", () => {
    const dir = tmpDir("prune");
    const evidenceDir = join(dir, "evidence");
    const archiveDir = join(dir, "archive");
    mkdirSync(evidenceDir, { recursive: true });

    try {
      const oldFile = join(evidenceDir, "old-report.json");
      const recentFile = join(evidenceDir, "recent-report.json");
      writeFileSync(oldFile, JSON.stringify({ type: "security", age: "old" }));
      writeFileSync(recentFile, JSON.stringify({ type: "test", age: "new" }));

      const now = Date.now();
      const fiftyDaysAgo = new Date(now - 50 * 24 * 60 * 60 * 1000);
      utimesSync(oldFile, fiftyDaysAgo, fiftyDaysAgo);

      const result = pruneEvidence({
        evidenceDir,
        archiveDir,
        olderThanMs: 30 * 24 * 60 * 60 * 1000,
        now,
      });

      expect(result.archived).toContain("old-report.json");
      expect(result.skipped).toContain("recent-report.json");
      expect(result.archived.length).toBe(1);
      expect(result.skipped.length).toBe(1);

      expect(existsSync(join(archiveDir, "old-report.json.gz"))).toBe(true);
      expect(existsSync(oldFile)).toBe(false);
      expect(existsSync(recentFile)).toBe(true);

      const restored = gunzipSync(
        readFileSync(join(archiveDir, "old-report.json.gz")),
      ).toString();
      expect(JSON.parse(restored)).toEqual({ type: "security", age: "old" });
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("returns empty result for missing directory", () => {
    const result = pruneEvidence({
      evidenceDir: "/nonexistent/path",
      archiveDir: "/nonexistent/archive",
      olderThanMs: 1000,
    });
    expect(result.archived).toEqual([]);
    expect(result.skipped).toEqual([]);
  });

  test("skips non-evidence files", () => {
    const dir = tmpDir("prune-skip");
    const evidenceDir = join(dir, "evidence");
    mkdirSync(evidenceDir, { recursive: true });
    try {
      writeFileSync(join(evidenceDir, "readme.md"), "not evidence");
      writeFileSync(join(evidenceDir, "data.json"), "{}");

      const now = Date.now();
      const oldTime = new Date(now - 100 * 24 * 60 * 60 * 1000);
      utimesSync(join(evidenceDir, "readme.md"), oldTime, oldTime);
      utimesSync(join(evidenceDir, "data.json"), oldTime, oldTime);

      const result = pruneEvidence({
        evidenceDir,
        archiveDir: join(dir, "archive"),
        olderThanMs: 1,
        now,
      });
      expect(result.archived).toContain("data.json");
      expect(result.archived).not.toContain("readme.md");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("queryEvidence", () => {
  test("filters by type", () => {
    const dir = tmpDir("query-type");
    mkdirSync(dir, { recursive: true });
    const registryPath = join(dir, "registry.jsonl");
    try {
      const now = new Date().toISOString();
      appendJsonLine(registryPath, {
        type: "security",
        runId: "r1",
        path: "a.json",
        valid: true,
        timestamp: now,
      });
      appendJsonLine(registryPath, {
        type: "test",
        runId: "r2",
        path: "b.json",
        valid: true,
        timestamp: now,
      });
      appendJsonLine(registryPath, {
        type: "security",
        runId: "r3",
        path: "c.json",
        valid: true,
        timestamp: now,
      });

      const result = queryEvidence({ registryPath, type: "security" });
      expect(result.filtered).toBe(2);
      expect(result.total).toBe(3);
      expect(result.records.every((r) => r.type === "security")).toBe(true);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("filters by since duration", () => {
    const dir = tmpDir("query-since");
    mkdirSync(dir, { recursive: true });
    const registryPath = join(dir, "registry.jsonl");
    try {
      const now = Date.now();
      const recent = new Date(now - 2 * 24 * 60 * 60 * 1000).toISOString();
      const old = new Date(now - 30 * 24 * 60 * 60 * 1000).toISOString();
      appendJsonLine(registryPath, {
        type: "test",
        runId: "r1",
        path: "a.json",
        valid: true,
        timestamp: recent,
      });
      appendJsonLine(registryPath, {
        type: "test",
        runId: "r2",
        path: "b.json",
        valid: true,
        timestamp: old,
      });

      const result = queryEvidence({
        registryPath,
        sinceMs: 7 * 24 * 60 * 60 * 1000,
        now,
      });
      expect(result.filtered).toBe(1);
      expect(result.records[0]!.runId).toBe("r1");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("combines type and since filters", () => {
    const dir = tmpDir("query-combo");
    mkdirSync(dir, { recursive: true });
    const registryPath = join(dir, "registry.jsonl");
    try {
      const now = Date.now();
      const recent = new Date(now - 1 * 24 * 60 * 60 * 1000).toISOString();
      const old = new Date(now - 30 * 24 * 60 * 60 * 1000).toISOString();
      appendJsonLine(registryPath, {
        type: "security",
        runId: "r1",
        path: "a.json",
        valid: true,
        timestamp: recent,
      });
      appendJsonLine(registryPath, {
        type: "build",
        runId: "r2",
        path: "b.json",
        valid: true,
        timestamp: recent,
      });
      appendJsonLine(registryPath, {
        type: "security",
        runId: "r3",
        path: "c.json",
        valid: true,
        timestamp: old,
      });

      const result = queryEvidence({
        registryPath,
        type: "security",
        sinceMs: 7 * 24 * 60 * 60 * 1000,
        now,
      });
      expect(result.filtered).toBe(1);
      expect(result.records[0]!.runId).toBe("r1");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("returns all records when no filters applied", () => {
    const dir = tmpDir("query-all");
    mkdirSync(dir, { recursive: true });
    const registryPath = join(dir, "registry.jsonl");
    try {
      const now = new Date().toISOString();
      appendJsonLine(registryPath, {
        type: "test",
        runId: "r1",
        path: "a.json",
        valid: true,
        timestamp: now,
      });
      appendJsonLine(registryPath, {
        type: "build",
        runId: "r2",
        path: "b.json",
        valid: true,
        timestamp: now,
      });

      const result = queryEvidence({ registryPath });
      expect(result.filtered).toBe(2);
      expect(result.total).toBe(2);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("returns empty for missing registry", () => {
    const result = queryEvidence({
      registryPath: "/nonexistent/registry.jsonl",
    });
    expect(result.records).toEqual([]);
    expect(result.total).toBe(0);
    expect(result.filtered).toBe(0);
  });
});

describe("EVIDENCE_TYPES", () => {
  test("contains all required types", () => {
    expect(EVIDENCE_TYPES).toContain("security");
    expect(EVIDENCE_TYPES).toContain("test");
    expect(EVIDENCE_TYPES).toContain("build");
    expect(EVIDENCE_TYPES).toContain("governance");
    expect(EVIDENCE_TYPES).toContain("planning");
  });
});
