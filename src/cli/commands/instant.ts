import { spawnSync } from "node:child_process";
import process from "node:process";
import * as readline from "node:readline";
import type { CommandModule } from "yargs";
import { runLandingFlow } from "../../wow/flows/landing.js";
import { runSaasFlow } from "../../wow/flows/saas.js";
import { runBotFlow } from "../../wow/flows/bot.js";
import { runAdminFlow } from "../../wow/flows/admin.js";
import { runRefactorFlow } from "../../wow/flows/refactor.js";
import type { WowResult } from "../../wow/output.js";

// Module-level flag to show warning only once per session
let _deprecationShown = false;

function showDeprecationWarning(goal: string): void {
  if (_deprecationShown) return;
  _deprecationShown = true;
  console.error(`⚠️  DEPRECATED: 'omg instant "${goal}"' is deprecated.`);
  console.error(`   Use: omg "${goal}" instead`);
  // Log to deprecation log
  const logEntry = JSON.stringify({
    timestamp: new Date().toISOString(),
    command: "instant",
    goal,
    suggestion: `omg "${goal}"`,
  });
  import("node:fs")
    .then((fs) => {
      import("node:path").then((path) => {
        const dir = ".omg/state";
        fs.mkdirSync(dir, { recursive: true });
        fs.appendFileSync(
          path.join(dir, "deprecation-log.jsonl"),
          logEntry + "\n",
        );
      });
    })
    .catch(() => {}); // Ignore errors
}

const MAX_CLARIFICATION_ROUNDS = 3;

function askQuestion(prompt: string): Promise<string> {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  return new Promise((resolve) => {
    rl.question(`${prompt} `, (answer) => {
      rl.close();
      resolve(answer.trim());
    });
  });
}

interface InstantArgs {
  readonly prompt: string;
  readonly json?: boolean;
  readonly dryRun?: boolean;
  readonly targetDir?: string;
}

interface InstantOptions {
  readonly dryRun: boolean;
  readonly targetDir: string;
}

interface InstantPayload extends Record<string, unknown> {
  readonly success?: boolean;
  readonly type?: string;
  readonly confidence?: number;
  readonly clarification_needed?: boolean;
  readonly clarification_prompt?: string | null;
  readonly target_dir?: string;
  readonly file_count?: number;
  readonly pack_loaded?: boolean;
  readonly evidence?: Record<string, unknown>;
  readonly warning?: string;
  readonly subdirectory?: string;
  readonly skipped_files?: readonly unknown[];
  readonly dry_run?: boolean;
  readonly rollback?: boolean;
}

interface PythonResult {
  readonly status: number | null;
  readonly stdout: string;
  readonly stderr: string;
}

function normalizePrompt(rawPrompt: string): string {
  return String(rawPrompt ?? "").trim();
}

function buildModuleCommand(
  prompt: string,
  options: InstantOptions,
  includeRollback = true,
): string[] {
  const command = [
    "-m",
    "runtime.instant_mode",
    "--prompt",
    prompt,
    "--target-dir",
    options.targetDir,
    "--json",
  ];

  if (includeRollback) {
    command.push("--rollback");
  }

  if (options.dryRun) {
    command.push("--dry-run");
  }

  return command;
}

function buildFallbackCommand(
  prompt: string,
  options: InstantOptions,
): string[] {
  const script = [
    "import argparse, json, tempfile",
    "from pathlib import Path",
    "import runtime.instant_mode as instant_mode",
    "parser = argparse.ArgumentParser()",
    "parser.add_argument('--prompt', required=True)",
    "parser.add_argument('--target-dir', required=True)",
    "parser.add_argument('--json', action='store_true')",
    "parser.add_argument('--dry-run', action='store_true')",
    "parser.add_argument('--rollback', action='store_true')",
    "args = parser.parse_args()",
    "requested_target = Path(args.target_dir).expanduser().resolve()",
    "effective_target = requested_target",
    "warning = None",
    "if args.dry_run:",
    "    if requested_target.exists() and requested_target.is_dir():",
    "        entries = list(requested_target.iterdir())",
    "        if entries:",
    "            effective_target = instant_mode._next_available_subdirectory(requested_target, 'instant-dry-run')",
    "            warning = f'Target was non-empty, dry-run would use subdirectory: {effective_target}'",
    "    with tempfile.TemporaryDirectory() as tmp_dir:",
    "        payload = instant_mode.run_instant(args.prompt, tmp_dir)",
    "    payload['target_dir'] = str(effective_target)",
    "    payload['dry_run'] = True",
    "    payload['rollback'] = args.rollback",
    "    if warning is not None:",
    "        payload['warning'] = warning",
    "        payload['subdirectory'] = str(effective_target)",
    "    print(json.dumps(payload))",
    "else:",
    "    payload = instant_mode.run_instant(args.prompt, str(requested_target))",
    "    payload['dry_run'] = False",
    "    payload['rollback'] = args.rollback",
    "    print(json.dumps(payload))",
  ].join("\n");

  const command = [
    "-c",
    script,
    "--prompt",
    prompt,
    "--target-dir",
    options.targetDir,
    "--json",
    "--rollback",
  ];

  if (options.dryRun) {
    command.push("--dry-run");
  }

  return command;
}

