import type { CommandModule } from "yargs";

export const blockedCommand: CommandModule = {
  command: "blocked",
  describe: "Show latest blocked explanation",
  handler: (): void => {
    console.log("blocked: no blocked state found");
  },
};
