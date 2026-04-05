import { spawnSync } from "node:child_process";
import type { CommandModule } from "yargs";

interface AutorunArgs {
  readonly goal: readonly (string | number)[];
  readonly json?: boolean;
  readonly tier?: string;
  readonly singleAgent?: boolean;
}

function normalizeGoal(rawGoal: readonly (string | number)[]): string {
  return rawGoal
    .map((part) => String(part ?? "").trim())
    .filter((part) => part.length > 0)
    .join(" ");
}

function runAutorun(
  goal: string,
  options: { readonly tier: string; readonly singleAgent: boolean },
): Record<string, unknown> {
  const command = [
    "-m",
    "runtime.autorun_pipeline",
    "--goal",
    goal,
    "--project-dir",
    process.cwd(),
    "--tier",
    options.tier,
    "--json",
  ];

  if (options.singleAgent) {
    command.push("--single-agent");
  }

  const result = spawnSync("python3", command, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 300_000,
  });

  const stdout = `${result.stdout ?? ""}`.trim();
  const stderr = `${result.stderr ?? ""}`.trim();
  if (result.status !== 0) {
    throw new Error(
      [
        `autorun pipeline failed (exit=${result.status ?? "unknown"})`,
        stderr,
        stdout,
      ]
        .filter((segment) => segment.length > 0)
        .join("\n"),
    );
  }

  if (!stdout) {
    throw new Error("autorun pipeline returned empty output");
  }

  try {
    const payload = JSON.parse(stdout) as Record<string, unknown>;
    return payload;
  } catch (error) {
    throw new Error(
      `autorun pipeline returned invalid JSON: ${String(error)}\n${stdout}`,
    );
  }
}

function printHuman(payload: Record<string, unknown>): void {
  const stages =
    typeof payload.stages === "object" && payload.stages !== null
      ? (payload.stages as Record<string, unknown>)
      : {};
  const plan =
    typeof stages.plan === "object" && stages.plan !== null
      ? (stages.plan as Record<string, unknown>)
      : {};
  const review =
    typeof stages.review === "object" && stages.review !== null
      ? (stages.review as Record<string, unknown>)
      : {};
  const execute =
    typeof stages.execute === "object" && stages.execute !== null
      ? (stages.execute as Record<string, unknown>)
      : {};
  const verify =
    typeof stages.verify === "object" && stages.verify !== null
      ? (stages.verify as Record<string, unknown>)
      : {};

  const reviewCheckpoint =
    typeof review.governance_checkpoint === "object" &&
    review.governance_checkpoint !== null
      ? (review.governance_checkpoint as Record<string, unknown>)
      : {};
  const productionGate =
    typeof verify.production_gate === "object" &&
    verify.production_gate !== null
      ? (verify.production_gate as Record<string, unknown>)
      : {};

  console.log(`Autorun status: ${String(payload.status ?? "unknown")}`);
  console.log(
    `Plan: ${String(plan.task_count ?? 0)} tasks (plan_id=${String(plan.plan_id ?? "")})`,
  );
  console.log(`Review: ${String(reviewCheckpoint.decision ?? "unknown")}`);
  console.log(
    `Execute: ${String(execute.status ?? "unknown")} mode=${String(execute.executor_mode ?? "unknown")}`,
  );
  console.log(
    `Verify: proof_gate=${String(verify.proof_gate_verdict ?? "fail")} production=${String(productionGate.status ?? "blocked")}`,
  );

  const evidence = Array.isArray(payload.evidence) ? payload.evidence : [];
  for (const item of evidence) {
    const text = String(item ?? "").trim();
    if (text.length > 0) {
      console.log(`Evidence: ${text}`);
    }
  }
}

export const autorunCommand: CommandModule<object, AutorunArgs> = {
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
  handler: (argv): void => {
    const goal = normalizeGoal(argv.goal);
    if (!goal) {
      throw new Error("goal is required");
    }

    const payload = runAutorun(goal, {
      tier: String(argv.tier ?? "max"),
      singleAgent: Boolean(argv.singleAgent),
    });

    if (argv.json) {
      console.log(JSON.stringify(payload, null, 2));
      return;
    }
    printHuman(payload);
  },
};
