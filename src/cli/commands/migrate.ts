import type { CommandModule } from "yargs";
import { migrateConfig } from "../../config/migration.js";

interface MigrateArgs {
  readonly from: string;
  readonly to: string;
  readonly dryRun?: boolean;
  readonly apply?: boolean;
}

export const migrateCommand: CommandModule<object, MigrateArgs> = {
  command: "migrate",
  describe: "Migrate OMG project config across versions",
  builder: (yargs) =>
    yargs
      .option("from", {
        type: "string",
        demandOption: true,
        describe: "Source OMG version (example: 2.3.0)",
      })
      .option("to", {
        type: "string",
        demandOption: true,
        describe: "Target OMG version (example: 3.0.0)",
      })
      .option("dry-run", {
        type: "boolean",
        default: true,
        describe: "Preview migration without writing files",
      })
      .option("apply", {
        type: "boolean",
        default: false,
        describe: "Apply migration and create rollback backups",
      })
      .check((argv) => {
        if (Boolean(argv.apply) && Boolean(argv["dry-run"])) {
          throw new Error("Choose only one mode: --apply or --dry-run");
        }
        return true;
      }),
  handler: (argv): void => {
    const report = migrateConfig({
      from: argv.from,
      to: argv.to,
      apply: Boolean(argv.apply),
      dryRun: Boolean(argv["dry-run"]),
      projectDir: process.cwd(),
    });

    console.log(JSON.stringify(report, null, 2));

    if (report.errors.length > 0) {
      process.exitCode = 1;
    }
  },
};
