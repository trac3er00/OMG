#!/usr/bin/env bun

import { basename } from "node:path";
import process from "node:process";
import yargs from "yargs";
import { hideBin } from "yargs/helpers";
import { formatCliError, printCliError } from "./error-formatter.js";
import { hooksListCommand } from "./commands/hooks.js";
import { memoryCommand } from "./commands/memory.js";
import { pauseCommand } from "./commands/pause.js";
import { skillsListCommand } from "./commands/skills.js";

const CLI_VERSION = "2.3.0";

type CommandItem = {
  readonly name: string;
  readonly description: string;
};

type CommandGroup = {
  readonly title: string;
  readonly items: readonly CommandItem[];
};

const COMMAND_GROUPS: readonly CommandGroup[] = [
  {
    title: "Setup",
    items: [
      { name: "env doctor", description: "Run environment diagnostics" },
      { name: "doctor", description: "Diagnose installation issues" },
      { name: "health-check", description: "Verify setup and tool health" },
      { name: "init", description: "Interactive first-time setup" },
      { name: "project-init", description: "Deprecated alias for /OMG:init" },
      { name: "setup", description: "Native OMG setup and adoption flow" },
      { name: "diagnose-plugins", description: "Diagnose plugin conflicts" },
    ],
  },
  {
    title: "Work",
    items: [
      {
        name: "instant",
        description:
          "Build anything with one command - scaffold + code + preview",
      },
      { name: "crazy", description: "Maximum multi-agent orchestration" },
      { name: "deep-plan", description: "Canonical strategic planning" },
      { name: "browser", description: "Browser automation and verification" },
      { name: "playwright", description: "Compatibility alias for browser" },
      { name: "forge", description: "Labs-only domain prototyping" },
      { name: "domains", description: "Domain pack discovery and scaffolding" },
      {
        name: "ai-commit",
        description: "Split uncommitted changes into atomic commits",
      },
      { name: "issue", description: "Active red-team issue triage" },
      {
        name: "arch",
        description: "Dependency graphs and architecture diagrams",
      },
      { name: "ccg", description: "Tri-track synthesis orchestration" },
      {
        name: "deps",
        description: "Dependency CVE, license, and update scans",
      },
    ],
  },
  {
    title: "Verify",
    items: [
      { name: "ship", description: "Idea-to-evidence-to-PR flow" },
      { name: "validate", description: "Canonical validation checks" },
      { name: "security-check", description: "Canonical security pipeline" },
      {
        name: "preflight",
        description: "Route selection and evidence planning",
      },
      {
        name: "api-twin",
        description: "Contract replay and live verification",
      },
      { name: "red-team", description: "Adversarial security review" },
      { name: "next", description: "Planned next-step surface" },
    ],
  },
  {
    title: "Configure",
    items: [
      { name: "preset", description: "Inspect or apply the canonical preset" },
      { name: "mode", description: "Set the current session mode" },
      { name: "theme", description: "Interactive theme selection" },
      { name: "lsp", description: "Show detected LSP server status" },
      { name: "profile-review", description: "Review governed profile state" },
      { name: "teams", description: "Internal staged team routing" },
      { name: "cost", description: "Session cost tracking and budgets" },
      { name: "stats", description: "Session analytics and usage trends" },
    ],
  },
  {
    title: "Inspect",
    items: [
      { name: "hooks list", description: "List registered hook scripts" },
      { name: "memory show", description: "Show structured memory schemas" },
      { name: "skills list", description: "List installed OMG skills" },
    ],
  },
  {
    title: "Advanced",
    items: [
      {
        name: "session-branch",
        description: "Create or manage state branches",
      },
      { name: "session-fork", description: "Fork state from a snapshot" },
      {
        name: "session-merge",
        description: "Merge state branches with conflicts",
      },
      { name: "ralph-start", description: "Start the Ralph autonomous loop" },
      { name: "ralph-stop", description: "Stop the Ralph autonomous loop" },
      { name: "create-agent", description: "Wizard for custom agent creation" },
      { name: "compat", description: "Run legacy skill names via dispatcher" },
      { name: "domain-init", description: "Alias for /OMG:init [domain-name]" },
      { name: "escalate", description: "Auto-route to Codex, Gemini, or CCG" },
      { name: "handoff", description: "Structured session handoff document" },
    ],
  },
] as const;

