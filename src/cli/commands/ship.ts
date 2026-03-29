import type { CommandModule } from "yargs";

export const shipCommand: CommandModule = {
  command: "ship",
  describe: "Run ship workflow",
  handler: (): void => {
    console.log("ship: delegated to runtime pipeline");
  },
};