function runPython(command: string[]): PythonResult {
  const result = spawnSync("python3", command, {
    cwd: process.cwd(),
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 300_000,
  });

  if (result.error) {
    throw result.error;
  }

  return {
    status: result.status,
    stdout: `${result.stdout ?? ""}`.trim(),
    stderr: `${result.stderr ?? ""}`.trim(),
  };
}

function parsePayload(
  result: PythonResult,
  failurePrefix: string,
): InstantPayload {
  if (result.status !== 0) {
    throw new Error(
      [
        `${failurePrefix} (exit=${result.status ?? "unknown"})`,
        result.stderr,
        result.stdout,
      ]
        .filter((segment) => segment.length > 0)
        .join("\n"),
    );
  }

  if (!result.stdout) {
    throw new Error(`${failurePrefix} returned empty output`);
  }

  try {
    return JSON.parse(result.stdout) as InstantPayload;
  } catch (error) {
    throw new Error(
      `${failurePrefix} returned invalid JSON: ${String(error)}\n${result.stdout}`,
    );
  }
}

type FlowType = "landing" | "saas" | "bot" | "admin" | "refactor";

interface FlowPattern {
  readonly flow: FlowType;
  readonly patterns: readonly RegExp[];
}

const FLOW_PATTERNS: readonly FlowPattern[] = [
  {
    flow: "landing",
    patterns: [/\blanding\s*page\b/i, /\blanding\b/i],
  },
  {
    flow: "saas",
    patterns: [/\bsaas\b/i, /\bSaaS\b/],
  },
  {
    flow: "bot",
    patterns: [/\bbot\b/i, /\bdiscord\s*bot\b/i, /\btelegram\s*bot\b/i],
  },
  {
    flow: "admin",
    patterns: [/\badmin\b/i, /\badmin\s*panel\b/i, /\badmin\s*dashboard\b/i],
  },
  {
    flow: "refactor",
    patterns: [/\brefactor\b/i],
  },
];

function detectFlowType(prompt: string): FlowType | null {
  const normalizedPrompt = prompt.toLowerCase();
  for (const { flow, patterns } of FLOW_PATTERNS) {
    for (const pattern of patterns) {
      if (pattern.test(normalizedPrompt)) {
        return flow;
      }
    }
  }
  return null;
}

function mapWowResultToPayload(
  result: WowResult,
  targetDir: string,
): InstantPayload {
  return {
    success: result.success,
    type: result.flowName,
    target_dir: targetDir,
    file_count: 0, // Wow flows don't track file count explicitly
    proofScore: result.proofScore,
    url: result.url,
    buildTime: result.buildTime,
    error: result.error,
  };
}

async function runWowFlow(
  flowType: FlowType,
  prompt: string,
  targetDir: string,
): Promise<WowResult> {
  switch (flowType) {
    case "landing":
      return runLandingFlow(prompt, targetDir);
    case "saas":
      return runSaasFlow(prompt, targetDir);
    case "bot":
      return runBotFlow(prompt, targetDir);
    case "admin":
      return runAdminFlow(prompt, targetDir);
    case "refactor":
      return runRefactorFlow(prompt, targetDir);
  }
}

/**
 * Attempts to run a TypeScript wow flow based on prompt keyword matching.
 * Returns InstantPayload if a matching flow was found and executed.
 * Returns null if no flow matched (caller should fall back to Python).
 */
export async function tryWowFlow(
  prompt: string,
  targetDir: string,
): Promise<InstantPayload | null> {
  const flowType = detectFlowType(prompt);
  if (flowType === null) {
    return null;
  }

  const result = await runWowFlow(flowType, prompt, targetDir);
  return mapWowResultToPayload(result, targetDir);
}