function printCommands(): void {
  console.log("OMG Commands");
  console.log("");

  for (const group of COMMAND_GROUPS) {
    console.log(`${group.title}:`);
    for (const item of group.items) {
      console.log(`  ${item.name.padEnd(14)} - ${item.description}`);
    }
    console.log("");
  }
}

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
      command: "commands",
      describe: "Print categorized OMG command index",
      handler: async () => {
        printCommands();
      },
    })
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
    .command(
      "instant <prompt>",
      "Build anything with one command - scaffold + code + preview",
      (yargs) => {
        yargs.positional("prompt", {
          describe: "What to build",
          type: "string",
        });
      },
      async (argv) => {
        console.log("Running instant mode:", argv.prompt);
      },
    )
    .command({
      command: "autorun <goal...>",
      describe:
        "Run governed pipeline (plan → review → execute → verify) for a goal",
      builder: (command) =>
        command
          .positional("goal", {
            type: "string",
            array: true,
            demandOption: true,
            describe: "Goal text to execute in autorun pipeline",
          })
          .option("tier", {
            type: "string",
            default: "max",
            describe: "Planning tier hint",
          })
          .option("single-agent", {
            type: "boolean",
            default: false,
            describe: "Force single-agent execution mode",
          })
          .option("json", {
            type: "boolean",
            default: false,
            describe: "Output full pipeline payload as JSON",
          }),
      handler: async (argv) => {
        const { autorunCommand } = await import("./commands/autorun.js");
        await autorunCommand.handler?.(argv as never);
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
      command: "hooks",
      describe: "Inspect registered hook scripts",
      builder: (command) =>
        command
          .command(hooksListCommand)
          .demandCommand(1, "Specify a hooks subcommand: list"),
      handler: () => {},
    })
    .command({
      command: "skills",
      describe: "Inspect installed OMG skills",
      builder: (command) =>
        command
          .command(skillsListCommand)
          .demandCommand(1, "Specify a skills subcommand: list"),
      handler: () => {},
    })
    .command(memoryCommand)
    .command(pauseCommand)
    .command({
      command: "lsp",
      describe: "Show LSP server status",
      handler: async () => {
        const { runLspStatus } = await import("./commands/lsp-status.js");
        await runLspStatus();
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
    .command({
      command: "audit",
      describe: "Audit log management",
      builder: (command) =>
        command
          .command({
            command: "export",
            describe:
              "Export audit logs in SIEM-compatible format (enterprise only)",
            builder: (sub) =>
              sub
                .option("format", {
                  type: "string",
                  choices: ["jsonl"] as const,
                  default: "jsonl",
                  describe: "Export format",
                })
                .option("output", {
                  type: "string",
                  demandOption: true,
                  describe: "Output file path, or '-' for stdout",
                })
                .option("projectDir", {
                  type: "string",
                  describe: "Project directory override",
                }),
            handler: async (argv) => {
              const { auditExportCommand } =
                await import("./commands/audit.js");
              await auditExportCommand.handler?.(argv as never);
            },
          })
          .demandCommand(1, "Specify an audit subcommand"),
      handler: () => {},
    })
    .command({
      command: "evidence",
      describe: "Evidence retention and querying",
      builder: (command) =>
        command
          .command({
            command: "prune",
            describe:
              "Archive and remove evidence older than a given threshold",
            builder: (sub) =>
              sub
                .option("older-than", {
                  type: "string",
                  demandOption: true,
                  describe: 'Duration threshold, e.g. "30d", "24h", "60m"',
                })
                .option("projectDir", {
                  type: "string",
                  describe: "Project directory override",
                })
                .option("json", {
                  type: "boolean",
                  default: false,
                  describe: "Output as JSON",
                }),
            handler: async (argv) => {
              const { evidencePruneCommand } =
                await import("./commands/evidence.js");
              await evidencePruneCommand.handler(argv as never);
            },
          })
          .command({
            command: "query",
            describe: "Query evidence records by type and age",
            builder: (sub) =>
              sub
                .option("since", {
                  type: "string",
                  describe: 'Filter evidence newer than duration, e.g. "7d"',
                })
                .option("type", {
                  type: "string",
                  describe: "Filter by evidence type",
                })
                .option("projectDir", {
                  type: "string",
                  describe: "Project directory override",
                })
                .option("json", {
                  type: "boolean",
                  default: true,
                  describe: "Output as JSON (default)",
                }),
            handler: async (argv) => {
              const { evidenceQueryCommand } =
                await import("./commands/evidence.js");
              await evidenceQueryCommand.handler(argv as never);
            },
          })
          .demandCommand(1, "Specify an evidence subcommand: prune or query"),
      handler: () => {},
    })
    .command({
      command: "contract",
      describe: "Contract compilation and validation",
      builder: (command) =>
        command
          .command(
            "validate",
            "Validate the canonical contract schema",
            (sub) =>
              sub.option("json", {
                type: "boolean",
                description: "Output as JSON",
                default: false,
              }),
            async (subArgv) => {
              const { contractValidateCommand } =
                await import("./commands/contract.js");
              await contractValidateCommand.handler?.(subArgv as never);
            },
          )
          .command(
            "compile",
            "Compile contract artifacts for target hosts",
            (sub) =>
              sub
                .option("host", {
                  type: "string",
                  array: true,
                  describe: "Target host(s): claude, codex, gemini, kimi",
                })
                .option("channel", {
                  type: "string",
                  describe: "Release channel",
                  default: "public",
                })
                .option("json", {
                  type: "boolean",
                  description: "Output as JSON",
                  default: false,
                }),
            async (subArgv) => {
              const { contractCompileCommand } =
                await import("./commands/contract.js");
              await contractCompileCommand.handler?.(subArgv as never);
            },
          )
          .demandCommand(
            1,
            "Specify a contract subcommand: validate or compile",
          ),
      handler: () => {},
    })
    .command({
      command: "migrate",
      describe: "Migrate OMG project config between versions",
      builder: (command) =>
        command
          .option("from", {
            type: "string",
            demandOption: true,
            describe: "Source OMG version",
          })
          .option("to", {
            type: "string",
            demandOption: true,
            describe: "Target OMG version",
          })
          .option("dry-run", {
            type: "boolean",
            default: true,
            describe: "Preview migration without writing files",
          })
          .option("apply", {
            type: "boolean",
            default: false,
            describe: "Apply migration and create rollback backups",
          }),
      handler: async (argv) => {
        const { migrateCommand } = await import("./commands/migrate.js");
        await migrateCommand.handler?.(argv as never);
      },
    })
    .command({
      command: "handoff",
      describe: "Produce structured session handoff document",
      builder: (command) =>
        command
          .option("save", {
            type: "boolean",
            description: "Save output to .sisyphus/handoffs/",
            default: false,
          })
          .option("format", {
            type: "string",
            choices: ["md", "json"] as const,
            description: "Output format",
            default: "md",
          })
          .option("verbosity", {
            type: "string",
            choices: ["brief", "standard", "detailed"] as const,
            description:
              "Items per section: brief (3), standard (10), detailed (50)",
            default: "standard",
          }),
      handler: async (argv) => {
        const { handoffCommand } = await import("./commands/handoff.js");
        await handoffCommand.handler?.(argv as never);
      },
    })
    .command({
      command: "next",
      describe: "Analyze project health and surface next improvements",
      builder: (command) =>
        command
          .option("focus", {
            type: "string",
            description: "Narrow analysis to a specific dimension",
          })
          .option("quick", {
            type: "boolean",
            description: "Skip deep analysis for faster results",
            default: false,
          })
          .option("output", {
            type: "string",
            description: "Write full JSON report to this path",
          }),
      handler: async (argv) => {
        const { nextCommand } = await import("./commands/next.js");
        await nextCommand.handler?.(argv as never);
      },
    })
    .command({
      command: "red-team [scope]",
      describe: "Run adversarial security review",
      builder: (command) =>
        command
          .positional("scope", {
            type: "string",
            description: "File or directory to scan",
            default: ".",
          })
          .option("severity-floor", {
            type: "string",
            choices: ["low", "medium", "high", "critical"] as const,
            description: "Minimum severity level for findings",
            default: "medium",
          })
          .option("output", {
            type: "string",
            description: "Write full JSON report to this path",
          }),
      handler: async (argv) => {
        const { redTeamCommand } = await import("./commands/red-team.js");
        await redTeamCommand.handler?.(argv as never);
      },
    })
    .command({
      command: "domains [subcommand] [pack]",
      describe: "Domain pack discovery and scaffolding",
      builder: (command) =>
        command
          .positional("subcommand", {
            type: "string",
            description: "Subcommand: list or init",
            default: "list",
          })
          .positional("pack", {
            type: "string",
            description: "Pack name (for init)",
          })
          .option("target", {
            type: "string",
            description: "Target directory for scaffold output",
          }),
      handler: async (argv) => {
        const { runDomains } = await import("./commands/domains.js");
        runDomains(
          argv.subcommand as string | undefined,
          argv.pack as string | undefined,
          argv.target as string | undefined,
        );
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
