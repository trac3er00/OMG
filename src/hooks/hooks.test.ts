import { describe, test, expect } from "bun:test";

import {
  BudgetConstants,
  CostLedger,
  BudgetGovernor,
  type CostEntry,
  type CostLedgerDeps,
} from "./budget.js";

import { AnalyticsHook } from "./analytics.js";

import { CompressionHook, type FeedbackEntry } from "./compression.js";

import {
  QualityRunner,
  TddGate,
  isSafeCommand,
  type QualityRunnerDeps,
} from "./quality.js";

import {
  KeywordRouter,
  StopGate,
  VerificationCheck,
  RecentFailuresCheck,
  type IntentRoutingMap,
} from "./routing.js";

import {
  MemoryHook,
  LearningsAggregator,
  type MemoryDeps,
} from "./memory.js";

describe("BudgetConstants", () => {
  test("has session-start budgets", () => {
    expect(BudgetConstants.SESSION_TOTAL).toBe(2000);
    expect(BudgetConstants.SESSION_IDLE).toBe(200);
    expect(BudgetConstants.PROFILE).toBe(200);
  });

  test("has prompt-enhancer budgets", () => {
    expect(BudgetConstants.PROMPT_TOTAL).toBe(1000);
    expect(BudgetConstants.KNOWLEDGE).toBe(300);
  });
});

describe("CostLedger", () => {
  function makeDeps(): CostLedgerDeps & { lines: string[]; written: string[] } {
    const lines: string[] = [];
    const written: string[] = [];
    return {
      lines,
      written,
      readLines: async () => lines,
      appendLine: async (_path: string, line: string) => { written.push(line); },
      fileSize: async () => 100,
      rename: async () => {},
      remove: async () => {},
      exists: async () => lines.length > 0,
      mkdirp: async () => {},
    };
  }

  test("appendEntry writes JSONL", async () => {
    const deps = makeDeps();
    const ledger = new CostLedger("/project", deps);
    const entry: CostEntry = {
      ts: "2025-01-01T00:00:00Z",
      tool: "Bash",
      tokensIn: 100,
      tokensOut: 50,
      costUsd: 0.01,
      model: "claude",
      sessionId: "s1",
    };
    await ledger.appendEntry(entry);
    expect(deps.written.length).toBe(1);
    const parsed = JSON.parse(deps.written[0].trim()) as Record<string, unknown>;
    expect(parsed["tool"]).toBe("Bash");
    expect(parsed["tokens_in"]).toBe(100);
  });

  test("readSummary aggregates entries", async () => {
    const deps = makeDeps();
    deps.lines.push(
      '{"tool":"Bash","tokens_in":100,"tokens_out":50,"cost_usd":0.01,"session_id":"s1"}',
      '{"tool":"Read","tokens_in":200,"tokens_out":10,"cost_usd":0.02,"session_id":"s1"}',
      '{"tool":"Bash","tokens_in":50,"tokens_out":25,"cost_usd":0.005,"session_id":"s2"}',
    );
    const ledger = new CostLedger("/project", deps);
    const summary = await ledger.readSummary();

    expect(summary.entryCount).toBe(3);
    expect(summary.totalTokens).toBe(435);
    expect(summary.byTool["Bash"]?.count).toBe(2);
    expect(summary.bySession["s1"]?.count).toBe(2);
  });

  test("readSummary returns empty for missing ledger", async () => {
    const deps = makeDeps();
    const ledger = new CostLedger("/project", deps);
    const summary = await ledger.readSummary();
    expect(summary.entryCount).toBe(0);
    expect(summary.totalTokens).toBe(0);
  });
});

