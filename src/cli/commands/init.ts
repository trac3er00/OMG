import type { CommandModule } from "yargs";
import { createInterface } from "node:readline/promises";
import { basename } from "node:path";
import process from "node:process";

type InitTierHint = "auto" | "intermediate" | "expert";
type SkillLevel = "beginner" | "intermediate" | "expert";
type FlowMode = "guided" | "fast";

interface CollectedConfig {
  projectName: string;
  preset: string;
  mode?: string;
  features?: Record<string, boolean>;
  skillLevel: SkillLevel;
  flowMode: FlowMode;
}

type RL = ReturnType<typeof createInterface>;

interface InitCommandDeps {
  readonly input: NodeJS.ReadableStream;
  readonly output: NodeJS.WritableStream;
  readonly env: NodeJS.ProcessEnv;
  readonly cwd: () => string;
  readonly createReadline: typeof createInterface;
  readonly log: (message?: string) => void;
  readonly error: (message?: string) => void;
  readonly runInitWizard: (opts: {
    autoConfirm: boolean;
    json: boolean;
  }) => Promise<void>;
}

const DEFAULT_DEPS: InitCommandDeps = {
  input: process.stdin,
  output: process.stdout,
  env: process.env,
  cwd: () => process.cwd(),
  createReadline: createInterface,
  log: (message = "") => console.log(message),
  error: (message = "") => console.error(message),
  runInitWizard: async (opts) => {
    const { initWizard } = await import("../../install/orchestrator.js");
    await initWizard(opts);
  },
};

function describeError(error: unknown): string {
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message.trim();
  }

  return "Unknown setup failure";
}

async function ask(rl: RL, question: string, fallback = ""): Promise<string> {
  const raw = await rl.question(question);
  return raw.trim() || fallback;
}

async function choose(
  rl: RL,
  label: string,
  choices: readonly string[],
  defaultChoice: string,
): Promise<string> {
  const tags = choices
    .map((choice) => (choice === defaultChoice ? `[${choice}]` : choice))
    .join(" / ");
  const raw = await ask(rl, `${label} (${tags}): `, defaultChoice);
  return (
    choices.find((choice) =>
      choice.toLowerCase().startsWith(raw.toLowerCase()),
    ) ?? defaultChoice
  );
}

async function toggle(
  rl: RL,
  label: string,
  defaultYes = true,
): Promise<boolean> {
  const hint = defaultYes ? "Y/n" : "y/N";
  const raw = await ask(rl, `${label} [${hint}]: `);
  if (!raw) return defaultYes;
  return /^y(es)?$/i.test(raw);
}

function determineTierHint(argv: Record<string, unknown>): InitTierHint {
  if (argv.advanced || argv.fast) return "expert";
  if (argv.configure) return "intermediate";
  return "auto";
}

function printStep(
  deps: InitCommandDeps,
  current: number,
  total: number,
  title: string,
  description: string,
  compact = false,
): void {
  if (compact) {
    deps.log(`\n[${current}/${total}] ${title}`);
    return;
  }

  deps.log(`\nStep ${current} of ${total}: ${title}`);
  deps.log(description);
}

function confirmChoice(deps: InitCommandDeps, message: string): void {
  deps.log(`✓ ${message}`);
}

function buildIntermediateFeatures(
  preset: string,
  browser = false,
): Record<string, boolean> {
  const safeDefault = preset !== "minimal";
  return {
    "mutation-gate": true,
    firewall: true,
    "secret-guard": true,
    "cost-ledger": true,
    "proof-gate": safeDefault,
    "tdd-gate": false,
    "trust-review": safeDefault,
    "auto-compact": safeDefault,
    hud: safeDefault,
    browser,
    "team-dispatch": preset === "full" || preset === "experimental",
  };
}

async function collectSkillLevel(
  rl: RL,
  deps: InitCommandDeps,
  tierHint: InitTierHint,
): Promise<SkillLevel> {
  const defaultChoice =
    tierHint === "expert"
      ? "expert"
      : tierHint === "intermediate"
        ? "intermediate"
        : "beginner";

  deps.log("\nStep 1: Pick your setup pace");
  deps.log(
    "Choose how much guidance you want. Press Enter for the beginner-friendly default.",
  );

  const skillLevel = (await choose(
    rl,
    "Guidance level",
    ["beginner", "intermediate", "expert"],
    defaultChoice,
  )) as SkillLevel;

  confirmChoice(deps, `Guidance level: ${skillLevel}`);
  return skillLevel;
}

