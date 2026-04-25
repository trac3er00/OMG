#!/usr/bin/env bun

import process from "node:process";
import { instantCommand } from "../cli/commands/instant.js";
import { shipCommand } from "../cli/commands/ship.js";
import { proofCommand } from "../cli/commands/proof.js";
import { blockedCommand } from "../cli/commands/blocked.js";

const TUI_VERSION = "2.7.0-alpha";

interface CommandInfo {
  readonly name: string;
  readonly description: string;
  readonly handler: ((args: readonly string[]) => Promise<void>) | null;
}

export const COMMANDS: Record<string, CommandInfo> = {
  instant: {
    name: "instant",
    description: "Build anything with one command - scaffold + code + preview",
    handler: async (args: readonly string[]): Promise<void> => {
      const prompt = args[0];
      if (!prompt) {
        console.error("Error: instant requires a <prompt> argument");
        process.exit(1);
      }
      await instantCommand.handler?.({
        prompt,
        json: args.includes("--json"),
        dryRun: args.includes("--dry-run"),
        targetDir: process.cwd(),
      } as never);
    },
  },
  ship: {
    name: "ship",
    description: "Run ship workflow - tests, evidence, contract validation",
    handler: async (_args: readonly string[]): Promise<void> => {
      await shipCommand.handler?.({
        json: _args.includes("--json"),
      } as never);
    },
  },
  proof: {
    name: "proof",
    description: "Inspect latest proof artifacts",
    handler: async (args: readonly string[]): Promise<void> => {
      await proofCommand.handler?.({
        html: args.includes("--html"),
      } as never);
    },
  },
  blocked: {
    name: "blocked",
    description: "Show latest blocked explanation",
    handler: async (): Promise<void> => {
      await blockedCommand.handler?.({} as never);
    },
  },
  help: {
    name: "help",
    description: "Show available commands",
    handler: null,
  },
};

export function showHelp(): void {
  console.log(`omg-tui v${TUI_VERSION}`);
  console.log("");
  console.log("Usage: omg-tui <command> [options]");
  console.log("");
  console.log("Commands:");
  for (const [name, info] of Object.entries(COMMANDS)) {
    console.log(`  ${name.padEnd(12)} ${info.description}`);
  }
  console.log("");
  console.log("Examples:");
  console.log('  omg-tui instant "build a landing page"');
  console.log("  omg-tui ship");
  console.log("  omg-tui proof --html");
  console.log("  omg-tui blocked");
  console.log("  omg-tui help");
}

export async function handleTuiCommand(args: readonly string[]): Promise<void> {
  const commandName = args[0]?.toLowerCase() ?? "help";
  const commandArgs = args.slice(1);

  if (
    commandName === "help" ||
    commandName === "--help" ||
    commandName === "-h"
  ) {
    showHelp();
    return;
  }

  if (commandName === "--version" || commandName === "-v") {
    console.log(`omg-tui v${TUI_VERSION}`);
    return;
  }

  const command = COMMANDS[commandName];
  if (!command) {
    console.error(`Unknown command: ${commandName}`);
    console.error("");
    showHelp();
    process.exit(1);
  }

  if (command.handler) {
    await command.handler(commandArgs);
  } else {
    showHelp();
  }
}

if (import.meta.main) {
  handleTuiCommand(process.argv.slice(2)).catch((error: unknown) => {
    console.error(
      "Error:",
      error instanceof Error ? error.message : String(error),
    );
    process.exit(1);
  });
}

export { TUI_VERSION };
