import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { CommandModule } from "yargs";

const VALID_CATEGORIES = [
  "decisions",
  "preferences",
  "failures",
  "open_loops",
  "team_context",
] as const;

type MemoryCategory = (typeof VALID_CATEGORIES)[number];

const VALID_TIERS = ["auto", "micro", "ship"] as const;

type MemoryTierName = (typeof VALID_TIERS)[number];

interface MemoryTierStatusRow {
  readonly name: MemoryTierName;
  readonly count: number;
  readonly size_bytes: number;
  readonly last_promoted: string | null;
  readonly last_demoted: string | null;
}

interface MemoryShowArgs {
  readonly category?: string;
}

interface MemoryTierStatusArgs {
  json?: boolean;
  tier?: MemoryTierName;
}

function buildSchemaCommand(
  projectDir: string,
  category: MemoryCategory,
): string {
  const escaped = projectDir.replace(/'/g, "\\'");
  return [
    "python3",
    "-c",
    `'import sys; sys.path.insert(0, "${escaped}"); ` +
      `from runtime.memory_schema import get_schema_description; ` +
      `print(get_schema_description("${category}"))'`,
  ].join(" ");
}

function getTierStatusPaths(projectDir: string): string[] {
  return [
    join(projectDir, ".omg", "state", "memory-tier-status.json"),
    join(projectDir, ".omg", "state", "tier-status.json"),
  ];
}

function emptyTierStatus(): MemoryTierStatusRow[] {
  return VALID_TIERS.map((name) => ({
    name,
    count: 0,
    size_bytes: 0,
    last_promoted: null,
    last_demoted: null,
  }));
}

function normalizeTierStatusEntry(
  name: string,
  entry: Partial<MemoryTierStatusRow> & Record<string, unknown>,
): MemoryTierStatusRow | null {
  if (!VALID_TIERS.includes(name as MemoryTierName)) {
    return null;
  }

  const tierName = name as MemoryTierName;
  const count = Number(entry.count ?? 0);
  const sizeBytes = Number(entry.size_bytes ?? 0);
  const lastPromoted =
    typeof entry.last_promoted === "string" ? entry.last_promoted : null;
  const lastDemoted =
    typeof entry.last_demoted === "string" ? entry.last_demoted : null;

  return {
    name: tierName,
    count: Number.isFinite(count) ? count : 0,
    size_bytes: Number.isFinite(sizeBytes) ? sizeBytes : 0,
    last_promoted: lastPromoted,
    last_demoted: lastDemoted,
  };
}

function parseTierStatusPayload(
  payload: unknown,
): MemoryTierStatusRow[] | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const entries: MemoryTierStatusRow[] = [];

  if (Array.isArray(payload)) {
    for (const entry of payload) {
      if (!entry || typeof entry !== "object") {
        continue;
      }
      const record = entry as Record<string, unknown>;
      const tierName = typeof record.name === "string" ? record.name : "";
      const normalized = normalizeTierStatusEntry(tierName, record);
      if (normalized) {
        entries.push(normalized);
      }
    }
  } else {
    const record = payload as Record<string, unknown>;
    if (Array.isArray(record.tiers)) {
      return parseTierStatusPayload(record.tiers);
    }

    for (const tier of VALID_TIERS) {
      const entry = record[tier];
      if (!entry || typeof entry !== "object") {
        continue;
      }
      const normalized = normalizeTierStatusEntry(
        tier,
        entry as Partial<MemoryTierStatusRow> & Record<string, unknown>,
      );
      if (normalized) {
        entries.push(normalized);
      }
    }
  }

  if (!entries.length) {
    return null;
  }

  const byTier = new Map(entries.map((entry) => [entry.name, entry]));
  return VALID_TIERS.map(
    (tier) =>
      byTier.get(tier) ?? {
        name: tier,
        count: 0,
        size_bytes: 0,
        last_promoted: null,
        last_demoted: null,
      },
  );
}

