import { describe, expect, test } from "bun:test";

import { TokenBudget } from "./budget.js";
import { LogMonitor } from "./monitor.js";

describe("TokenBudget.trackSessionTokens", () => {
  test("accumulates tokens for a single session", () => {
    const budget = new TokenBudget();
    budget.trackSessionTokens("session-1", 100);
    budget.trackSessionTokens("session-1", 200);
    expect(budget.getSessionTokens("session-1")).toBe(300);
  });

  test("tracks multiple sessions independently", () => {
    const budget = new TokenBudget();
    budget.trackSessionTokens("s1", 500);
    budget.trackSessionTokens("s2", 300);
    expect(budget.getSessionTokens("s1")).toBe(500);
    expect(budget.getSessionTokens("s2")).toBe(300);
  });

  test("returns 0 for unknown session", () => {
    const budget = new TokenBudget();
    expect(budget.getSessionTokens("unknown")).toBe(0);
  });
});

describe("TokenBudget.trackTaskTokens", () => {
  test("accumulates tokens for a single task", () => {
    const budget = new TokenBudget();
    budget.trackTaskTokens("task-1", 150);
    budget.trackTaskTokens("task-1", 250);
    expect(budget.getTaskTokens("task-1")).toBe(400);
  });

  test("total equals sum of all tasks", () => {
    const budget = new TokenBudget();
    budget.trackTaskTokens("t1", 100);
    budget.trackTaskTokens("t2", 200);
    budget.trackTaskTokens("t3", 300);
    expect(budget.getTotalTokens()).toBe(600);
  });
});

describe("TokenBudget.getReport", () => {
  test("report totals match tracked values", () => {
    const budget = new TokenBudget();
    budget.trackTaskTokens("t1", 100);
    budget.trackTaskTokens("t2", 200);
    budget.trackTaskTokens("t3", 300);
    budget.trackSessionTokens("s1", 600);

    const report = budget.getReport();
    expect(report.totalTokens).toBe(600);
    expect(report.taskTokens.get("t1")).toBe(100);
    expect(report.taskTokens.get("t2")).toBe(200);
    expect(report.taskTokens.get("t3")).toBe(300);
    expect(report.sessionTokens.get("s1")).toBe(600);
  });

  test("no waste when usage is clean", () => {
    const budget = new TokenBudget();
    budget.trackTaskTokens("t1", 100);
    budget.trackTaskTokens("t2", 200);

    const report = budget.getReport();
    expect(report.wastedTokens).toBe(0);
    expect(report.recommendations).toContain(
      "No waste patterns detected — token usage looks efficient",
    );
  });
});

describe("TokenBudget waste detection: repeated errors", () => {
  test("detects repeated error pattern from identical-size bursts", () => {
    const budget = new TokenBudget();
    budget.trackTaskTokens("failing-task", 50);
    budget.trackTaskTokens("failing-task", 50);
    budget.trackTaskTokens("failing-task", 50);
    budget.trackTaskTokens("failing-task", 50);

    const report = budget.getReport();
    const repeatedError = report.wastePatterns.find(
      (p) => p.type === "repeated_error",
    );
    expect(repeatedError).toBeDefined();
    expect(repeatedError!.occurrences).toBeGreaterThanOrEqual(3);
    expect(repeatedError!.wastedTokens).toBeGreaterThan(0);
    expect(report.recommendations).toContain(
      "Fix root cause of repeated errors to avoid retry token waste",
    );
  });
});

describe("TokenBudget waste detection: duplicate research", () => {
  test("detects tasks with identical token consumption", () => {
    const budget = new TokenBudget();
    budget.trackTaskTokens("research-a", 500);
    budget.trackTaskTokens("research-b", 500);

    const report = budget.getReport();
    const dupResearch = report.wastePatterns.find(
      (p) => p.type === "duplicate_research",
    );
    expect(dupResearch).toBeDefined();
    expect(dupResearch!.occurrences).toBe(2);
    expect(dupResearch!.wastedTokens).toBe(500);
  });
});

describe("TokenBudget waste detection: context rebuilds", () => {
  test("detects large token bursts suggesting context rebuilds", () => {
    const budget = new TokenBudget();
    budget.trackSessionTokens("s1", 15_000);
    budget.trackSessionTokens("s1", 12_000);
    budget.trackSessionTokens("s1", 11_000);

    const report = budget.getReport();
    const rebuild = report.wastePatterns.find(
      (p) => p.type === "context_rebuild",
    );
    expect(rebuild).toBeDefined();
    expect(rebuild!.occurrences).toBe(3);
    expect(rebuild!.wastedTokens).toBe(23_000);
    expect(report.recommendations).toContain(
      "Use session checkpoints to avoid expensive context rebuilds",
    );
  });
});