describe("BudgetGovernor", () => {
  test("checkBudget returns remaining percentage", () => {
    const governor = new BudgetGovernor({ sessionLimitUsd: 10 });
    const result = governor.checkBudget(2.0, 10);
    expect(result.exceeded).toBe(false);
    expect(result.remainingPct).toBe(80);
    expect(result.remaining).toBeCloseTo(8.0);
  });

  test("checkBudget detects exceeded budget", () => {
    const governor = new BudgetGovernor({ sessionLimitUsd: 5 });
    const result = governor.checkBudget(5.5, 20);
    expect(result.exceeded).toBe(true);
    expect(result.remainingPct).toBe(0);
  });

  test("threshold alerts fire once", () => {
    const governor = new BudgetGovernor(
      { sessionLimitUsd: 10 },
      [50, 80, 95],
    );
    const r1 = governor.checkBudget(5.5, 10);
    expect(r1.thresholdAlerts.length).toBe(1);
    expect(r1.thresholdAlerts[0]).toContain("50%");

    const r2 = governor.checkBudget(5.5, 11);
    expect(r2.thresholdAlerts.length).toBe(0);
  });

  test("estimateCallCost returns non-negative", () => {
    const governor = new BudgetGovernor();
    const cost = governor.estimateCallCost("hello world", "response text");
    expect(cost).toBeGreaterThanOrEqual(0);
  });

  test("context string includes budget info", () => {
    const governor = new BudgetGovernor({ sessionLimitUsd: 10 });
    const result = governor.checkBudget(3.0, 5);
    expect(result.context).toContain("Budget:");
    expect(result.context).toContain("remaining");
    expect(result.context).toContain("$3.00");
  });

  test("getUsage computes projected calls", () => {
    const governor = new BudgetGovernor({ sessionLimitUsd: 10 });
    const usage = governor.getUsage(2.0, 10);
    expect(usage.usedCostUsd).toBe(2.0);
    expect(usage.usedCalls).toBe(10);
    expect(usage.projectedCalls).toBeGreaterThan(0);
  });
});

describe("AnalyticsHook", () => {
  test("records and summarizes tool calls", () => {
    const hook = new AnalyticsHook();
    hook.recordToolCall("Bash", true, 100);
    hook.recordToolCall("Bash", true, 200);
    hook.recordToolCall("Read", false, 50);

    const summary = hook.getSummary();
    expect(summary.totalCalls).toBe(3);
    expect(summary.byTool["Bash"]?.count).toBe(2);
    expect(summary.byTool["Bash"]?.successRate).toBe(1);
    expect(summary.byTool["Read"]?.successRate).toBe(0);
  });

  test("computes overall success rate", () => {
    const hook = new AnalyticsHook();
    hook.recordToolCall("A", true, 10);
    hook.recordToolCall("B", false, 10);

    const summary = hook.getSummary();
    expect(summary.overallSuccessRate).toBe(0.5);
  });

  test("computes average latency", () => {
    const hook = new AnalyticsHook();
    hook.recordToolCall("A", true, 100);
    hook.recordToolCall("A", true, 300);

    const summary = hook.getSummary();
    expect(summary.avgLatencyMs).toBe(200);
  });

  test("detects file hotspots", () => {
    const hook = new AnalyticsHook();
    for (let i = 0; i < 7; i++) {
      hook.recordFileEdit("src/hot.ts");
    }
    hook.recordFileEdit("src/cold.ts");

    const summary = hook.getSummary();
    expect(summary.hotspots.length).toBe(1);
    expect(summary.hotspots[0].file).toBe("src/hot.ts");
    expect(summary.hotspots[0].editCount).toBe(7);
  });

  test("error trend is stable with no data", () => {
    const hook = new AnalyticsHook();
    const summary = hook.getSummary();
    expect(summary.errorTrend.trend).toBe("stable");
  });

  test("tool shifts detect usage anomalies", () => {
    const hook = new AnalyticsHook();
    for (let i = 0; i < 10; i++) hook.recordToolCall("Heavy", true, 10);
    hook.recordToolCall("Light", true, 10);

    const summary = hook.getSummary();
    expect(summary.toolShifts.length).toBeGreaterThan(0);
  });
});

describe("CompressionHook", () => {
  test("shouldCompress returns true when over limit", () => {
    const hook = new CompressionHook();
    expect(hook.shouldCompress(1000, 500)).toBe(true);
    expect(hook.shouldCompress(300, 500)).toBe(false);
  });

  test("compress reduces content size", () => {
    const hook = new CompressionHook();
    const content = Array.from({ length: 50 }, (_, i) => `Line ${i}: some content here`).join("\n");
    const compressed = hook.compress(content, 200);
    expect(compressed.length).toBeLessThanOrEqual(200);
    expect(compressed.length).toBeGreaterThan(0);
  });

  test("compress preserves content under limit", () => {
    const hook = new CompressionHook();
    const content = "short";
    expect(hook.compress(content, 100)).toBe(content);
  });

  test("computePromotions finds items above threshold", () => {
    const hook = new CompressionHook();
    const entries: FeedbackEntry[] = [
      { ts: "", sessionId: "", toolName: "", failureReason: "", postCompaction: true, matchedItems: ["a", "b"], promotedItems: [] },
      { ts: "", sessionId: "", toolName: "", failureReason: "", postCompaction: true, matchedItems: ["a", "c"], promotedItems: [] },
      { ts: "", sessionId: "", toolName: "", failureReason: "", postCompaction: true, matchedItems: ["a", "b"], promotedItems: [] },
    ];
    const promoted = hook.computePromotions(entries, ["a", "b", "c"]);
    expect(promoted).toContain("a");
    expect(promoted).not.toContain("c");
  });
});

