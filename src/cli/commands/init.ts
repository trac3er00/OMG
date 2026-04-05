import type { CommandModule } from "yargs";

export const initCommand: CommandModule = {
  command: "init",
  describe:
    "Interactive first-time setup wizard (doctor → plan → confirm → apply)",
  builder: (yargs) =>
    yargs
      .option("yes", {
        alias: "y",
        type: "boolean",
        description: "Auto-confirm all prompts",
        default: false,
      })
      .option("json", {
        type: "boolean",
        description: "Output results as JSON",
        default: false,
      }),
  handler: async (argv) => {
    const { initWizard } = await import("../../install/orchestrator.js");
    await initWizard({
      autoConfirm: Boolean(argv.yes),
      json: Boolean(argv.json),
    });
  },
};
