import type { CommandModule } from "yargs";
import { createInterface } from "node:readline/promises";
import { basename } from "node:path";
import process from "node:process";

type InitTier = "default" | "configure" | "advanced";

interface CollectedConfig {
  projectName: string;
  preset: string;
  mode?: string;
  features?: Record<string, boolean>;
}

type RL = ReturnType<typeof createInterface>;

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
    .map((c) => (c === defaultChoice ? `[${c}]` : c))
    .join(" / ");
  const raw = await ask(rl, `${label} (${tags}): `, defaultChoice);
  return (
    choices.find((c) => c.toLowerCase().startsWith(raw.toLowerCase())) ??
    defaultChoice
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

function determineTier(argv: Record<string, unknown>): InitTier {
  if (argv.advanced) return "advanced";
  if (argv.configure) return "configure";
  return "default";
}

async function collectTier1(rl: RL): Promise<CollectedConfig> {
  console.log("\n\x1b[1m🚀 OMG Quick Setup\x1b[0m\n");

  const cwd = basename(process.cwd());
  const projectName = await ask(rl, `Project name (${cwd}): `, cwd);
  const preset = await choose(
    rl,
    "Preset",
    ["minimal", "standard", "full"],
    "standard",
  );

  console.log(
    `\n✅ Using preset \x1b[1m${preset}\x1b[0m for \x1b[1m${projectName}\x1b[0m\n`,
  );

  return { projectName, preset };
}

async function collectTier2(rl: RL): Promise<CollectedConfig> {
  console.log("\n\x1b[1m⚙️  OMG Configuration\x1b[0m\n");

  const cwd = basename(process.cwd());
  const projectName = await ask(rl, `Project name (${cwd}): `, cwd);
  const preset = await choose(
    rl,
    "Preset",
    ["minimal", "standard", "full", "experimental"],
    "standard",
  );
  const mode = await choose(rl, "Mode", ["omg-only", "coexist"], "omg-only");

  console.log("\n\x1b[2mFeature flags (Enter for preset defaults):\x1b[0m");
  const securityGates = await toggle(
    rl,
    "  Security gates (firewall + secret-guard)?",
    true,
  );
  const proofGate = await toggle(
    rl,
    "  Proof gate (evidence-backed verification)?",
    preset !== "minimal",
  );
  const hud = await toggle(rl, "  HUD status line?", preset !== "minimal");
  const autoCompact = await toggle(rl, "  Auto-compact?", preset !== "minimal");
  const browser = await toggle(
    rl,
    "  Browser automation?",
    preset === "experimental",
  );

  const features: Record<string, boolean> = {
    "mutation-gate": true,
    firewall: securityGates,
    "secret-guard": securityGates,
    "cost-ledger": true,
    "proof-gate": proofGate,
    "tdd-gate": false,
    "trust-review": proofGate,
    "auto-compact": autoCompact,
    hud,
    browser,
    "team-dispatch": false,
  };

  console.log(
    `\n✅ Configured \x1b[1m${preset}\x1b[0m for \x1b[1m${projectName}\x1b[0m (mode: ${mode})\n`,
  );

  return { projectName, preset, mode, features };
}

async function collectTier3(rl: RL): Promise<CollectedConfig> {
  console.log("\n\x1b[1m🔧 OMG Advanced Configuration\x1b[0m\n");

  const cwd = basename(process.cwd());
  const projectName = await ask(rl, `Project name (${cwd}): `, cwd);
  const preset = await choose(
    rl,
    "Preset",
    ["minimal", "standard", "full", "experimental", "production"],
    "standard",
  );
  const mode = await choose(rl, "Mode", ["omg-only", "coexist"], "omg-only");

  console.log("\n\x1b[2mAll feature flags:\x1b[0m");
  const mutationGate = await toggle(
    rl,
    "  mutation-gate (block risky mutations)?",
    true,
  );
  const firewall = await toggle(
    rl,
    "  firewall (Bash command screening)?",
    true,
  );
  const secretGuard = await toggle(
    rl,
    "  secret-guard (secret detection in reads/edits)?",
    true,
  );
  const costLedger = await toggle(
    rl,
    "  cost-ledger (track token/cost budget)?",
    true,
  );
  const proofGate = await toggle(
    rl,
    "  proof-gate (evidence-backed verification)?",
    preset !== "minimal",
  );
  const tddGate = await toggle(
    rl,
    "  tdd-gate (require tests before implementation)?",
    ["experimental", "production"].includes(preset),
  );
  const trustReview = await toggle(
    rl,
    "  trust-review (config change safety review)?",
    preset !== "minimal",
  );
  const autoCompact = await toggle(
    rl,
    "  auto-compact (automatic context compaction)?",
    preset !== "minimal",
  );
  const hudFlag = await toggle(
    rl,
    "  hud (status line display)?",
    preset !== "minimal",
  );
  const browserFlag = await toggle(
    rl,
    "  browser (browser automation)?",
    ["experimental", "full"].includes(preset),
  );
  const teamDispatch = await toggle(
    rl,
    "  team-dispatch (multi-agent dispatch)?",
    ["full", "experimental", "production"].includes(preset),
  );

  const features: Record<string, boolean> = {
    "mutation-gate": mutationGate,
    firewall,
    "secret-guard": secretGuard,
    "cost-ledger": costLedger,
    "proof-gate": proofGate,
    "tdd-gate": tddGate,
    "trust-review": trustReview,
    "auto-compact": autoCompact,
    hud: hudFlag,
    browser: browserFlag,
    "team-dispatch": teamDispatch,
  };

  const enabled = Object.entries(features)
    .filter(([, v]) => v)
    .map(([k]) => k);
  console.log(
    `\n✅ Advanced config for \x1b[1m${projectName}\x1b[0m (preset: ${preset}, mode: ${mode})`,
  );
  console.log(`   Enabled: ${enabled.join(", ")}\n`);

  return { projectName, preset, mode, features };
}

export const initCommand: CommandModule = {
  command: "init",
  describe:
    "Interactive first-time setup wizard (doctor → plan → confirm → apply)",
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
        description: "Show preset, mode, and key feature flag options",
        default: false,
      })
      .option("advanced", {
        type: "boolean",
        description: "Show all configuration options",
        default: false,
      }),
  handler: async (argv) => {
    const tier = determineTier(argv);

    if (!argv.yes) {
      const rl = createInterface({
        input: process.stdin,
        output: process.stdout,
      });

      try {
        let config: CollectedConfig;

        switch (tier) {
          case "configure":
            config = await collectTier2(rl);
            break;
          case "advanced":
            config = await collectTier3(rl);
            break;
          default:
            config = await collectTier1(rl);
            break;
        }

        process.env.OMG_INIT_PROJECT_NAME = config.projectName;
        process.env.OMG_INIT_PRESET = config.preset;
        if (config.mode) process.env.OMG_INIT_MODE = config.mode;
        if (config.features) {
          process.env.OMG_INIT_FEATURES = JSON.stringify(config.features);
        }
      } finally {
        rl.close();
      }
    }

    const { initWizard } = await import("../../install/orchestrator.js");
    await initWizard({
      autoConfirm: Boolean(argv.yes),
      json: Boolean(argv.json),
    });

    if (tier === "default") {
      console.log(
        "\nRun with --configure for more options, --advanced for full control",
      );
    }
  },
};
