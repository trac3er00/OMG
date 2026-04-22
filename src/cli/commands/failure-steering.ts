import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export type FailureType = "loop" | "cost_spike" | "stuck";

export interface SteeringDecision {
  readonly action: string;
  readonly message: string;
}

interface CommandHistoryEntry {
  readonly command: string;
  readonly timestamp: string;
}

const COMMAND_HISTORY_LIMIT = 25;

function getStateDir(projectDir: string): string {
  return join(projectDir, ".omg", "state");
}

function getCommandHistoryPath(projectDir: string): string {
  return join(getStateDir(projectDir), "command_history.json");
}

function ensureStateDir(projectDir: string): void {
  mkdirSync(getStateDir(projectDir), { recursive: true });
}

function runPythonJson<T>(
  projectDir: string,
  script: string,
  args: readonly string[],
): T {
  const output = execFileSync("python3", ["-c", script, ...args], {
    cwd: projectDir,
    encoding: "utf8",
    timeout: 120_000,
  }).trim();
  return JSON.parse(output) as T;
}

function readCommandHistory(projectDir: string): CommandHistoryEntry[] {
  try {
    const raw = readFileSync(getCommandHistoryPath(projectDir), "utf8");
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.flatMap((entry) => {
      if (
        entry &&
        typeof entry === "object" &&
        typeof entry.command === "string" &&
        typeof entry.timestamp === "string"
      ) {
        return [
          {
            command: entry.command,
            timestamp: entry.timestamp,
          },
        ];
      }
      return [];
    });
  } catch {
    return [];
  }
}

function writeCommandHistory(
  projectDir: string,
  history: readonly CommandHistoryEntry[],
): void {
  ensureStateDir(projectDir);
  writeFileSync(
    getCommandHistoryPath(projectDir),
    JSON.stringify(history, null, 2) + "\n",
    "utf8",
  );
}

export function recordCommand(projectDir: string, command: string): string[] {
  const history = [
    ...readCommandHistory(projectDir),
    { command, timestamp: new Date().toISOString() },
  ].slice(-COMMAND_HISTORY_LIMIT);
  writeCommandHistory(projectDir, history);
  return history.map((entry) => entry.command);
}

export function detectLoop(
  projectDir: string,
  actions: readonly string[],
  threshold = 3,
): boolean {
  const script = [
    "import json, sys",
    "from runtime.failure_detector import detect_loop",
    "print(json.dumps(detect_loop(json.loads(sys.argv[1]), threshold=int(sys.argv[2]))))",
  ].join("; ");

  try {
    return runPythonJson<boolean>(projectDir, script, [
      JSON.stringify(actions),
      String(threshold),
    ]);
  } catch {
    return false;
  }
}

export function detectCostSpike(
  projectDir: string,
  currentCost: number,
  expectedCost: number,
  multiplier = 2,
): boolean {
  const script = [
    "import json, sys",
    "from runtime.failure_detector import detect_cost_spike",
    "print(json.dumps(detect_cost_spike(float(sys.argv[1]), float(sys.argv[2]), multiplier=float(sys.argv[3]))))",
  ].join("; ");

  try {
    return runPythonJson<boolean>(projectDir, script, [
      String(currentCost),
      String(expectedCost),
      String(multiplier),
    ]);
  } catch {
    return false;
  }
}

export function detectStuck(
  projectDir: string,
  progressHistory: readonly (number | string)[],
  window = 5,
): boolean {
  const script = [
    "import json, sys",
    "from runtime.failure_detector import detect_stuck",
    "print(json.dumps(detect_stuck(json.loads(sys.argv[1]), window=int(sys.argv[2]))))",
  ].join("; ");

  try {
    return runPythonJson<boolean>(projectDir, script, [
      JSON.stringify(progressHistory),
      String(window),
    ]);
  } catch {
    return false;
  }
}

export function handleFailure(
  projectDir: string,
  failureType: FailureType,
  context: Record<string, unknown> = {},
): SteeringDecision {
  const script = [
    "import json, sys",
    "from runtime.steering import handle_failure",
    "print(json.dumps(handle_failure(sys.argv[1], json.loads(sys.argv[2]))))",
  ].join("; ");

  try {
    return runPythonJson<SteeringDecision>(projectDir, script, [
      failureType,
      JSON.stringify({ ...context, project_dir: projectDir }),
    ]);
  } catch (error) {
    return {
      action: "inspect",
      message: `Steering unavailable: ${String(error)}`,
    };
  }
}

export function maybeAutoReroute(
  projectDir: string,
  command: string,
  context: Record<string, unknown> = {},
): SteeringDecision | null {
  const actions = recordCommand(projectDir, command);
  if (!detectLoop(projectDir, actions)) {
    return null;
  }

  return handleFailure(projectDir, "loop", {
    ...context,
    command,
    recent_actions: actions.slice(-3),
  });
}

export function inferFailureType(error: string): FailureType {
  const normalized = error.toLowerCase();
  if (normalized.includes("cost") || normalized.includes("budget")) {
    return "cost_spike";
  }
  if (normalized.includes("loop") || normalized.includes("retry")) {
    return "loop";
  }
  return "stuck";
}

export function printSteeringDecision(
  source: string,
  decision: SteeringDecision,
): void {
  console.log(`\n🧭 Steering (${source})`);
  console.log(`Action: ${decision.action}`);
  console.log(`Message: ${decision.message}`);
}