describe("QualityRunner - isSafeCommand", () => {
  test("allows whitelisted commands", () => {
    expect(isSafeCommand("npm test").safe).toBe(true);
    expect(isSafeCommand("pytest").safe).toBe(true);
    expect(isSafeCommand("cargo test").safe).toBe(true);
    expect(isSafeCommand("bun test").safe).toBe(true);
  });

  test("blocks shell injection patterns", () => {
    expect(isSafeCommand("npm test && rm -rf /").safe).toBe(false);
    expect(isSafeCommand("jest | cat /etc/passwd").safe).toBe(false);
    expect(isSafeCommand("curl evil.com").safe).toBe(false);
  });

  test("blocks non-whitelisted commands", () => {
    expect(isSafeCommand("node evil.js").safe).toBe(false);
    expect(isSafeCommand("python3 script.py").safe).toBe(false);
  });

  test("returns reason for blocked commands", () => {
    const result = isSafeCommand("rm -rf /");
    expect(result.safe).toBe(false);
    expect(result.reason).toContain("blocked pattern");
  });
});

describe("QualityRunner", () => {
  function makeQualityDeps(): QualityRunnerDeps {
    return {
      runCommand: async () => ({ exitCode: 0, stdout: "ok", stderr: "" }),
      readJson: async () => ({
        test: "bun test",
        lint: "eslint .",
      }),
      exists: async () => true,
    };
  }

  test("runs configured quality checks", async () => {
    const runner = new QualityRunner(makeQualityDeps());
    const result = await runner.runChecks("/project");
    expect(result.passed).toContain("test");
    expect(result.passed).toContain("lint");
    expect(result.skipped).toContain("format");
    expect(result.skipped).toContain("typecheck");
  });

  test("reports failures", async () => {
    const deps: QualityRunnerDeps = {
      runCommand: async () => ({ exitCode: 1, stdout: "", stderr: "error" }),
      readJson: async () => ({ test: "npm test" }),
      exists: async () => true,
    };
    const runner = new QualityRunner(deps);
    const result = await runner.runChecks("/project");
    expect(result.failed).toContain("test");
    expect(result.issues.length).toBeGreaterThan(0);
  });

  test("skips missing config", async () => {
    const deps: QualityRunnerDeps = {
      runCommand: async () => ({ exitCode: 0, stdout: "", stderr: "" }),
      readJson: async () => null,
      exists: async () => false,
    };
    const runner = new QualityRunner(deps);
    const result = await runner.runChecks("/project");
    expect(result.skipped.length).toBe(4);
  });
});

describe("TddGate", () => {
  test("detects fake test patterns", () => {
    const gate = new TddGate();
    const content = `
      test("trivial", () => {
        expect(true).toBe(true);
      });
    `;
    const issues = gate.analyzeTestContent(content);
    expect(issues.some((i) => i.category === "FAKE")).toBe(true);
  });

  test("detects boilerplate-only tests", () => {
    const gate = new TddGate();
    const content = `
      typeof result;
      instanceof Foo;
      toBeDefined();
      toBeDefined();
    `;
    const issues = gate.analyzeTestContent(content);
    expect(issues.some((i) => i.category === "BOILERPLATE")).toBe(true);
  });

  test("detects skip patterns", () => {
    const gate = new TddGate();
    const content = 'it.skip("broken test", () => {});';
    const issues = gate.analyzeTestContent(content);
    expect(issues.some((i) => i.category === "SKIP")).toBe(true);
  });

  test("clean test passes analysis", () => {
    const gate = new TddGate();
    const content = `
      test("adds numbers", () => {
        expect(add(1, 2)).toEqual(3);
      });
      test("handles error", () => {
        expect(() => add(null, 2)).toThrow();
      });
      test("handles edge case boundary", () => {
        expect(add(0, 0)).toEqual(0);
      });
    `;
    const issues = gate.analyzeTestContent(content);
    expect(issues.filter((i) => i.category === "FAKE").length).toBe(0);
    expect(issues.filter((i) => i.category === "BOILERPLATE").length).toBe(0);
  });
});