function loadTierStatus(projectDir: string): MemoryTierStatusRow[] {
  for (const statusPath of getTierStatusPaths(projectDir)) {
    try {
      const raw = readFileSync(statusPath, "utf8");
      const parsed = JSON.parse(raw) as unknown;
      const rows = parseTierStatusPayload(parsed);
      if (rows) {
        return rows;
      }
    } catch {
      continue;
    }
  }

  return emptyTierStatus();
}

function formatBytes(sizeBytes: number): string {
  if (!Number.isFinite(sizeBytes) || sizeBytes <= 0) {
    return "0 B";
  }
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }
  const units = ["KB", "MB", "GB", "TB"];
  let value = sizeBytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value % 1 === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unitIndex]}`;
}

function displayTimestamp(value: string | null): string {
  return value ?? "-";
}

function printTierStatusTable(rows: MemoryTierStatusRow[]): void {
  console.log("CMMS Tier Status");
  console.log("─────────────────────────────────────────────");
  console.log(
    ["Tier", "Items", "Size", "Last Promoted", "Last Demoted"].join(" │ "),
  );
  for (const row of rows) {
    console.log(
      [
        row.name.toUpperCase().padEnd(4),
        String(row.count).padEnd(5),
        formatBytes(row.size_bytes).padEnd(8),
        displayTimestamp(row.last_promoted).padEnd(16),
        displayTimestamp(row.last_demoted).padEnd(16),
      ].join(" │ "),
    );
  }
  console.log("─────────────────────────────────────────────");
}

export function runMemoryTierStatus(options: MemoryTierStatusArgs = {}): void {
  const { json = false, tier } = options;
  const projectDir = process.cwd();
  const rows = loadTierStatus(projectDir);
  const filteredRows = tier
    ? rows.filter((entry) => entry.name === tier)
    : rows;

  if (json) {
    console.log(JSON.stringify(filteredRows, null, 2));
    return;
  }

  printTierStatusTable(filteredRows);
}

export function runMemoryShow(category?: string): void {
  const projectDir = process.cwd();

  if (!category) {
    console.log("Available memory categories:");
    VALID_CATEGORIES.forEach((entry) => {
      console.log(`  ${entry}`);
    });
    console.log("\nUsage: npx omg memory show <category>");
    return;
  }

  if (!VALID_CATEGORIES.includes(category as MemoryCategory)) {
    console.error(
      `Unknown category: ${category}. Valid: ${VALID_CATEGORIES.join(", ")}`,
    );
    process.exit(1);
  }

  const safeCategory = category as MemoryCategory;

  console.log(`Memory category: ${safeCategory}`);
  console.log("(Schema validation available via runtime.memory_schema)");
  console.log("\nCategory schema:");

  try {
    const desc = execSync(buildSchemaCommand(projectDir, safeCategory), {
      encoding: "utf8",
      cwd: projectDir,
      timeout: 30_000,
    }).trimEnd();
    console.log(desc);
  } catch {
    console.log(`Category: ${safeCategory} (schema info unavailable)`);
  }
}

export const memoryCommand: CommandModule<object, MemoryShowArgs> = {
  command: "memory",
  describe: "Inspect structured memory categories",
  builder: (yargs) =>
    yargs
      .command(
        "show [category]",
        "Show a structured memory category schema",
        (command) =>
          command.positional("category", {
            type: "string",
            describe: "Structured memory category",
          }),
        (argv) => {
          runMemoryShow(argv.category);
        },
      )
      .command(
        "tier-status",
        "Show CMMS tier metadata",
        (command) =>
          command
            .option("json", {
              type: "boolean",
              description: "Emit JSON instead of a table",
              default: false,
            })
            .option("tier", {
              type: "string",
              choices: VALID_TIERS as readonly MemoryTierName[],
              description: "Filter to a single tier",
            }),
        (argv) => {
          const options: MemoryTierStatusArgs = {};
          if (argv.json) {
            options.json = true;
          }
          if (argv.tier) {
            options.tier = argv.tier as MemoryTierName;
          }
          runMemoryTierStatus(options);
        },
      )
      .demandCommand(1, "Specify a memory subcommand: show, tier-status"),
  handler: () => {},
};
