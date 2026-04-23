import type { CommandModule } from "yargs";

import {
  detectCostSpike,
  detectLoop,
  detectStuck,
  handleFailure,
  printSteeringDecision,
  type FailureType,
} from "./failure-steering.js";

export interface RerouteOptions {
  readonly failureType?: FailureType | undefined;
  readonly recentActions?: string | undefined;
  readonly currentCost?: number | undefined;
  readonly expectedCost?: number | undefined;
  readonly progressHistory?: string | undefined;
}

interface RerouteArgs {
  "failure-type": FailureType | undefined;
  "recent-actions": string | undefined;
  "current-cost": number | undefined;
  "expected-cost": number | undefined;
  "progress-history": string | undefined;
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

export function runReroute(options: RerouteOptions = {}): void {
  const projectDir = process.cwd();
  const failureType = resolveFailureType(projectDir, options);

  if (!failureType) {
    console.log(
      "No steering failure detected. Provide --failure-type or detection inputs.",
    );
    return;
  }

  const decision = handleFailure(projectDir, failureType, {
    command: "reroute",
    recent_actions: parseList(options.recentActions),
    current_cost: options.currentCost,
    expected_cost: options.expectedCost,
    progress_history: parseProgressHistory(options.progressHistory),
  });
  printSteeringDecision("reroute", decision);
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
      }),
  handler: (argv): void => {
    runReroute({
      failureType: argv["failure-type"],
      recentActions: argv["recent-actions"],
      currentCost: argv["current-cost"],
      expectedCost: argv["expected-cost"],
      progressHistory: argv["progress-history"],
    });
  },
};