async function collectBeginnerFlow(
  rl: RL,
  deps: InitCommandDeps,
): Promise<CollectedConfig> {
  const cwd = basename(deps.cwd());

  printStep(
    deps,
    2,
    4,
    "Name your project",
    "We'll keep the current folder name unless you want something else.",
  );
  const projectName = await ask(rl, `Project name (${cwd}): `, cwd);
  confirmChoice(deps, `Project name: ${projectName}`);

  printStep(
    deps,
    3,
    4,
    "Choose a setup style",
    "Recommended is the safest default. Minimal keeps it tiny. Full adds more optional capabilities.",
  );
  deps.log("  minimal    - smallest install surface");
  deps.log("  standard   - recommended for most teams");
  deps.log("  full       - adds more optional tooling");
  const preset = await choose(
    rl,
    "Preset",
    ["minimal", "standard", "full"],
    "standard",
  );
  confirmChoice(deps, `Preset: ${preset}`);

  printStep(
    deps,
    4,
    4,
    "Review before setup",
    "You're in guided mode, so we'll confirm before OMG makes any changes.",
  );
  deps.log(`  Project: ${projectName}`);
  deps.log(`  Preset: ${preset}`);
  const confirmed = await toggle(rl, "Start setup with these choices?", true);
  if (!confirmed) {
    throw new Error("Setup cancelled before changes were applied");
  }
  confirmChoice(deps, "Setup confirmed");

  return {
    projectName,
    preset,
    mode: "omg-only",
    features: buildIntermediateFeatures(preset),
    skillLevel: "beginner",
    flowMode: "guided",
  };
}

async function collectIntermediateFlow(
  rl: RL,
  deps: InitCommandDeps,
): Promise<CollectedConfig> {
  const cwd = basename(deps.cwd());

  printStep(
    deps,
    2,
    5,
    "Project name",
    "Set the workspace name OMG should use for this install.",
  );
  const projectName = await ask(rl, `Project name (${cwd}): `, cwd);
  confirmChoice(deps, `Project name: ${projectName}`);

  printStep(
    deps,
    3,
    5,
    "Preset",
    "Pick the install footprint. Standard is the balanced default.",
  );
  const preset = await choose(
    rl,
    "Preset",
    ["minimal", "standard", "full", "experimental"],
    "standard",
  );
  confirmChoice(deps, `Preset: ${preset}`);

  printStep(
    deps,
    4,
    5,
    "Mode",
    "OMG-only is the recommended native path. Coexist preserves other tooling where possible.",
  );
  const mode = await choose(rl, "Mode", ["omg-only", "coexist"], "omg-only");
  confirmChoice(deps, `Mode: ${mode}`);

  printStep(
    deps,
    5,
    5,
    "Review",
    "We'll keep the recommended protection defaults and confirm before applying the plan.",
  );
  deps.log(`  Project: ${projectName}`);
  deps.log(`  Preset: ${preset}`);
  deps.log(`  Mode: ${mode}`);
  const confirmed = await toggle(rl, "Continue with this setup?", true);
  if (!confirmed) {
    throw new Error("Setup cancelled before changes were applied");
  }
  confirmChoice(deps, "Setup confirmed");

  return {
    projectName,
    preset,
    mode,
    features: buildIntermediateFeatures(preset, preset === "experimental"),
    skillLevel: "intermediate",
    flowMode: "guided",
  };
}

async function collectExpertFlow(
  rl: RL,
  deps: InitCommandDeps,
  fast: boolean,
): Promise<CollectedConfig> {
  const cwd = basename(deps.cwd());

  if (fast) {
    printStep(deps, 1, 3, "Project", "", true);
    const projectName = await ask(rl, `Project name (${cwd}): `, cwd);
    confirmChoice(deps, `Project name: ${projectName}`);

    printStep(deps, 2, 3, "Preset", "", true);
    const preset = await choose(
      rl,
      "Preset",
      ["minimal", "standard", "full", "experimental", "production"],
      "standard",
    );
    confirmChoice(deps, `Preset: ${preset}`);

    printStep(deps, 3, 3, "Apply", "", true);
    const confirmed = await toggle(rl, "Apply with omg-only mode?", true);
    if (!confirmed) {
      throw new Error("Fast setup cancelled before changes were applied");
    }
    confirmChoice(deps, "Fast setup confirmed");

    return {
      projectName,
      preset,
      mode: "omg-only",
      features: buildIntermediateFeatures(preset, preset === "experimental"),
      skillLevel: "expert",
      flowMode: "fast",
    };
  }

  printStep(deps, 2, 5, "Project name", "Set the target workspace name.");
  const projectName = await ask(rl, `Project name (${cwd}): `, cwd);
  confirmChoice(deps, `Project name: ${projectName}`);

  printStep(deps, 3, 5, "Preset", "Select the install profile.");
  const preset = await choose(
    rl,
    "Preset",
    ["minimal", "standard", "full", "experimental", "production"],
    "standard",
  );
  confirmChoice(deps, `Preset: ${preset}`);

  printStep(deps, 4, 5, "Mode", "Choose native or coexist mode.");
  const mode = await choose(rl, "Mode", ["omg-only", "coexist"], "omg-only");
  confirmChoice(deps, `Mode: ${mode}`);

  printStep(
    deps,
    5,
    5,
    "Review",
    "Defaults stay concise: mutation, security, proof, and HUD protections remain on unless the preset narrows them.",
  );
  deps.log(`  Project: ${projectName}`);
  deps.log(`  Preset: ${preset}`);
  deps.log(`  Mode: ${mode}`);
  const confirmed = await toggle(rl, "Apply this setup?", true);
  if (!confirmed) {
    throw new Error("Setup cancelled before changes were applied");
  }
  confirmChoice(deps, "Setup confirmed");

  return {
    projectName,
    preset,
    mode,
    features: buildIntermediateFeatures(preset, preset === "experimental"),
    skillLevel: "expert",
    flowMode: "guided",
  };
}

