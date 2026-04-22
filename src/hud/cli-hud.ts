export interface HudData {
  progress: number;
  currentTask: string;
  modelReasoning?: string;
  failureLocation?: string;
  costEstimate?: number;
}

export class CliHud {
  private isRunning: boolean = false;

  start(): void {
    this.isRunning = true;
    process.stdout.write("\x1b[?25l");
  }

  update(data: HudData): void {
    if (!this.isRunning) return;

    const progressStr = CliHud.formatProgress(data.progress);
    const taskStr = `Task: ${data.currentTask}`;
    const reasoningStr = data.modelReasoning
      ? `\nReasoning: ${data.modelReasoning}`
      : "";
    const failureStr = data.failureLocation
      ? `\nFailure: ${data.failureLocation}`
      : "";
    const costStr =
      data.costEstimate !== undefined
        ? `\nCost Est: $${data.costEstimate.toFixed(4)}`
        : "";

    process.stdout.write("\x1b[2K\x1b[0G");

    const output = `${progressStr} | ${taskStr}${reasoningStr}${failureStr}${costStr}\n`;
    process.stdout.write(output);

    const lines = output.split("\n").length - 1;
    if (lines > 0) {
      process.stdout.write(`\x1b[${lines}A`);
    }
  }

  stop(): void {
    if (!this.isRunning) return;
    this.isRunning = false;
    process.stdout.write("\x1b[?25h");
    process.stdout.write("\n");
  }

  static formatProgress(pct: number): string {
    const clamped = Math.max(0, Math.min(100, pct));
    const width = 20;
    const filled = Math.round((clamped / 100) * width);
    const empty = width - filled;
    return `[${"#".repeat(filled)}${"-".repeat(empty)}] ${clamped.toFixed(1)}%`;
  }
}
