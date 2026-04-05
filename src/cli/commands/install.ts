import type { CommandModule } from "yargs";
import { SetupOrchestrator } from "../../install/orchestrator.js";
import { InstallPlanner } from "../../install/planner.js";

interface InstallArgs {
  readonly plan?: boolean;
  readonly apply?: boolean;
}

function printLines(lines: readonly string[]): void {
  for (const line of lines) {
    console.log(line);
  }
}

export const installCommand: CommandModule<object, InstallArgs> = {
  command: "install",
  describe: "Plan or apply OMG host setup",
  builder: (command) =>
    command
      .option("plan", {
        type: "boolean",
        default: false,
        describe: "Preview install actions without mutations",
      })
      .option("apply", {
        type: "boolean",
        default: false,
        describe: "Apply install actions to detected hosts",
      })
      .check((argv) => {
        if (argv.plan && argv.apply) {
          throw new Error("Choose only one mode: --plan or --apply");
        }
        if (!argv.plan && !argv.apply) {
          throw new Error("Specify --plan or --apply");
        }
        return true;
      }),
  handler: async (args): Promise<void> => {
    const orchestrator = SetupOrchestrator.create(InstallPlanner.create());

    if (args.plan) {
      const result = await orchestrator.plan();
      printLines(result.preview);
      return;
    }

    const result = await orchestrator.apply();
    printLines(result.preview);
    console.log(`Applied ${result.files.length} install step(s).`);
  },
};
