import { HudState } from "./hud.js";
import { OrchestrationSession, type SessionEvent } from "./session.js";

export interface HudServerOptions {
  readonly session: OrchestrationSession;
  readonly hud?: HudState;
  readonly refreshIntervalMs?: number;
}

export class HudServer {
  static create(options: HudServerOptions): HudServer {
    return new HudServer(options);
  }

  readonly hud: HudState;
  private readonly session: OrchestrationSession;
  private refreshInterval: ReturnType<typeof setInterval> | null = null;
  private readonly refreshIntervalMs: number;

  constructor(options: HudServerOptions) {
    this.session = options.session;
    this.hud = options.hud ?? HudState.create();
    this.refreshIntervalMs = options.refreshIntervalMs ?? 1_000;
  }

  start(): void {
    this.session.on("event", (event: SessionEvent) => {
      this.hud.pushEvent(event);
    });

    this.refreshInterval = setInterval(() => {
      this.hud.update(this.session.snapshot());
    }, this.refreshIntervalMs);

    this.hud.update(this.session.snapshot());
  }

  stop(): void {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
  }

  renderAnsi(): string {
    return this.hud.render();
  }

  snapshotJson(): Record<string, unknown> {
    const snap = this.session.snapshot();
    return {
      sessionId: snap.sessionId,
      mode: snap.mode,
      status: snap.status,
      startedAt: snap.startedAt,
      elapsedMs: snap.elapsedMs,
      agents: snap.agents.map((a) => ({
        agentId: a.agentId,
        taskId: a.taskId,
        state: String(a.state),
        category: a.category,
        elapsedMs: a.elapsedMs,
      })),
      progress: {
        total: snap.tasksTotal,
        completed: snap.tasksCompleted,
        failed: snap.tasksFailed,
        skipped: snap.tasksSkipped,
      },
      budget: snap.budgetPressure,
      recentEvents: snap.events.slice(-20).map((e) => ({
        type: e.type,
        timestamp: e.timestamp,
        payload: e.payload,
      })),
    };
  }
}
