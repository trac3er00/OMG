import type { CommandModule } from "yargs";

export const proofCommand: CommandModule = {
  command: "proof",
  describe: "Inspect latest proof artifacts",
  handler: (): void => {
    console.log("proof: delegated to proof workflows");
  },
};
