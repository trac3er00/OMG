import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { CommandModule } from "yargs";
import { CheckpointSchema } from "./pause.js";

const CHECKPOINT_TTL_MS = 24 * 60 * 60 * 1000;

function isCheckpointStale(
  timestamp: string,
  ttlMs: number = CHECKPOINT_TTL_MS,
): boolean {
  const checkpointTime = new Date(timestamp).getTime();
  return Date.now() - checkpointTime > ttlMs;
}

function isVersionCompatible(
  checkpointVersion: string,
  currentVersion: string,
): boolean {
  const [cMaj, cMin] = checkpointVersion.split(".").map(Number);
  const [sMaj, sMin] = currentVersion.split(".").map(Number);
  return cMaj === sMaj && cMin === sMin;
}

export function findLatestCheckpoint(projectDir: string): string | null {
  const stateDir = join(projectDir, ".omg", "state");
  if (!existsSync(stateDir)) return null;

  const files = readdirSync(stateDir)
    .filter((f) => f.startsWith("checkpoint-") && f.endsWith(".json"))
    .map((f) => ({ file: f, path: join(stateDir, f) }))
    .sort((a, b) => b.file.localeCompare(a.file));

  return files.length > 0 ? files[0].path : null;
}

export function restoreFromCheckpoint(projectDir: string): {
  success: boolean;
  message: string;
} {
  const checkpointPath = findLatestCheckpoint(projectDir);

  if (!checkpointPath) {
    return {
      success: false,
      message: "No checkpoint found. Run 'omg pause' first.",
    };
  }

  let raw: unknown;
  try {
    raw = JSON.parse(readFileSync(checkpointPath, "utf8"));
  } catch {
    return {
      success: false,
      message: `Failed to read checkpoint: ${checkpointPath}`,
    };
  }

  const parsed = CheckpointSchema.safeParse(raw);
  if (!parsed.success) {
    return { success: false, message: "Checkpoint file has invalid schema." };
  }

  const checkpoint = parsed.data;

  if (isCheckpointStale(checkpoint.timestamp)) {
    return {
      success: false,
      message: `Checkpoint is stale (older than 24h). timestamp=${checkpoint.timestamp}`,
    };
  }

  const currentVersion = "2.3.0";
  if (!isVersionCompatible(checkpoint.version, currentVersion)) {
    return {
      success: false,
      message: `Version mismatch: checkpoint=${checkpoint.version}, current=${currentVersion}`,
    };
  }

  return {
    success: true,
    message: `Restored: session_id=${checkpoint.session_id}, timestamp=${checkpoint.timestamp}, pending_tasks=${checkpoint.pending_tasks.length}`,
  };
}

interface ContinueArgs {
  readonly quiet: boolean;
}

export const continueCommand: CommandModule<object, ContinueArgs> = {
  command: "continue",
  describe: "Restore session from the most recent checkpoint",
  builder: (yargs: any) =>
    yargs.option("quiet", {
      type: "boolean",
      default: false,
      describe: "Suppress output",
    }),
  handler: (argv) => {
    const projectDir = process.cwd();
    const result = restoreFromCheckpoint(projectDir);
    if (!result.success) {
      console.error(result.message);
      process.exit(1);
    }
    if (!argv.quiet) {
      console.log(result.message);
    }
  },
};
