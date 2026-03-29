export type { ArtifactParseResult } from "../types/evidence.js";

// ---------------------------------------------------------------------------
// JUnit XML parser (regex-based, no DOM dependency)
// ---------------------------------------------------------------------------

export interface JUnitSummary {
  readonly tests: number;
  readonly failures: number;
  readonly errors: number;
  readonly time: number;
  readonly failureMessages: readonly string[];
}

export interface JUnitResult {
  readonly artifact_type: "junit";
  readonly path: string;
  readonly parsed: boolean;
  readonly summary: JUnitSummary | Record<string, unknown>;
  readonly error?: string;
}

function extractAttr(attrs: string, name: string): string | null {
  const m = attrs.match(new RegExp(`${name}="([^"]*)"`, "i"));
  return m?.[1] ?? null;
}

function parseJUnitXml(
  xml: string,
): { summary: JUnitSummary } | { error: string } {
  const rootMatch = xml.match(/<(testsuites?)\b([^>]*)>/i);
  if (!rootMatch) return { error: "Failed to parse JUnit XML" };

  const rootName = rootMatch[1]?.toLowerCase() ?? "";
  if (rootName !== "testsuite" && rootName !== "testsuites") {
    return { error: `Invalid JUnit root element: ${rootName}` };
  }

  const attrs = rootMatch[2] ?? "";
  const tests = parseInt(extractAttr(attrs, "tests") ?? "0", 10);
  const failures = parseInt(extractAttr(attrs, "failures") ?? "0", 10);
  const errors = parseInt(extractAttr(attrs, "errors") ?? "0", 10);
  const time = parseFloat(extractAttr(attrs, "time") ?? "0");

  const failureMessages: string[] = [];
  const failureRe = /<failure[^>]*message="([^"]*)"[^>]*>/gi;
  let m: RegExpExecArray | null;
  while ((m = failureRe.exec(xml)) !== null) {
    if (m[1]) failureMessages.push(m[1]);
  }

  return { summary: { tests, failures, errors, time, failureMessages } };
}

export function parseJUnit(xml: string): JUnitResult {
  if (!xml.trim()) {
    return {
      artifact_type: "junit",
      path: "",
      parsed: false,
      summary: {},
      error: "Empty XML",
    };
  }

  const result = parseJUnitXml(xml);
  if ("error" in result) {
    return {
      artifact_type: "junit",
      path: "",
      parsed: false,
      summary: {},
      error: result.error,
    };
  }

  return {
    artifact_type: "junit",
    path: "",
    parsed: true,
    summary: result.summary,
  };
}

// ---------------------------------------------------------------------------
// SARIF JSON parser
// ---------------------------------------------------------------------------

export interface SarifSummary {
  readonly totalResults: number;
  readonly toolName: string;
  readonly warnings: number;
  readonly errors: number;
  readonly runCount: number;
  readonly version: string;
}

export interface SarifResult {
  readonly artifact_type: "sarif";
  readonly path: string;
  readonly parsed: boolean;
  readonly summary: SarifSummary | Record<string, unknown>;
  readonly error?: string;
}

interface SarifPayload {
  version?: string;
  runs?: Array<{
    tool?: { driver?: { name?: string } };
    results?: Array<{ level?: string }>;
  }>;
}

export function parseSarif(json: string): SarifResult {
  let data: SarifPayload;
  try {
    data = JSON.parse(json) as SarifPayload;
  } catch (err) {
    return {
      artifact_type: "sarif",
      path: "",
      parsed: false,
      summary: {},
      error: err instanceof Error ? err.message : String(err),
    };
  }

  const runs = data.runs;
  if (!Array.isArray(runs)) {
    return {
      artifact_type: "sarif",
      path: "",
      parsed: false,
      summary: {},
      error: "sarif_missing_runs",
    };
  }

  let warnings = 0;
  let errors = 0;
  let totalResults = 0;

  for (const run of runs) {
    const results = run.results ?? [];
    totalResults += results.length;
    for (const r of results) {
      if (r.level === "error") errors++;
      else warnings++;
    }
  }

  const toolName = runs[0]?.tool?.driver?.name ?? "unknown";
  const version = String(data.version ?? "").trim();

  return {
    artifact_type: "sarif",
    path: "",
    parsed: true,
    summary: { totalResults, toolName, warnings, errors, runCount: runs.length, version },
  };
}

// ---------------------------------------------------------------------------
// Coverage parser
// ---------------------------------------------------------------------------

export interface CoverageSummary {
  readonly lineRate: number;
  readonly branchRate: number;
  readonly lineCoverage: number;
}

export interface CoverageResult {
  readonly artifact_type: "coverage";
  readonly path: string;
  readonly parsed: boolean;
  readonly summary: CoverageSummary | Record<string, unknown>;
  readonly error?: string;
}

export function parseCoverage(data: unknown): CoverageResult {
  if (data == null || typeof data !== "object") {
    return {
      artifact_type: "coverage",
      path: "",
      parsed: false,
      summary: {},
      error: "Invalid coverage data",
    };
  }

  const d = data as Record<string, unknown>;
  const lineRate = typeof d["line_rate"] === "number" ? d["line_rate"] : 0;
  const branchRate = typeof d["branch_rate"] === "number" ? d["branch_rate"] : 0;

  return {
    artifact_type: "coverage",
    path: "",
    parsed: true,
    summary: { lineRate, branchRate, lineCoverage: lineRate * 100 },
  };
}

// ---------------------------------------------------------------------------
// Browser trace parser
// ---------------------------------------------------------------------------

export interface BrowserTraceSummary {
  readonly hasTrace: boolean;
  readonly eventCount: number;
}

export interface BrowserTraceResult {
  readonly artifact_type: "browser_trace";
  readonly path: string;
  readonly parsed: boolean;
  readonly summary: BrowserTraceSummary | Record<string, unknown>;
  readonly error?: string;
}

interface BrowserTracePayload {
  trace?: unknown;
  events?: unknown[];
}

export function parseBrowserTrace(json: string): BrowserTraceResult {
  let data: BrowserTracePayload;
  try {
    data = JSON.parse(json) as BrowserTracePayload;
  } catch (err) {
    return {
      artifact_type: "browser_trace",
      path: "",
      parsed: false,
      summary: {},
      error: err instanceof Error ? err.message : String(err),
    };
  }

  if (typeof data !== "object" || data === null) {
    return {
      artifact_type: "browser_trace",
      path: "",
      parsed: false,
      summary: {},
      error: "browser_trace_invalid_payload",
    };
  }

  const hasTrace = "trace" in data;
  const hasEvents = Array.isArray(data.events);

  if (!hasTrace && !hasEvents) {
    return {
      artifact_type: "browser_trace",
      path: "",
      parsed: false,
      summary: {},
      error: "browser_trace_missing_trace_or_events",
    };
  }

  return {
    artifact_type: "browser_trace",
    path: "",
    parsed: true,
    summary: {
      hasTrace,
      eventCount: hasEvents ? data.events!.length : 0,
    },
  };
}
