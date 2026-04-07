import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { z } from "zod";
import type { CommandModule } from "yargs";

export const CheckpointSchema = z.object({
  session_id: z.string(),
  timestamp: z.string(),
  active_task: z.string().optional(),
  pending_tasks: z.array(z.string()).default([]),
  memory_snapshot: z.record(z.string(), z.unknown()).default({}),
  context_summary: z.string().default(""),
  version: z.string(),
  provider: z.string().default("unknown"),
});

export type Checkpoint = z.infer<typeof CheckpointSchema>;

export function createPauseCheckpoint(projectDir: string): string {
  const sessionId = `pause-${Date.now()}`;
  const checkpoint: Checkpoint = CheckpointSchema.parse({
    session_id: sessionId,
    timestamp: new Date().toISOString(),
    active_task: undefined,
    pending_tasks: [],
    memory_snapshot: {},
    context_summary: "Session paused by user",
    version: "2.3.0",
    provider: process.env.OMG_PROVIDER ?? "unknown",
  });

  const stateDir = join(projectDir, ".omg", "state");
  mkdirSync(stateDir, { recursive: true });
  const filename = join(stateDir, `checkpoint-${sessionId}.json`);
  writeFileSync(filename, JSON.stringify(checkpoint, null, 2), "utf8");
  return filename;
}

interface PauseArgs {
  readonly quiet: boolean;
}

export const pauseCommand: CommandModule<object, PauseArgs> = {
  command: "pause",
  describe: "Pause current session and write checkpoint",
  builder: (yargs: any) =>
    yargs.option("quiet", {
      type: "boolean",
      default: false,
      describe: "Suppress output",
    }),
  handler: (argv) => {
    const projectDir = process.cwd();
    const filename = createPauseCheckpoint(projectDir);
    if (!argv.quiet) {
      console.log(`Checkpoint saved to: ${filename}`);
    }
  },
};
