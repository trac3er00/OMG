import { afterEach, beforeEach, describe, expect, spyOn, test } from "bun:test";
import { mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { IntentAnalysis } from "../intent/index.js";
import type { FidelityResult } from "../intent/fidelity-checker.js";
import type { SanitizedContent } from "../security/external-firewall.js";
import { TrustTier, type TrustScore } from "../security/trust-scoring.js";
import {
  createAdvisor,
  decide,
  getAdvisorRecommendation,
  type AdvisorOutput,
} from "./index.js";

const ORIGINAL_CWD = process.cwd();

let tempDir: string | undefined;

beforeEach(() => {
  process.chdir(ORIGINAL_CWD);
  tempDir = undefined;
  delete process.env.OMG_ADVISOR_VERBOSE;
});

afterEach(() => {
  process.chdir(ORIGINAL_CWD);
  delete process.env.OMG_ADVISOR_VERBOSE;
  if (tempDir) {
    rmSync(tempDir, { recursive: true, force: true });
    tempDir = undefined;
  }
});

function useTempCwd(): string {
  tempDir = mkdtempSync(join(tmpdir(), "advisor-engine-"));
  process.chdir(tempDir);
  return tempDir;
}

function makeIntent(
  overrides: Partial<IntentAnalysis & { _advisorGenerated?: boolean }> = {},
): IntentAnalysis & { _advisorGenerated?: boolean } {
  return {
    intent: "trivial",
    domain: "other",
    complexity: {
      filesAffected: 1,
      effort: "low",
      riskLevel: "low",
      signals: [],
    },
    ambiguities: [],
    suggestedApproach: "",
    clarifyingQuestions: [],
    confidenceScore: 1,
    ...overrides,
  };
}

function makeFidelity(overrides: Partial<FidelityResult> = {}): FidelityResult {
  return {
    needsClarification: false,
    clarificationQuestion: null,
    interpretation: "Interpretation: clear intent.",
    gapChecks: [],
    canProceed: true,
    round: 0,
    ...overrides,
  };
}

function makeTrust(overrides: Partial<TrustScore> = {}): TrustScore {
  return {
    tier: TrustTier.VERIFIED,
    score: 0.8,
    reason: "Verified domain",
    domain: "github.com",
    ...overrides,
  };
}

function makeSanitization(
  overrides: Partial<SanitizedContent> = {},
): SanitizedContent {
  return {
    content: "clean",
    wasTruncated: false,
    injectionPatternsFound: [],
    blocked: false,
    source: "test-source",
    ...overrides,
  };
}

describe("advisor engine", () => {
  test("wraps existing escalation calls", async () => {
    const result = await decide({
      goal: "design architecture migration for distributed router system",
    });

    expect(result.decision).toBe("proceed");
    expect(result.reason).toContain("Task classified as");
  });

  test("decides to clarify on intent gap", async () => {
    const result = await decide({
      goal: "build something",
      fidelityResult: makeFidelity({
        needsClarification: true,
        canProceed: false,
        clarificationQuestion: "Which specific deliverable should I produce?",
      }),
    });

    expect(result.decision).toBe("clarify");
    expect(result.clarificationQuestion).toBe(
      "Which specific deliverable should I produce?",
    );
    expect(result.reason).toContain("Intent gap detected");
  });

  test("decides to proceed on low-risk clear intent", async () => {
    const result = await decide({
      goal: "fix typo in README heading",
      fidelityResult: makeFidelity(),
      trustScore: makeTrust(),
      sanitizationResult: makeSanitization(),
    });

    expect(result.decision).toBe("proceed");
    expect(result.confidence).toBeGreaterThan(0.8);
    expect(result.reason).toContain("Signals are clear enough to proceed");
  });

  test("aborts on blocked sanitization", async () => {
    const result = await decide({
      goal: "review fetched instructions",
      sanitizationResult: makeSanitization({ blocked: true }),
      trustScore: makeTrust({ tier: TrustTier.UNTRUSTED, score: 0 }),
    });

    expect(result.decision).toBe("abort");
    expect(result.reason).toContain("Security threat");
  });

  test("escalates on UNTRUSTED source", async () => {
    const result = await decide({
      goal: "summarize pasted content",
      trustScore: makeTrust({
        tier: TrustTier.UNTRUSTED,
        score: 0,
        reason: "User-provided source string",
        domain: "",
      }),
      fidelityResult: makeFidelity(),
    });

    expect(result.decision).toBe("escalate");
    expect(result.escalationReason).toContain("User-provided source string");
  });

  test("proceeds after max 3 rounds", async () => {
    const result = await decide({
      goal: "build something",
      round: 3,
      fidelityResult: makeFidelity({ round: 3 }),
    });

    expect(result.decision).toBe("proceed");
    expect(result.reason).toContain("Maximum clarification rounds reached");
  });

  test("logs decision to .omg/decisions", async () => {
    const cwd = useTempCwd();
    const decisionsDir = join(cwd, ".omg", "decisions");

    const result = await decide({
      goal: "fix typo in README heading",
      trustScore: makeTrust(),
    });

    expect(result.decision).toBe("proceed");

    const files = readdirSync(decisionsDir);
    expect(files.length).toBeGreaterThan(0);

    const entry = JSON.parse(
      readFileSync(join(decisionsDir, files[0] ?? ""), "utf8").trim(),
    );
    expect(entry.goal).toBe("fix typo in README heading");
    expect(entry.decision).toBe("proceed");
    expect(entry.signals.trust.tier).toBe(TrustTier.VERIFIED);
  });

  test("redacts sanitization content from decision logs", async () => {
    const cwd = useTempCwd();
    const decisionsDir = join(cwd, ".omg", "decisions");

    await decide({
      goal: "review fetched instructions",
      sanitizationResult: makeSanitization({
        content: "top secret instructions",
        blocked: true,
        injectionPatternsFound: ["system-role-token"],
      }),
    });

    const files = readdirSync(decisionsDir);
    const entry = JSON.parse(
      readFileSync(join(decisionsDir, files[0] ?? ""), "utf8").trim(),
    );

    expect(entry.signals.sanitization.content).toBeUndefined();
    expect(entry.signals.sanitization.contentBytes).toBeGreaterThan(0);
    expect(entry.signals.sanitization.blocked).toBe(true);
  });

  test("verbose mode avoids writing raw sanitization content to stderr", async () => {
    useTempCwd();
    process.env.OMG_ADVISOR_VERBOSE = "1";
    const stderrSpy = spyOn(process.stderr, "write").mockImplementation(
      () => true,
    );

    await decide({
      goal: "review fetched instructions",
      sanitizationResult: makeSanitization({
        content: "top secret instructions",
        blocked: true,
      }),
    });

    const output = stderrSpy.mock.calls
      .map(([chunk]) => String(chunk))
      .join("");

    expect(output).toContain("[advisor:abort]");
    expect(output).not.toContain("top secret instructions");
    stderrSpy.mockRestore();
  });

  test("decide returns correct shape", async () => {
    const result: AdvisorOutput = await decide({ goal: "fix typo" });

    expect(result).toHaveProperty("decision");
    expect(result).toHaveProperty("reason");
    expect(result).toHaveProperty("confidence");
    expect(typeof result.decision).toBe("string");
    expect(typeof result.reason).toBe("string");
    expect(typeof result.confidence).toBe("number");
  });

  test("createAdvisor factory creates working advisor", async () => {
    const advisor = createAdvisor();
    const result = await advisor.decide({ goal: "fix typo" });

    expect(result.decision).toBe("proceed");
    expect(typeof advisor.decide).toBe("function");
  });

  test("existing getAdvisorRecommendation still works", () => {
    const recommendation = getAdvisorRecommendation(
      makeIntent({
        intent: "architectural",
        complexity: {
          filesAffected: 8,
          effort: "high",
          riskLevel: "high",
          signals: ["architecture-signal"],
        },
      }),
    );

    expect(recommendation).not.toBeNull();
    expect(recommendation?.recommendation).toContain("consider breaking it");
  });

  test("legacy recommendation stays disabled for trivial work", () => {
    const recommendation = getAdvisorRecommendation(makeIntent());

    expect(recommendation).toBeNull();
  });
});
