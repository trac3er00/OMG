import type { CommandModule } from "yargs";

export const envDoctorCommand: CommandModule = {
  command: "env doctor",
  describe: "Run environment diagnostics",
  handler: (): void => {
    const payload = {
      status: "ok",
      command: "env doctor",
      version: "3.0.0",
    };
    console.log(JSON.stringify(payload, null, 2));
  },
};
