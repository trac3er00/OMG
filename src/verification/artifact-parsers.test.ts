import { describe, test, expect } from "bun:test";
import {
  parseJUnit,
  parseSarif,
  parseCoverage,
  parseBrowserTrace,
} from "./artifact-parsers.js";

// ---------------------------------------------------------------------------
// JUnit XML fixtures
// ---------------------------------------------------------------------------

const VALID_JUNIT = `<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="test suite" tests="5" failures="0" errors="0" time="1.23">
  <testsuite name="my.suite" tests="5" failures="0" errors="0" time="1.0">
    <testcase name="test_one" classname="my.suite" time="0.2"/>
    <testcase name="test_two" classname="my.suite" time="0.3"/>
    <testcase name="test_three" classname="my.suite" time="0.5"/>
  </testsuite>
</testsuites>`;

const JUNIT_WITH_FAILURES = `<?xml version="1.0" encoding="UTF-8"?>
<testsuites tests="3" failures="1" errors="0" time="0.5">
  <testsuite name="suite" tests="3" failures="1" errors="0">
    <testcase name="pass_test" time="0.1"/>
    <testcase name="fail_test" time="0.2">
      <failure message="Expected 1 to equal 2">AssertionError</failure>
    </testcase>
  </testsuite>
</testsuites>`;

const JUNIT_SINGLE_SUITE = `<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="single" tests="2" failures="0" errors="1" time="0.4">
  <testcase name="ok_test" time="0.1"/>
  <testcase name="err_test" time="0.3">
    <error message="NullPointerException">stack trace</error>
  </testcase>
</testsuite>`;

