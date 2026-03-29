import type { CommandModule } from "yargs";

export const validateCommand: CommandModule = {
  command: "validate",
  describe: "Run validation checks",
  handler: (): void => {
    console.log("validate: delegated to validation pipeline");
  },
};
