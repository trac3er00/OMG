import type {
  SessionSnapshot,
  SessionEvent,
  AgentStatus,
  SessionStatus,
  OrchestrationMode,
} from "./session.js";

export interface HudRenderOptions {
  readonly width?: number;
  readonly maxEventLines?: number;
  readonly showBudget?: boolean;
  readonly showEvents?: boolean;
}

const BOLD = "\x1b[1m";
const DIM = "\x1b[2m";
const RESET = "\x1b[0m";
const GREEN = "\x1b[32m";
const YELLOW = "\x1b[33m";
const RED = "\x1b[31m";
const CYAN = "\x1b[36m";
const MAGENTA = "\x1b[35m";

const STATUS_COLOR: Record<string, string> = {
  completed: GREEN,
  fulfilled: GREEN,
  running: CYAN,
  RUNNING: CYAN,
  failed: RED,
  rejected: RED,
  FAILED: RED,
  skipped: YELLOW,
  cancelled: DIM,
  CANCELLED: DIM,
  idle: DIM,
};

function colorize(text: string, status: string): string {
  const color = STATUS_COLOR[status] ?? RESET;
  return `${color}${text}${RESET}`;
}

function pad(str: string, len: number): string {
  if (str.length >= len) return str.slice(0, len);
  return str + " ".repeat(len - str.length);
}