describe("parseJUnit", () => {
  test("parses valid JUnit XML", () => {
    const r = parseJUnit(VALID_JUNIT);
    expect(r.parsed).toBe(true);
    expect(r.artifact_type).toBe("junit");
    expect(r.summary.tests).toBeGreaterThan(0);
    expect(r.summary.failures).toBe(0);
    expect(r.summary.errors).toBe(0);
  });

  test("detects test failures", () => {
    const r = parseJUnit(JUNIT_WITH_FAILURES);
    expect(r.parsed).toBe(true);
    expect(r.summary.failures).toBe(1);
    const msgs = (r.summary as Record<string, unknown>)["failureMessages"] as string[];
    expect(msgs.length).toBeGreaterThan(0);
  });

  test("parses single testsuite root", () => {
    const r = parseJUnit(JUNIT_SINGLE_SUITE);
    expect(r.parsed).toBe(true);
    expect(r.summary.tests).toBe(2);
    expect(r.summary.errors).toBe(1);
  });

  test("handles malformed XML gracefully", () => {
    const r = parseJUnit("<not valid xml>>>");
    expect(r.parsed).toBe(false);
    expect(r.error).toBeTruthy();
  });

  test("handles empty XML gracefully", () => {
    const r = parseJUnit("");
    expect(r.parsed).toBe(false);
    expect(r.error).toBeTruthy();
  });

  test("rejects non-junit root element", () => {
    const r = parseJUnit('<html><body>not junit</body></html>');
    expect(r.parsed).toBe(false);
    expect(r.error).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// SARIF fixtures
// ---------------------------------------------------------------------------

const VALID_SARIF = JSON.stringify({
  version: "2.1.0",
  runs: [
    {
      tool: { driver: { name: "ESLint", version: "8.0.0" } },
      results: [
        {
          ruleId: "no-unused-vars",
          level: "warning",
          message: { text: "x is defined but never used" },
        },
        {
          ruleId: "no-console",
          level: "error",
          message: { text: "Unexpected console statement" },
        },
      ],
    },
  ],
});

describe("parseSarif", () => {
  test("parses valid SARIF JSON", () => {
    const r = parseSarif(VALID_SARIF);
    expect(r.parsed).toBe(true);
    expect(r.artifact_type).toBe("sarif");
    expect(r.summary.totalResults).toBe(2);
    expect(r.summary.toolName).toBe("ESLint");
    expect(r.summary.warnings).toBeGreaterThanOrEqual(0);
    expect(r.summary.errors).toBeGreaterThanOrEqual(0);
  });

  test("handles missing runs gracefully", () => {
    const r = parseSarif(JSON.stringify({ version: "2.1.0" }));
    expect(r.parsed).toBe(false);
    expect(r.error).toBeTruthy();
  });

  test("handles invalid JSON gracefully", () => {
    const r = parseSarif("not json{{{");
    expect(r.parsed).toBe(false);
    expect(r.error).toBeTruthy();
  });

  test("handles empty string gracefully", () => {
    const r = parseSarif("");
    expect(r.parsed).toBe(false);
    expect(r.error).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Coverage fixtures
// ---------------------------------------------------------------------------

describe("parseCoverage", () => {
  test("parses valid coverage object", () => {
    const r = parseCoverage({ line_rate: 0.85, branch_rate: 0.75 });
    expect(r.parsed).toBe(true);
    expect(r.artifact_type).toBe("coverage");
    expect(r.summary.lineRate).toBe(0.85);
    expect(r.summary.branchRate).toBe(0.75);
    expect(r.summary.lineCoverage).toBe(85);
  });

  test("handles null gracefully", () => {
    const r = parseCoverage(null);
    expect(r.parsed).toBe(false);
    expect(r.error).toBeTruthy();
  });

  test("handles undefined gracefully", () => {
    const r = parseCoverage(undefined);
    expect(r.parsed).toBe(false);
    expect(r.error).toBeTruthy();
  });

  test("handles non-object gracefully", () => {
    const r = parseCoverage("not an object");
    expect(r.parsed).toBe(false);
    expect(r.error).toBeTruthy();
  });

  test("defaults missing rates to zero", () => {
    const r = parseCoverage({});
    expect(r.parsed).toBe(true);
    expect(r.summary.lineRate).toBe(0);
    expect(r.summary.branchRate).toBe(0);
  });
});

// ---------------------------------------------------------------------------
// Browser trace fixtures
// ---------------------------------------------------------------------------

const VALID_TRACE = JSON.stringify({
  trace: { some: "data" },
  events: [
    { type: "click", ts: 1000 },
    { type: "navigate", ts: 2000 },
  ],
});

describe("parseBrowserTrace", () => {
  test("parses valid browser trace JSON", () => {
    const r = parseBrowserTrace(VALID_TRACE);
    expect(r.parsed).toBe(true);
    expect(r.artifact_type).toBe("browser_trace");
    expect(r.summary.hasTrace).toBe(true);
    expect(r.summary.eventCount).toBe(2);
  });

  test("accepts trace-only (no events)", () => {
    const r = parseBrowserTrace(JSON.stringify({ trace: {} }));
    expect(r.parsed).toBe(true);
    expect(r.summary.hasTrace).toBe(true);
    expect(r.summary.eventCount).toBe(0);
  });

  test("accepts events-only (no trace key)", () => {
    const r = parseBrowserTrace(JSON.stringify({ events: [{ type: "x" }] }));
    expect(r.parsed).toBe(true);
    expect(r.summary.hasTrace).toBe(false);
    expect(r.summary.eventCount).toBe(1);
  });

  test("rejects payload missing both trace and events", () => {
    const r = parseBrowserTrace(JSON.stringify({ foo: "bar" }));
    expect(r.parsed).toBe(false);
    expect(r.error).toBeTruthy();
  });

  test("handles invalid JSON gracefully", () => {
    const r = parseBrowserTrace("<<<not json");
    expect(r.parsed).toBe(false);
    expect(r.error).toBeTruthy();
  });

  test("handles empty string gracefully", () => {
    const r = parseBrowserTrace("");
    expect(r.parsed).toBe(false);
    expect(r.error).toBeTruthy();
  });
});