describe("KeywordRouter", () => {
  const routingMap: IntentRoutingMap = {
    INTENT_PLAN: "planner",
    INTENT_CODE: "coder",
    INTENT_STOP: null,
  };

  test("routes known intent to target", () => {
    const router = new KeywordRouter(routingMap);
    const result = router.route({
      detectedIntents: [{ intent: "INTENT_CODE", confidence: 0.9 }],
    });
    expect(result.target).toBe("coder");
    expect(result.confidence).toBe(0.9);
    expect(result.fallback).toBe(false);
  });

  test("routes INTENT_STOP to null target", () => {
    const router = new KeywordRouter(routingMap);
    const result = router.route({
      detectedIntents: [{ intent: "INTENT_STOP", confidence: 0.95 }],
    });
    expect(result.target).toBeNull();
    expect(result.intent).toBe("INTENT_STOP");
    expect(result.fallback).toBe(false);
  });

  test("returns fallback for unknown intent", () => {
    const router = new KeywordRouter(routingMap);
    const result = router.route({
      detectedIntents: [{ intent: "UNKNOWN", confidence: 0.5 }],
    });
    expect(result.fallback).toBe(true);
    expect(result.target).toBeNull();
  });

  test("returns fallback for null input", () => {
    const router = new KeywordRouter(routingMap);
    const result = router.route(null);
    expect(result.fallback).toBe(true);
  });

  test("extractLeaderHint parses from data", () => {
    const router = new KeywordRouter(routingMap);
    const hint = router.extractLeaderHint({
      LEADER_HINT: {
        detected_intents: [{ intent: "INTENT_PLAN", confidence: 0.8 }],
      },
    });
    expect(hint).not.toBeNull();
    expect(hint?.detectedIntents[0].intent).toBe("INTENT_PLAN");
  });

  test("extractLeaderHint returns null for missing hint", () => {
    const router = new KeywordRouter(routingMap);
    const hint = router.extractLeaderHint({ foo: "bar" });
    expect(hint).toBeNull();
  });
});

describe("StopGate", () => {
  test("passes when all checks pass", () => {
    const gate = new StopGate([new VerificationCheck()]);
    const result = gate.evaluate({
      hasSourceWrites: true,
      hasTests: true,
      hasVerification: true,
      changedFiles: ["src/a.ts"],
      recentFailures: 0,
    });
    expect(result.shouldStop).toBe(true);
    expect(result.blocks.length).toBe(0);
  });

  test("blocks when verification missing", () => {
    const gate = new StopGate([new VerificationCheck()]);
    const result = gate.evaluate({
      hasSourceWrites: true,
      hasTests: false,
      hasVerification: false,
      changedFiles: ["src/a.ts"],
      recentFailures: 0,
    });
    expect(result.shouldStop).toBe(false);
    expect(result.blocks.length).toBe(1);
  });

  test("blocks on recent failures", () => {
    const gate = new StopGate([new RecentFailuresCheck()]);
    const result = gate.evaluate({
      hasSourceWrites: false,
      hasTests: false,
      hasVerification: false,
      changedFiles: [],
      recentFailures: 3,
    });
    expect(result.shouldStop).toBe(false);
    expect(result.blocks[0]).toContain("FAILED");
  });

  test("combines multiple checks", () => {
    const gate = new StopGate([new VerificationCheck(), new RecentFailuresCheck()]);
    const result = gate.evaluate({
      hasSourceWrites: true,
      hasTests: false,
      hasVerification: false,
      changedFiles: ["src/a.ts"],
      recentFailures: 5,
    });
    expect(result.blocks.length).toBe(2);
  });
});

