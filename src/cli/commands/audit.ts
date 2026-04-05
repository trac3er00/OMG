import type { CommandModule } from "yargs";

interface AuditExportArgs {
  readonly format: string;
  readonly output: string;
  readonly projectDir?: string;
}

export const auditExportCommand: CommandModule<object, AuditExportArgs> = {
  command: "export",
  describe: "Export audit logs in SIEM-compatible format (enterprise only)",
  builder: (yargs) =>
    yargs
      .option("format", {
        type: "string",
        choices: ["jsonl"],
        default: "jsonl",
        describe: "Export format",
      })
      .option("output", {
        type: "string",
        demandOption: true,
        describe: "Output file path, or '-' for stdout",
      })
      .option("projectDir", {
        type: "string",
        describe: "Project directory override",
      }) as never,
  handler: async (argv) => {
    const { AuditTrail, SiemChannelError } =
      await import("../../security/audit-trail.js");
    const trailOpts = argv.projectDir ? { projectDir: argv.projectDir } : {};
    const trail = AuditTrail.create(trailOpts);

    try {
      const exportOpts = {
        format: argv.format as "jsonl",
        output: argv.output,
        ...(argv.projectDir ? { projectDir: argv.projectDir } : {}),
      };
      const result = trail.exportSiem(exportOpts);

      if (argv.output !== "-") {
        console.log(
          `Exported ${result.eventCount} audit events to ${result.output}`,
        );
      }
    } catch (error) {
      if (error instanceof SiemChannelError) {
        console.error(`Error: ${error.message}`);
        process.exit(1);
      }
      throw error;
    }
  },
};