async function collectConfig(
  rl: RL,
  deps: InitCommandDeps,
  argv: Record<string, unknown>,
): Promise<CollectedConfig> {
  const tierHint = determineTierHint(argv);

  if (argv.fast) {
    deps.log("\n🚀 OMG Fast Init\n");
    return collectExpertFlow(rl, deps, true);
  }

  deps.log("\n🚀 OMG Universal Onboarding\n");
  const skillLevel = await collectSkillLevel(rl, deps, tierHint);

  switch (skillLevel) {
    case "expert":
      return collectExpertFlow(rl, deps, false);
    case "intermediate":
      return collectIntermediateFlow(rl, deps);
    default:
      return collectBeginnerFlow(rl, deps);
  }
}

function storeConfig(deps: InitCommandDeps, config: CollectedConfig): void {
  deps.env.OMG_INIT_PROJECT_NAME = config.projectName;
  deps.env.OMG_INIT_PRESET = config.preset;
  deps.env.OMG_INIT_SKILL_LEVEL = config.skillLevel;
  deps.env.OMG_INIT_FLOW_MODE = config.flowMode;

  if (config.mode) {
    deps.env.OMG_INIT_MODE = config.mode;
  }

  if (config.features) {
    deps.env.OMG_INIT_FEATURES = JSON.stringify(config.features);
  }
}

async function runWizardWithRetry(
  rl: RL,
  deps: InitCommandDeps,
  argv: Record<string, unknown>,
): Promise<void> {
  for (;;) {
    try {
      await deps.runInitWizard({
        autoConfirm: Boolean(argv.yes),
        json: Boolean(argv.json),
      });
      return;
    } catch (error) {
      const message = describeError(error);
      deps.error(`\nSetup hit a problem: ${message}`);
      const retry = await toggle(rl, "Retry the setup now?", true);
      if (!retry) {
        throw error;
      }

      deps.log("Retrying setup...");
    }
  }
}

export function createInitCommand(
  overrides: Partial<InitCommandDeps> = {},
): CommandModule {
  const deps: InitCommandDeps = { ...DEFAULT_DEPS, ...overrides };

  return {
    command: "init",
    describe:
      "Universal first-time setup flow for beginner, intermediate, and expert users",
    builder: (yargs) =>
      yargs
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
        })
        .option("configure", {
          type: "boolean",
          description: "Start in intermediate setup mode",
          default: false,
        })
        .option("advanced", {
          type: "boolean",
          description: "Start in expert setup mode",
          default: false,
        })
        .option("fast", {
          type: "boolean",
          description:
            "Expert fast-track: minimal prompts, minimal explanation",
          default: false,
        }),
    handler: async (argv) => {
      if (!argv.yes) {
        const rl = deps.createReadline({
          input: deps.input,
          output: deps.output,
        });

        try {
          const config = await collectConfig(
            rl,
            deps,
            argv as Record<string, unknown>,
          );
          storeConfig(deps, config);
          await runWizardWithRetry(rl, deps, argv as Record<string, unknown>);
        } finally {
          rl.close();
        }
      } else {
        await deps.runInitWizard({
          autoConfirm: true,
          json: Boolean(argv.json),
        });
      }

      if (!argv.fast && !argv.yes) {
        deps.log(
          "\nTip: use --fast for the expert path or --configure to start at the balanced flow.",
        );
      }
    },
  };
}

export const initCommand: CommandModule = createInitCommand();