function formatMs(ms: number): string {
  if (ms < 1_000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1_000).toFixed(1)}s`;
  const mins = Math.floor(ms / 60_000);
  const secs = Math.floor((ms % 60_000) / 1_000);
  return `${mins}m${secs}s`;
}

function progressBar(completed: number, total: number, width: number): string {
  if (total === 0) return `[${"░".repeat(width)}] 0/0`;
  const ratio = Math.min(1, completed / total);
  const filled = Math.round(ratio * width);
  const empty = width - filled;
  return `[${"█".repeat(filled)}${"░".repeat(empty)}] ${completed}/${total}`;
}

function budgetGauge(label: string, pressure: number, width: number): string {
  const clamped = Math.min(1, Math.max(0, pressure));
  const filled = Math.round(clamped * width);
  const empty = width - filled;
  const color = clamped > 0.9 ? RED : clamped > 0.7 ? YELLOW : GREEN;
  const pct = `${Math.round(clamped * 100)}%`;
  return `  ${pad(label, 12)} ${color}[${"█".repeat(filled)}${"░".repeat(empty)}]${RESET} ${pct}`;
}

function modeLabel(mode: OrchestrationMode): string {
  if (mode === "ultrawork") return `${MAGENTA}ULTRAWORK${RESET}`;
  if (mode === "team") return `${CYAN}TEAM${RESET}`;
  return `${DIM}SEQUENTIAL${RESET}`;
}

function statusLabel(status: SessionStatus): string {
  return colorize(status.toUpperCase(), status);
}

export class HudState {
  static create(options: HudRenderOptions = {}): HudState {
    return new HudState(options);
  }

  private latestSnapshot: SessionSnapshot | null = null;
  private readonly recentEvents: SessionEvent[] = [];
  private readonly maxEventLines: number;
  private readonly width: number;
  private readonly showBudget: boolean;
  private readonly showEvents: boolean;

  constructor(options: HudRenderOptions = {}) {
    this.width = options.width ?? 80;
    this.maxEventLines = options.maxEventLines ?? 8;
    this.showBudget = options.showBudget ?? true;
    this.showEvents = options.showEvents ?? true;
  }

  update(snapshot: SessionSnapshot): void {
    this.latestSnapshot = snapshot;
    for (const event of snapshot.events) {
      if (
        !this.recentEvents.some(
          (e) => e.timestamp === event.timestamp && e.type === event.type,
        )
      ) {
        this.recentEvents.push(event);
      }
    }
    while (this.recentEvents.length > this.maxEventLines * 2) {
      this.recentEvents.shift();
    }
  }

  pushEvent(event: SessionEvent): void {
    this.recentEvents.push(event);
    while (this.recentEvents.length > this.maxEventLines * 2) {
      this.recentEvents.shift();
    }
  }

  render(): string {
    if (this.latestSnapshot == null) {
      return `${DIM}No orchestration session active${RESET}`;
    }

    const snap = this.latestSnapshot;
    const lines: string[] = [];

    lines.push(this.renderHeader(snap));
    lines.push("");

    if (snap.agents.length > 0) {
      lines.push(...this.renderAgentTable(snap.agents));
      lines.push("");
    }

    lines.push(this.renderProgress(snap));
    lines.push("");

    if (this.showBudget) {
      lines.push(...this.renderBudget(snap));
      lines.push("");
    }

    if (this.showEvents) {
      lines.push(...this.renderEventLog());
    }

    return lines.join("\n");
  }

  private renderHeader(snap: SessionSnapshot): string {
    const divider = "─".repeat(this.width);
    const sessionLine = `${BOLD}OMG Orchestration${RESET}  ${DIM}${snap.sessionId}${RESET}`;
    const modeLine = `Mode: ${modeLabel(snap.mode)}  Status: ${statusLabel(snap.status)}  Elapsed: ${BOLD}${formatMs(snap.elapsedMs)}${RESET}`;
    return `${divider}\n${sessionLine}\n${modeLine}\n${divider}`;
  }

  private renderAgentTable(agents: readonly AgentStatus[]): string[] {
    const lines: string[] = [];
    const header = `${BOLD}${pad("Agent", 16)} ${pad("Task", 20)} ${pad("Category", 16)} ${pad("Status", 10)} ${pad("Elapsed", 8)}${RESET}`;
    lines.push(header);

    for (const agent of agents) {
      const agentShort = agent.agentId.slice(0, 15);
      const taskShort = agent.taskId.slice(0, 19);
      const statusStr = colorize(
        pad(String(agent.state), 10),
        String(agent.state),
      );
      lines.push(
        `${pad(agentShort, 16)} ${pad(taskShort, 20)} ${pad(agent.category, 16)} ${statusStr} ${pad(formatMs(agent.elapsedMs), 8)}`,
      );
    }
    return lines;
  }

  private renderProgress(snap: SessionSnapshot): string {
    const total = snap.tasksTotal;
    const completed = snap.tasksCompleted;
    const failed = snap.tasksFailed;
    const skipped = snap.tasksSkipped;

    const bar = progressBar(completed, total, 30);
    const detail =
      failed > 0 || skipped > 0
        ? `  ${GREEN}${completed} done${RESET}  ${RED}${failed} failed${RESET}  ${YELLOW}${skipped} skipped${RESET}`
        : `  ${GREEN}${completed} done${RESET}`;

    return `  Progress: ${bar}${detail}`;
  }

  private renderBudget(snap: SessionSnapshot): string[] {
    const lines: string[] = [];
    lines.push(`${BOLD}  Budget${RESET}`);
    const pressure = snap.budgetPressure;
    lines.push(budgetGauge("Tokens", pressure.tokens ?? 0, 20));
    lines.push(budgetGauge("Wall Time", pressure.wall_time_ms ?? 0, 20));
    lines.push(budgetGauge("Memory", pressure.memory_mb ?? 0, 20));
    return lines;
  }

  private renderEventLog(): string[] {
    const lines: string[] = [];
    lines.push(`${BOLD}  Recent Events${RESET}`);
    const events = this.recentEvents.slice(-this.maxEventLines);
    if (events.length === 0) {
      lines.push(`  ${DIM}No events yet${RESET}`);
      return lines;
    }
    for (const event of events) {
      const time = event.timestamp.slice(11, 19);
      const typeColor =
        event.type.includes("fail") || event.type.includes("error")
          ? RED
          : event.type.includes("complete")
            ? GREEN
            : event.type.includes("spawn")
              ? CYAN
              : DIM;
      lines.push(
        `  ${DIM}${time}${RESET} ${typeColor}${event.type}${RESET} ${DIM}${formatEventPayload(event.payload)}${RESET}`,
      );
    }
    return lines;
  }
}

function formatEventPayload(
  payload: Readonly<Record<string, unknown>>,
): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(payload)) {
    if (key === "prompt" || key === "snapshot") continue;
    const str = typeof value === "string" ? value : JSON.stringify(value);
    parts.push(`${key}=${String(str).slice(0, 30)}`);
    if (parts.length >= 3) break;
  }
  return parts.join(" ");
}
