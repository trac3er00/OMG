import type { CommandModule } from "yargs";
import {
  formatGovernanceStatus,
  getUserGovernanceControl,
} from "../../governance/user-control.js";

interface GovernanceStatusArgs {
  readonly provider?: string;
  readonly projectDir?: string;
  readonly json?: boolean;
}

export const governanceStatusCommand: CommandModule<
  object,
  GovernanceStatusArgs
> = {
  command: "status",
  describe: "Show current governance gate states",
  builder: (yargs) =>
    yargs
      .option("provider", {
        type: "string",
        describe: "Provider override (e.g. claude, ollama)",
      })
      .option("projectDir", {
        type: "string",
        describe: "Project directory override",
      })
      .option("json", {
        type: "boolean",
        default: false,
        describe: "Output structured JSON",
      }) as never,
  handler: async (argv) => {
    const projectDir = argv.projectDir ?? process.cwd();
    const governance = getUserGovernanceControl(projectDir);
    const status = governance.getStatus(argv.provider);

    if (argv.json) {
      console.log(JSON.stringify(status, null, 2));
      return;
    }

    console.log(formatGovernanceStatus(status));
  },
};
