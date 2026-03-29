export interface WorkerWatchdogDeps {
  readonly now?: () => number;
}

export class WorkerWatchdog {
  static create(deps: WorkerWatchdogDeps = {}): WorkerWatchdog {
    return new WorkerWatchdog(deps);
  }

  private readonly now: () => number;
  private readonly heartbeats = new Map<string, number>();

  constructor(deps: WorkerWatchdogDeps = {}) {
    this.now = deps.now ?? (() => Date.now());
  }

  heartbeat(workerId: string): void {
    const normalized = normalizeWorkerId(workerId);
    this.heartbeats.set(normalized, this.now());
  }

  detectStall(workerId: string, thresholdMs: number): boolean {
    const normalized = normalizeWorkerId(workerId);
    const effectiveThresholdMs = Math.max(0, thresholdMs);
    const lastHeartbeatAt = this.heartbeats.get(normalized);
    if (lastHeartbeatAt === undefined) {
      return true;
    }
    const elapsedMs = this.now() - lastHeartbeatAt;
    return elapsedMs > effectiveThresholdMs;
  }
}

function normalizeWorkerId(workerId: string): string {
  return workerId.trim();
}
