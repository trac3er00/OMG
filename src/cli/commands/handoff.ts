import { execSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { CommandModule } from "yargs";

export interface HandoffOptions {
  readonly save?: boolean;
  readonly format?: "md" | "json";
  readonly verbosity?: "brief" | "standard" | "detailed";
}

interface HandoffArgs {
  readonly save: boolean;
  readonly format: string;
  readonly verbosity: string;
}

function buildPythonCommand(projectDir: string, verbosity: string): string {
  const escaped = projectDir.replace(/'/g, "\\'");
  return [
    "python3",
    "-c",
    `'import sys; sys.path.insert(0, "${escaped}"); ` +
      `from runtime.context_compactor import compact_context; ` +
      `ctx = compact_context(project_dir="${escaped}", verbosity="${verbosity}"); ` +
      `print(ctx.to_markdown(verbosity="${verbosity}"))'`,
  ].join(" ");
}

function runCompactor(projectDir: string, verbosity: string): string {
  const cmd = buildPythonCommand(projectDir, verbosity);
  try {
    return execSync(cmd, {
      encoding: "utf8",
      cwd: projectDir,
      timeout: 30_000,
    }).trimEnd();
  } catch {
    return "# Session Handoff\n\n(Context compaction unavailable — Python runtime not found)";
  }
}

export function runHandoff(options: HandoffOptions = {}): void {
  const { save = false, format = "md", verbosity = "standard" } = options;

  const projectDir = process.cwd();
  let output = runCompactor(projectDir, verbosity);

  if (format === "json") {
    const envelope = {
      handoff: output,
      timestamp: new Date().toISOString(),
      projectDir,
      verbosity,
    };
    output = JSON.stringify(envelope, null, 2);
  }

  if (save) {
    const timestamp = new Date()
      .toISOString()
      .replace(/[:.]/g, "-")
      .slice(0, 19);
    const handoffDir = join(projectDir, ".sisyphus", "handoffs");
    mkdirSync(handoffDir, { recursive: true });
    const ext = format === "json" ? "json" : "md";
    const filename = join(handoffDir, `handoff-${timestamp}.${ext}`);
    writeFileSync(filename, output + "\n", "utf8");
    console.log(`Handoff saved to: ${filename}`);
  } else {
    console.log(output);
  }
}

export const handoffCommand: CommandModule<object, HandoffArgs> = {
  command: "handoff",
  describe: "Produce structured session handoff document",
  builder: (yargs) =>
    yargs
      .option("save", {
        type: "boolean",
        description: "Save output to .sisyphus/handoffs/ instead of stdout",
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
  handler: (argv): void => {
    runHandoff({
      save: argv.save,
      format: argv.format as "md" | "json",
      verbosity: argv.verbosity as "brief" | "standard" | "detailed",
    });
  },
};
