import type { Persona } from "./detector.js";

const TECHNICAL_KEYS = new Set([
  "debug",
  "details",
  "diff",
  "error",
  "errors",
  "log",
  "logs",
  "raw",
  "stack",
  "technical",
  "trace",
]);

const BEGINNER_PRIORITY = [
  "result",
  "summary",
  "status",
  "message",
  "output",
  "nextStep",
  "next_action",
  "progress",
];

const EXEC_PRIORITY = [
  "status",
  "summary",
  "progress",
  "cost",
  "budget",
  "roi",
  "impact",
  "team",
  "risk",
  "timeline",
];

function formatLabel(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^./, (match) => match.toUpperCase());
}

function stringify(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }

  if (
    typeof value === "number" ||
    typeof value === "boolean" ||
    value === null ||
    value === undefined
  ) {
    return String(value);
  }

  if (Array.isArray(value)) {
    if (
      value.every(
        (item) => typeof item === "string" || typeof item === "number",
      )
    ) {
      return value.map((item) => String(item)).join(", ");
    }
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function collectEntries(
  data: Record<string, unknown>,
  priority: readonly string[],
  options?: { excludeTechnical?: boolean },
): Array<[string, unknown]> {
  const entries = Object.entries(data);
  const used = new Set<string>();
  const result: Array<[string, unknown]> = [];

  for (const key of priority) {
    if (key in data) {
      result.push([key, data[key]]);
      used.add(key);
    }
  }

  for (const [key, value] of entries) {
    if (used.has(key)) {
      continue;
    }

    if (options?.excludeTechnical && TECHNICAL_KEYS.has(key)) {
      continue;
    }

    result.push([key, value]);
  }

  return result;
}

function formatBeginner(data: Record<string, unknown>): string {
  const entries = collectEntries(data, BEGINNER_PRIORITY, {
    excludeTechnical: true,
  })
    .filter(([, value]) => value !== undefined)
    .slice(0, 5);

  if (entries.length === 0) {
    return "No results yet.";
  }

  const lines = ["Results"];
  for (const [key, value] of entries) {
    lines.push(`- ${formatLabel(key)}: ${stringify(value)}`);
  }
  return lines.join("\n");
}

function formatEngineer(data: Record<string, unknown>): string {
  const entries = collectEntries(data, BEGINNER_PRIORITY);
  if (entries.length === 0) {
    return "Technical view\n- No data available.";
  }

  const lines = ["Technical view"];
  for (const [key, value] of entries) {
    lines.push(`\n${formatLabel(key)}:`);
    lines.push(stringify(value));
  }
  return lines.join("\n");
}

function formatExec(data: Record<string, unknown>): string {
  const summary =
    (typeof data.summary === "string" && data.summary) ||
    (typeof data.result === "string" && data.result) ||
    (typeof data.message === "string" && data.message) ||
    "No executive summary available.";

  const metrics = collectEntries(data, EXEC_PRIORITY, {
    excludeTechnical: true,
  })
    .filter(([key, value]) => key !== "summary" && value !== undefined)
    .slice(0, 6);

  const lines = ["Executive summary", summary];

  if (metrics.length > 0) {
    lines.push("", "Key metrics");
    for (const [key, value] of metrics) {
      lines.push(`- ${formatLabel(key)}: ${stringify(value)}`);
    }
  }

  return lines.join("\n");
}

export function formatForPersona(
  data: Record<string, unknown>,
  persona: Persona,
): string {
  if (persona === "engineer") {
    return formatEngineer(data);
  }

  if (persona === "exec") {
    return formatExec(data);
  }

  return formatBeginner(data);
}