export function runInstant(
  prompt: string,
  options: InstantOptions,
): InstantPayload {
  const moduleResult = runPython(buildModuleCommand(prompt, options));
  if (moduleResult.status === 0 && moduleResult.stdout.length > 0) {
    return parsePayload(moduleResult, "instant mode failed");
  }

  if (moduleResult.stderr.includes("unrecognized arguments: --rollback")) {
    return parsePayload(
      runPython(buildModuleCommand(prompt, options, false)),
      "instant mode failed",
    );
  }

  if (
    moduleResult.status !== 0 ||
    moduleResult.stderr.length > 0 ||
    moduleResult.stdout.length > 0
  ) {
    return parsePayload(moduleResult, "instant mode failed");
  }

  return parsePayload(
    runPython(buildFallbackCommand(prompt, options)),
    "instant mode fallback failed",
  );
}

function requireProjectPath(payload: InstantPayload): string {
  const targetDir = String(payload.target_dir ?? "").trim();
  if (!targetDir) {
    throw new Error("instant mode did not return a project path");
  }
  return targetDir;
}

function printHuman(payload: InstantPayload): void {
  if (payload.success === false) {
    const clarificationPrompt = String(
      payload.clarification_prompt ?? "",
    ).trim();
    if (clarificationPrompt.length > 0) {
      throw new Error(clarificationPrompt);
    }
    throw new Error("instant mode failed");
  }

  const targetDir = requireProjectPath(payload);
  const fileCount = Number(payload.file_count ?? 0);
  console.log(`✓ Created ${fileCount} files in ${targetDir}`);

  const proofScore = payload.proofScore as number | undefined;
  if (proofScore !== undefined) {
    console.log(`📊 ProofScore: ${proofScore}/100`);
  }

  const url = payload.url as string | undefined;
  if (url) {
    console.log(`🌐 URL: ${url}`);
  }

  const warning = String(payload.warning ?? "").trim();
  if (warning.length > 0) {
    console.log(`Warning: ${warning}`);
  }
}

export const instantCommand: CommandModule<object, InstantArgs> = {
  command: "instant <prompt>",
  describe: "Build anything with one command - scaffold + code + preview",
  builder: (command) =>
    command
      .positional("prompt", {
        type: "string",
        demandOption: true,
        describe: "Goal string to build",
      })
      .option("json", {
        type: "boolean",
        default: false,
        describe: "Output instant mode payload as JSON",
      })
      .option("dry-run", {
        type: "boolean",
        default: false,
        describe: "Preview scaffold output without writing files",
      })
      .option("target-dir", {
        type: "string",
        default: process.cwd(),
        describe: "Target directory for the generated project",
        alias: "output-dir",
      }),
  handler: async (argv): Promise<void> => {
    let prompt = normalizePrompt(argv.prompt);
    showDeprecationWarning(prompt);
    if (!prompt) {
      throw new Error("prompt is required");
    }

    const options = {
      dryRun: Boolean(argv.dryRun),
      targetDir: String(argv.targetDir ?? process.cwd()),
    };

    const wowPayload = await tryWowFlow(prompt, options.targetDir);
    if (wowPayload !== null) {
      if (argv.json) {
        requireProjectPath(wowPayload);
        console.log(JSON.stringify(wowPayload, null, 2));
        return;
      }
      printHuman(wowPayload);
      return;
    }

    let payload = runInstant(prompt, options);
    let clarificationRound = 0;

    while (
      payload.clarification_needed &&
      payload.clarification_prompt &&
      clarificationRound < MAX_CLARIFICATION_ROUNDS
    ) {
      if (argv.json) {
        console.log(
          JSON.stringify(
            {
              success: false,
              error: "clarification_required",
              clarification_prompt: payload.clarification_prompt,
              message:
                "Clarification needed but JSON mode does not support interactive questions",
            },
            null,
            2,
          ),
        );
        process.exit(1);
      }

      clarificationRound++;

      const clarificationPrompt = String(payload.clarification_prompt).trim();
      const answer = await askQuestion(clarificationPrompt);

      if (!answer) {
        throw new Error("No clarification provided - aborting");
      }

      prompt = `${prompt}\n\nClarification: ${answer}`;
      payload = runInstant(prompt, options);
    }

    if (payload.clarification_needed && payload.clarification_prompt) {
      if (argv.json) {
        console.log(
          JSON.stringify(
            {
              success: false,
              error: "max_clarification_rounds_exceeded",
              message: `Failed to resolve clarification after ${MAX_CLARIFICATION_ROUNDS} rounds`,
              last_clarification_prompt: payload.clarification_prompt,
            },
            null,
            2,
          ),
        );
        process.exit(1);
      }
      throw new Error(
        `Failed to resolve clarification after ${MAX_CLARIFICATION_ROUNDS} rounds. Last question: ${payload.clarification_prompt}`,
      );
    }

    if (argv.json) {
      requireProjectPath(payload);
      console.log(JSON.stringify(payload, null, 2));
      return;
    }

    printHuman(payload);
  },
};
