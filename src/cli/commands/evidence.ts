import { join } from "node:path";
import {
  parseDuration,
  pruneEvidence,
  queryEvidence,
  EVIDENCE_TYPES,
} from "../../evidence/retention.js";
import { StateResolver } from "../../state/state-resolver.js";

export const evidencePruneCommand = {
  command: "prune",
  describe: "Archive and remove evidence older than a given threshold",
  builder: (yargs: import("yargs").Argv) =>
    yargs
      .option("older-than", {
        type: "string",
        demandOption: true,
        describe: 'Duration threshold, e.g. "30d", "24h", "60m"',
      })
      .option("projectDir", {
        type: "string",
        describe: "Project directory override",
      })
      .option("json", {
        type: "boolean",
        default: false,
        describe: "Output as JSON",
      }),
  handler: async (argv: {
    olderThan: string;
    projectDir?: string;
    json?: boolean;
  }) => {
    const projectDir = argv.projectDir ?? process.cwd();
    const olderThanMs = parseDuration(argv.olderThan);
    const evidenceDir = join(projectDir, ".omg", "evidence");
    const archiveDir = join(projectDir, ".omg", "archive");

    const result = pruneEvidence({ evidenceDir, archiveDir, olderThanMs });

    if (argv.json) {
      process.stdout.write(JSON.stringify(result, null, 2) + "\n");
    } else {
      process.stdout.write(
        `Pruned: ${result.archived.length} archived, ${result.skipped.length} kept\n`,
      );
      for (const f of result.archived) {
        process.stdout.write(`  archived: ${f} → ${f}.gz\n`);
      }
    }
  },
};

export const evidenceQueryCommand = {
  command: "query",
  describe: "Query evidence records by type and age",
  builder: (yargs: import("yargs").Argv) =>
    yargs
      .option("since", {
        type: "string",
        describe: 'Filter evidence newer than duration, e.g. "7d"',
      })
      .option("type", {
        type: "string",
        choices: EVIDENCE_TYPES as unknown as string[],
        describe: "Filter by evidence type",
      })
      .option("projectDir", {
        type: "string",
        describe: "Project directory override",
      })
      .option("json", {
        type: "boolean",
        default: true,
        describe: "Output as JSON (default)",
      }),
  handler: async (argv: {
    since?: string;
    type?: string;
    projectDir?: string;
    json?: boolean;
  }) => {
    const projectDir = argv.projectDir ?? process.cwd();
    const resolver = new StateResolver(projectDir);
    const registryPath = resolver.resolve(
      join("ledger", "evidence-registry.jsonl"),
    );

    const queryOpts: Parameters<typeof queryEvidence>[0] = { registryPath };
    if (argv.since) queryOpts.sinceMs = parseDuration(argv.since);
    if (argv.type) queryOpts.type = argv.type;

    const result = queryEvidence(queryOpts);

    if (argv.json !== false) {
      process.stdout.write(JSON.stringify(result.records, null, 2) + "\n");
    } else {
      process.stdout.write(
        `Found ${result.filtered} of ${result.total} records\n`,
      );
      for (const r of result.records) {
        process.stdout.write(`  [${r.type}] ${r.runId} — ${r.path}\n`);
      }
    }
  },
};
