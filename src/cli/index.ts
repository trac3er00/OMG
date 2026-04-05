#!/usr/bin/env bun

import { basename } from "node:path";
import process from "node:process";
import yargs from "yargs";
import { hideBin } from "yargs/helpers";
import { formatCliError, printCliError } from "./error-formatter.js";

const CLI_VERSION = "2.3.0";

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
    .command({
      command: "env doctor",
      describe: "Run environment diagnostics",
      builder: (command) =>
        command.option("json", {
          type: "boolean",
          description: "Output diagnostics as JSON",
          default: false,
        }),
      handler: async (argv) => {
        const { envDoctorCommand } = await import("./commands/env.js");
        await envDoctorCommand.handler?.(argv as never);
      },
    })
    .command({
      command: "init",
      describe:
        "Interactive first-time setup wizard (doctor → plan → confirm → apply)",
      builder: (command) =>
        command
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
        const { initCommand } = await import("./commands/init.js");
        await initCommand.handler?.(argv as never);
      },
    })
    .command({
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
      handler: async (argv) => {
        const { installCommand } = await import("./commands/install.js");
        await installCommand.handler?.(argv as never);
      },
    })
    .command({
      command: "ship",
      describe: "Run ship workflow",
      builder: (command) =>
        command.option("json", {
          type: "boolean",
          description: "Output ship readiness as JSON",
          default: false,
        }),
      handler: async (argv) => {
        const { shipCommand } = await import("./commands/ship.js");
        await shipCommand.handler?.(argv as never);
      },
    })
    .command({
      command: "proof",
      describe: "Inspect latest proof artifacts",
      builder: (command) =>
        command
          .option("html", {
            type: "boolean",
            description: "Open latest proof artifact in browser",
            default: false,
          })
          .command(
            "open",
            "Open/list proof artifacts",
            (openCommand) =>
              openCommand.option("html", {
                type: "boolean",
                description: "Open latest proof artifact in browser",
                default: false,
              }),
            async (openArgv) => {
              const { proofCommand } = await import("./commands/proof.js");
              await proofCommand.handler?.(openArgv as never);
            },
          ),
      handler: async (argv) => {
        const { proofCommand } = await import("./commands/proof.js");
        await proofCommand.handler?.(argv as never);
      },
    })
    .command({
      command: "blocked",
      describe: "Show latest blocked explanation",
      handler: async (argv) => {
        const { blockedCommand } = await import("./commands/blocked.js");
        await blockedCommand.handler?.(argv as never);
      },
    })
    .command({
      command: "validate",
      describe: "Run validation checks",
      builder: (command) =>
        command.option("json", {
          type: "boolean",
          description: "Output validation report as JSON",
          default: false,
        }),
      handler: async (argv) => {
        const { validateCommand } = await import("./commands/validate.js");
        await validateCommand.handler?.(argv as never);
      },
    })
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
      const formatted = formatCliError(error);
      printCliError(error);
      process.exit(formatted.exitCode);
    });
}

export { CLI_VERSION };
