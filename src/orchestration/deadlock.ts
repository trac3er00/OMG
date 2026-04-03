import { z } from "zod";

export const DEADLOCK_TIMEOUT_MS = 30_000;
export const ORPHAN_HEARTBEAT_INTERVAL_MS = 5_000;

export type ResourceLockPriority = "high" | "medium" | "low";
const PRIORITY_VALUES: Record<ResourceLockPriority, number> = {
  high: 2,
  medium: 1,
  low: 0,
};

export const ResourceLockSchema = z.object({
  resource_id: z.string(),
  holder_id: z.string(),
  priority: z.enum(["high", "medium", "low"]),
  acquired_at: z.number(),
  timeout_ms: z.number().positive(),
});
export type ResourceLock = z.infer<typeof ResourceLockSchema>;

export interface LockAcquisitionResult {
  readonly acquired: boolean;
  readonly lock: ResourceLock | null;
  readonly queued_position: number;
  readonly error?: string;
}

export interface OrphanDetectionResult {
  readonly orphan_ids: readonly string[];
  readonly checked_at: number;
}

export class ResourceLockManager {
  private readonly locks = new Map<string, ResourceLock>();
  private readonly queues = new Map<string, ResourceLock[]>();
  private readonly agentHeartbeats = new Map<string, number>();

  tryAcquire(
    resourceId: string,
    holderId: string,
    priority: ResourceLockPriority = "medium",
    timeoutMs = DEADLOCK_TIMEOUT_MS,
  ): LockAcquisitionResult {
    const existing = this.locks.get(resourceId);

    if (existing == null) {
      const lock = ResourceLockSchema.parse({
        resource_id: resourceId,
        holder_id: holderId,
        priority,
        acquired_at: Date.now(),
        timeout_ms: timeoutMs,
      });
      this.locks.set(resourceId, lock);
      return { acquired: true, lock, queued_position: 0 };
    }

    const existingPriority = PRIORITY_VALUES[existing.priority] ?? 0;
    const newPriority = PRIORITY_VALUES[priority] ?? 0;

    if (newPriority > existingPriority) {
      const lock = ResourceLockSchema.parse({
        resource_id: resourceId,
        holder_id: holderId,
        priority,
        acquired_at: Date.now(),
        timeout_ms: timeoutMs,
      });
      this.locks.set(resourceId, lock);
      return { acquired: true, lock, queued_position: 0 };
    }

    let queue = this.queues.get(resourceId);
    if (queue == null) {
      queue = [];
      this.queues.set(resourceId, queue);
    }
    queue.push(
      ResourceLockSchema.parse({
        resource_id: resourceId,
        holder_id: holderId,
        priority,
        acquired_at: Date.now(),
        timeout_ms: timeoutMs,
      }),
    );
    queue.sort((a, b) => {
      const bVal = PRIORITY_VALUES[b.priority as ResourceLockPriority] ?? 0;
      const aVal = PRIORITY_VALUES[a.priority as ResourceLockPriority] ?? 0;
      return bVal - aVal;
    });

    return {
      acquired: false,
      lock: null,
      queued_position: queue.findIndex((q) => q.holder_id === holderId) + 1,
    };
  }

  release(resourceId: string, holderId: string): boolean {
    const existing = this.locks.get(resourceId);
    if (existing == null || existing.holder_id !== holderId) return false;
    this.locks.delete(resourceId);

    const queue = this.queues.get(resourceId);
    if (queue != null && queue.length > 0) {
      const next = queue.shift();
      if (next != null) {
        this.locks.set(resourceId, next);
      }
    }
    return true;
  }

  isLocked(resourceId: string): boolean {
    const lock = this.locks.get(resourceId);
    if (lock == null) return false;
    if (Date.now() - lock.acquired_at > lock.timeout_ms) {
      this.locks.delete(resourceId);
      return false;
    }
    return true;
  }

  heartbeat(agentId: string): void {
    this.agentHeartbeats.set(agentId, Date.now());
  }

  detectOrphans(
    staleThresholdMs = ORPHAN_HEARTBEAT_INTERVAL_MS * 3,
  ): OrphanDetectionResult {
    const now = Date.now();
    const orphan_ids: string[] = [];
    for (const [agentId, lastHeartbeat] of this.agentHeartbeats) {
      if (now - lastHeartbeat > staleThresholdMs) {
        orphan_ids.push(agentId);
      }
    }
    return { orphan_ids, checked_at: now };
  }

  terminateOrphan(agentId: string): void {
    this.agentHeartbeats.delete(agentId);
    for (const [resourceId, lock] of this.locks) {
      if (lock.holder_id === agentId) {
        this.release(resourceId, agentId);
      }
    }
  }

  getLockCount(): number {
    return this.locks.size;
  }
}