describe("MemoryHook", () => {
  function makeMemoryDeps(): MemoryDeps & { files: Map<string, string> } {
    const files = new Map<string, string>();
    return {
      files,
      readFile: async (path: string) => {
        const content = files.get(path);
        if (content === undefined) throw new Error("not found");
        return content;
      },
      writeFile: async (path: string, content: string) => { files.set(path, content); },
      appendFile: async (path: string, content: string) => {
        files.set(path, (files.get(path) ?? "") + content);
      },
      exists: async (path: string) => files.has(path) || Array.from(files.keys()).some((k) => k.startsWith(path + "/")),
      mkdirp: async () => {},
      listDir: async (dir: string) => {
        const prefix = dir.endsWith("/") ? dir : dir + "/";
        return Array.from(files.keys())
          .filter((k) => k.startsWith(prefix))
          .map((k) => k.slice(prefix.length))
          .filter((k) => !k.includes("/"));
      },
      remove: async (path: string) => { files.delete(path); },
    };
  }

  test("recordLearning creates memory file", async () => {
    const deps = makeMemoryDeps();
    const hook = new MemoryHook("/project", deps);
    const path = await hook.recordLearning("sess123", "learned something");
    expect(path).toContain("sess123");
    expect(deps.files.size).toBe(1);
  });

  test("recordLearning appends to existing file", async () => {
    const deps = makeMemoryDeps();
    const hook = new MemoryHook("/project", deps);
    await hook.recordLearning("sess1234", "first");
    await hook.recordLearning("sess1234", "second");
    const values = Array.from(deps.files.values());
    expect(values[0]).toContain("first");
    expect(values[0]).toContain("second");
  });

  test("searchMemories finds by keyword", async () => {
    const deps = makeMemoryDeps();
    deps.files.set("/project/.omg/state/memory/2025-01-01-test.md", "typescript patterns and react hooks");
    deps.files.set("/project/.omg/state/memory/2025-01-02-other.md", "python flask");

    const hook = new MemoryHook("/project", deps);
    const result = await hook.searchMemories(["typescript"]);
    expect(result).toContain("typescript");
    expect(result).not.toContain("python");
  });

  test("getRecentMemories returns latest files", async () => {
    const deps = makeMemoryDeps();
    deps.files.set("/project/.omg/state/memory/2025-01-01.md", "old memory");
    deps.files.set("/project/.omg/state/memory/2025-01-02.md", "new memory");

    const hook = new MemoryHook("/project", deps);
    const result = await hook.getRecentMemories(2, 500);
    expect(result).toContain("new memory");
  });

  test("rotateMemories removes excess files", async () => {
    const deps = makeMemoryDeps();
    for (let i = 0; i < 5; i++) {
      deps.files.set(`/project/.omg/state/memory/2025-01-0${i}.md`, `memory ${i}`);
    }

    const hook = new MemoryHook("/project", deps);
    const removed = await hook.rotateMemories(3);
    expect(removed).toBe(2);
    expect(deps.files.size).toBe(3);
  });

  test("getLearning delegates to searchMemories", async () => {
    const deps = makeMemoryDeps();
    deps.files.set("/project/.omg/state/memory/2025-01-01-key.md", "value for key topic");

    const hook = new MemoryHook("/project", deps);
    const result = await hook.getLearning("key");
    expect(result).toContain("value for key topic");
  });
});

describe("LearningsAggregator", () => {
  function makeMemoryDeps(): MemoryDeps & { files: Map<string, string> } {
    const files = new Map<string, string>();
    return {
      files,
      readFile: async (path: string) => {
        const content = files.get(path);
        if (content === undefined) throw new Error("not found");
        return content;
      },
      writeFile: async (path: string, content: string) => { files.set(path, content); },
      appendFile: async (path: string, content: string) => {
        files.set(path, (files.get(path) ?? "") + content);
      },
      exists: async (path: string) => files.has(path) || Array.from(files.keys()).some((k) => k.startsWith(path + "/")),
      mkdirp: async () => {},
      listDir: async (dir: string) => {
        const prefix = dir.endsWith("/") ? dir : dir + "/";
        return Array.from(files.keys())
          .filter((k) => k.startsWith(prefix))
          .map((k) => k.slice(prefix.length))
          .filter((k) => !k.includes("/"));
      },
      remove: async (path: string) => { files.delete(path); },
    };
  }

  test("aggregates tool and file patterns", async () => {
    const deps = makeMemoryDeps();
    deps.files.set(
      "/project/.omg/state/learnings/session1.md",
      "## Most Used Tools\n- Bash: 10x\n- Read: 5x\n## Most Modified Files\n- src/index.ts: 8x\n",
    );
    deps.files.set(
      "/project/.omg/state/learnings/session2.md",
      "## Most Used Tools\n- Bash: 3x\n",
    );

    const agg = new LearningsAggregator("/project", deps);
    const result = await agg.aggregateLearnings();
    expect(result).toContain("Bash: 13x total");
    expect(result).toContain("index.ts: 8x total");
  });

  test("returns empty for no learnings", async () => {
    const deps = makeMemoryDeps();
    const agg = new LearningsAggregator("/project", deps);
    const result = await agg.aggregateLearnings();
    expect(result).toBe("");
  });

  test("saveCriticalPatterns writes to knowledge dir", async () => {
    const deps = makeMemoryDeps();
    deps.files.set(
      "/project/.omg/state/learnings/session1.md",
      "## Most Used Tools\n- Bash: 10x\n",
    );
    const agg = new LearningsAggregator("/project", deps);
    const path = await agg.saveCriticalPatterns();
    expect(path).toContain("critical-patterns.md");
    expect(deps.files.has(path)).toBe(true);
  });
});