describe("LogMonitor.parseLogContent", () => {
  test("parses standard log lines", () => {
    const content = [
      "[2024-01-15T10:00:00Z] ERROR Connection timeout",
      "[2024-01-15T10:01:00Z] WARN Memory high",
      "[2024-01-15T10:02:00Z] INFO Task started",
    ].join("\n");

    const monitor = new LogMonitor();
    const entries = monitor.parseLogContent(content);
    expect(entries).toHaveLength(3);
    expect(entries[0]!.level).toBe("error");
    expect(entries[1]!.level).toBe("warn");
    expect(entries[2]!.level).toBe("info");
  });

  test("handles format without brackets", () => {
    const content = "2024-01-15 10:00:00 ERROR Something broke\n";
    const monitor = new LogMonitor();
    const entries = monitor.parseLogContent(content);
    expect(entries).toHaveLength(1);
    expect(entries[0]!.message).toBe("Something broke");
  });

  test("skips malformed lines", () => {
    const content = "not a log line\n[2024-01-15T10:00:00Z] ERROR Valid\n";
    const monitor = new LogMonitor();
    const entries = monitor.parseLogContent(content);
    expect(entries).toHaveLength(1);
  });
});

describe("LogMonitor.analyze", () => {
  test("counts errors and warnings", () => {
    const monitor = new LogMonitor();
    const entries = monitor.parseLogContent(
      [
        "[2024-01-15T10:00:00Z] ERROR err1",
        "[2024-01-15T10:01:00Z] ERROR err2",
        "[2024-01-15T10:02:00Z] WARN w1",
        "[2024-01-15T10:03:00Z] INFO ok",
      ].join("\n"),
    );

    const report = monitor.analyze(entries);
    expect(report.totalLines).toBe(4);
    expect(report.errorCount).toBe(2);
    expect(report.warnCount).toBe(1);
  });

  test("detects repeated error waste indicator", () => {
    const lines = Array.from(
      { length: 5 },
      (_, i) => `[2024-01-15T10:0${i}:00Z] ERROR Connection refused`,
    ).join("\n");

    const monitor = new LogMonitor();
    const report = monitor.analyzeContent(lines);

    const repeatedIndicator = report.wasteIndicators.find(
      (w) => w.type === "repeated_error",
    );
    expect(repeatedIndicator).toBeDefined();
    expect(repeatedIndicator!.severity).toBe("medium");
  });

  test("detects context rebuild waste indicator", () => {
    const lines = [
      "[2024-01-15T10:00:00Z] INFO rebuilding context for session",
      "[2024-01-15T10:01:00Z] INFO context expired",
      "[2024-01-15T10:02:00Z] INFO cache miss on lookup",
    ].join("\n");

    const monitor = new LogMonitor();
    const report = monitor.analyzeContent(lines);

    const rebuildIndicator = report.wasteIndicators.find(
      (w) => w.type === "context_rebuild",
    );
    expect(rebuildIndicator).toBeDefined();
    expect(rebuildIndicator!.severity).toBe("high");
  });

  test("groups errors by normalized message", () => {
    const lines = [
      "[2024-01-15T10:00:00Z] ERROR Failed for user abcdef01-def4-5678-9012-345678901234",
      "[2024-01-15T10:01:00Z] ERROR Failed for user fff12300-aaa4-bbb8-ccc2-dddeeefff012",
      "[2024-01-15T10:02:00Z] ERROR Failed for user 11122233-4455-6677-8899-aabbccddeeff",
    ].join("\n");

    const monitor = new LogMonitor();
    const report = monitor.analyzeContent(lines);

    expect(report.errorPatterns).toHaveLength(1);
    expect(report.errorPatterns[0]!.count).toBe(3);
    expect(report.errorPatterns[0]!.message).toContain("<UUID>");
  });
});

describe("LogMonitor.analyzeContent", () => {
  test("empty content produces empty report", () => {
    const monitor = new LogMonitor();
    const report = monitor.analyzeContent("");
    expect(report.totalLines).toBe(0);
    expect(report.errorCount).toBe(0);
    expect(report.wasteIndicators).toHaveLength(0);
  });
});

describe("QA: end-to-end efficiency tracking", () => {
  test("track 3 tasks and verify total equals sum", () => {
    const budget = new TokenBudget();
    budget.trackTaskTokens("task-a", 1000);
    budget.trackTaskTokens("task-b", 2000);
    budget.trackTaskTokens("task-c", 3000);

    const report = budget.getReport();
    expect(report.totalTokens).toBe(6000);
    expect(report.taskTokens.size).toBe(3);
  });

  test("simulate repeated error pattern and verify waste detected", () => {
    const budget = new TokenBudget();
    for (let i = 0; i < 5; i++) {
      budget.trackTaskTokens("retry-task", 100);
    }

    const report = budget.getReport();
    expect(report.wastePatterns.length).toBeGreaterThanOrEqual(1);
    expect(report.wastedTokens).toBeGreaterThan(0);
    expect(report.savings).toBeGreaterThan(0);
  });
});
