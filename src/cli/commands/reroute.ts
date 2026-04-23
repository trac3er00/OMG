import type { CommandModule } from "yargs";

import {
  detectCostSpike,
  detectLoop,
  detectStuck,
  handleFailure,
  printSteeringDecision,
  type FailureType,
} from "./failure-steering.js";

const PROOF_SCORE_REROUTE_THRESHOLD = 40;
const DEFAULT_AUTO_REROUTE_RETRIES = 3;

export interface RerouteOptions {
  readonly failureType?: FailureType | undefined;
  readonly recentActions?: string | undefined;
  readonly currentCost?: number | undefined;
  readonly expectedCost?: number | undefined;
  readonly progressHistory?: string | undefined;
  readonly goal?: string | undefined;
  readonly proofScore?: number | undefined;
  readonly autoReroute?: boolean | undefined;
  readonly execute?: (() => Promise<number>) | undefined;
}

interface RerouteArgs {
  "failure-type": FailureType | undefined;
  "recent-actions": string | undefined;
  "current-cost": number | undefined;
  "expected-cost": number | undefined;
  "progress-history": string | undefined;
  goal: string | undefined;
  "proof-score": number | undefined;
  "auto-reroute": boolean | undefined;
}

/** Check if reroute is needed based on ProofScore */
export function shouldReroute(score: number): boolean {
  return score < PROOF_SCORE_REROUTE_THRESHOLD;
}

/** Suggest reroute to user (non-blocking) */
export function suggestReroute(goal: string, score: number): void {
  console.error(
    `⚠️  ProofScore ${score}/100 is below threshold (${PROOF_SCORE_REROUTE_THRESHOLD}). Consider rerouting.`,
  );
  console.error(`   Try: omg "${goal}" with a different approach`);
}

/** Auto-reroute: retry up to maxRetries times */
export async function autoReroute(
  goal: string,
  execute: () => Promise<number>,
  maxRetries: number = DEFAULT_AUTO_REROUTE_RETRIES,
): Promise<{ attempts: number; finalScore: number; success: boolean }> {
  void goal;

  let attempts = 0;
  let score = 0;

  while (attempts < maxRetries) {
    attempts += 1;
    score = await execute();

    if (!shouldReroute(score)) {
      return { attempts, finalScore: score, success: true };
    }

    if (attempts < maxRetries) {
      console.error(
        `Attempt ${attempts}/${maxRetries} failed (score: ${score}). Retrying...`,
      );
    }
  }

  return { attempts, finalScore: score, success: false };
}

function parseList(value: string | undefined): string[] {
  return (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function parseProgressHistory(
  value: string | undefined,
): Array<number | string> {
  return parseList(value).map((item) => {
    const numeric = Number(item);
    return Number.isFinite(numeric) ? numeric : item;
  });
}

function resolveFailureType(
  projectDir: string,
  options: RerouteOptions,
): FailureType | null {
  if (options.failureType) {
    return options.failureType;
  }

  const recentActions = parseList(options.recentActions);
  if (recentActions.length > 0 && detectLoop(projectDir, recentActions)) {
    return "loop";
  }

  if (
    options.currentCost !== undefined &&
    options.expectedCost !== undefined &&
    detectCostSpike(projectDir, options.currentCost, options.expectedCost)
  ) {
    return "cost_spike";
  }

  const progressHistory = parseProgressHistory(options.progressHistory);
  if (progressHistory.length > 0 && detectStuck(projectDir, progressHistory)) {
    return "stuck";
  }

  return null;
}

export async function runReroute(options: RerouteOptions = {}): Promise<void> {
  const {
    autoReroute: autoRerouteEnabled = false,
    execute,
    goal,
    proofScore,
  } = options;
  const projectDir = process.cwd();

  const run = async (): Promise<void> => {
    let proofScoreHandled = false;

    if (autoRerouteEnabled && goal && execute) {
      const result = await autoReroute(
        goal,
        execute,
        DEFAULT_AUTO_REROUTE_RETRIES,
      );
      proofScoreHandled = true;

      if (!result.success) {
        suggestReroute(goal, result.finalScore);
      }
    } else if (
      typeof proofScore === "number" &&
      goal &&
      shouldReroute(proofScore)
    ) {
      suggestReroute(goal, proofScore);
      proofScoreHandled = true;
    }

    const failureType = resolveFailureType(projectDir, options);

    if (!failureType) {
      if (!proofScoreHandled) {
        console.log(
          "No steering failure detected. Provide --failure-type or detection inputs.",
        );
      }
      return;
    }

    const decision = handleFailure(projectDir, failureType, {
      command: "reroute",
      recent_actions: parseList(options.recentActions),
      current_cost: options.currentCost,
      expected_cost: options.expectedCost,
      progress_history: parseProgressHistory(options.progressHistory),
      goal,
      proof_score: proofScore,
      auto_reroute: autoRerouteEnabled,
    });
    printSteeringDecision("reroute", decision);
  };

  await run();
}

export const rerouteCommand: CommandModule<object, RerouteArgs> = {
  command: "reroute",
  describe: "Detect failure signals and return a steering action",
  builder: (yargs) =>
    yargs
      .option("failure-type", {
        type: "string",
        choices: ["loop", "cost_spike", "stuck"] as const,
        description: "Force a specific failure type",
      })
      .option("recent-actions", {
        type: "string",
        description: "Comma-separated recent actions for loop detection",
      })
      .option("current-cost", {
        type: "number",
        description: "Current observed cost",
      })
      .option("expected-cost", {
        type: "number",
        description: "Expected baseline cost",
      })
      .option("progress-history", {
        type: "string",
        description: "Comma-separated progress history for stuck detection",
      })
      .option("goal", {
        type: "string",
        description: "Goal text to include in reroute suggestions",
      })
      .option("proof-score", {
        type: "number",
        description: "ProofScore to evaluate for reroute suggestions",
      })
      .option("auto-reroute", {
        type: "boolean",
        default: false,
        description: "Automatically retry rerouting up to 3 times",
      }),
  handler: async (argv): Promise<void> => {
    await runReroute({
      failureType: argv["failure-type"],
      recentActions: argv["recent-actions"],
      currentCost: argv["current-cost"],
      expectedCost: argv["expected-cost"],
      progressHistory: argv["progress-history"],
      goal: argv.goal,
      proofScore: argv["proof-score"],
      autoReroute: argv["auto-reroute"],
    });
  },
};
