#!/usr/bin/env bun

import { basename } from "node:path";
import process from "node:process";
import yargs from "yargs";
import { hideBin } from "yargs/helpers";
import { blockedCommand } from "./commands/blocked.js";
import { envDoctorCommand } from "./commands/env.js";
import { installCommand } from "./commands/install.js";
import { proofCommand } from "./commands/proof.js";
import { shipCommand } from "./commands/ship.js";
import { validateCommand } from "./commands/validate.js";

const CLI_VERSION = "3.0.0";

async function maybeStartControlServer(): Promise<boolean> {
  const executable = basename(process.argv[1] ?? "");
  if (executable !== "omg-control") {
    return false;
  }

  const { startServer } = await import("../mcp/server.js");
  await startServer();
  return true;
}

async function runCli(): Promise<void> {
  await yargs(hideBin(process.argv))
    .scriptName("omg")
    .strict()
    .help()
    .version("version", CLI_VERSION, CLI_VERSION)
    .alias("v", "version")
    .command(envDoctorCommand)
    .command(installCommand)
    .command(shipCommand)
    .command(proofCommand)
    .command(blockedCommand)
    .command(validateCommand)
    .demandCommand(1, "Specify a command")
    .parseAsync();
}

if (import.meta.main) {
  maybeStartControlServer()
    .then(async (startedControlServer) => {
      if (!startedControlServer) {
        await runCli();
      }
    })
    .catch((error: unknown) => {
      console.error(error);
      process.exit(1);
    });
}

export { CLI_VERSION };
