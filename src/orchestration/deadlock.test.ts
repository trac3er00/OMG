import { describe, test, expect } from "bun:test";
import { DEADLOCK_TIMEOUT_MS, ResourceLockManager } from "./deadlock.js";

describe("orchestration/deadlock", () => {
  test("DEADLOCK_TIMEOUT_MS is 30000", () => {
    expect(DEADLOCK_TIMEOUT_MS).toBe(30_000);
  });

  describe("ResourceLockManager", () => {
    describe("tryAcquire", () => {
      test("acquires free resource immediately", () => {
        const mgr = new ResourceLockManager();
        const result = mgr.tryAcquire("file.ts", "agent-a");
        expect(result.acquired).toBe(true);
        expect(result.lock?.holder_id).toBe("agent-a");
      });

      test("queues when resource is held at same priority", () => {
        const mgr = new ResourceLockManager();
        mgr.tryAcquire("file.ts", "agent-a");
        const result = mgr.tryAcquire("file.ts", "agent-b");
        expect(result.acquired).toBe(false);
        expect(result.queued_position).toBeGreaterThan(0);
      });

      test("high priority agent preempts medium priority", () => {
        const mgr = new ResourceLockManager();
        mgr.tryAcquire("file.ts", "agent-a", "medium");
        const result = mgr.tryAcquire("file.ts", "agent-b", "high");
        expect(result.acquired).toBe(true);
        expect(result.lock?.holder_id).toBe("agent-b");
      });

      test("same agent can acquire different resources", () => {
        const mgr = new ResourceLockManager();
        const r1 = mgr.tryAcquire("file-a.ts", "agent-a");
        const r2 = mgr.tryAcquire("file-b.ts", "agent-a");
        expect(r1.acquired).toBe(true);
        expect(r2.acquired).toBe(true);
      });
    });

    describe("release", () => {
      test("releases lock and allows next in queue", () => {
        const mgr = new ResourceLockManager();
        mgr.tryAcquire("file.ts", "agent-a");
        mgr.tryAcquire("file.ts", "agent-b");
        const released = mgr.release("file.ts", "agent-a");
        expect(released).toBe(true);
        expect(mgr.isLocked("file.ts")).toBe(true);
      });

      test("returns false when not the holder", () => {
        const mgr = new ResourceLockManager();
        mgr.tryAcquire("file.ts", "agent-a");
        expect(mgr.release("file.ts", "agent-b")).toBe(false);
      });

      test("returns false for unowned resource", () => {
        const mgr = new ResourceLockManager();
        expect(mgr.release("nonexistent.ts", "agent-a")).toBe(false);
      });
    });

    describe("isLocked", () => {
      test("returns false for unlocked resource", () => {
        const mgr = new ResourceLockManager();
        expect(mgr.isLocked("file.ts")).toBe(false);
      });

      test("returns true for locked resource", () => {
        const mgr = new ResourceLockManager();
        mgr.tryAcquire("file.ts", "agent-a");
        expect(mgr.isLocked("file.ts")).toBe(true);
      });

      test("auto-releases timed-out locks", () => {
        const mgr = new ResourceLockManager();
        mgr.tryAcquire("file.ts", "agent-a", "medium", 1);
        return new Promise<void>((resolve) => {
          setTimeout(() => {
            expect(mgr.isLocked("file.ts")).toBe(false);
            resolve();
          }, 10);
        });
      });
    });

    describe("orphan detection", () => {
      test("fresh agents are not orphans", () => {
        const mgr = new ResourceLockManager();
        mgr.heartbeat("agent-a");
        const result = mgr.detectOrphans(10000);
        expect(result.orphan_ids).not.toContain("agent-a");
      });

      test("stale agents are detected as orphans", () => {
        const mgr = new ResourceLockManager();
        mgr.heartbeat("agent-stale");
        const result = mgr.detectOrphans(-1);
        expect(result.orphan_ids).toContain("agent-stale");
      });

      test("terminateOrphan releases its locks", () => {
        const mgr = new ResourceLockManager();
        mgr.tryAcquire("file.ts", "orphan-agent");
        mgr.heartbeat("orphan-agent");
        expect(mgr.isLocked("file.ts")).toBe(true);
        mgr.terminateOrphan("orphan-agent");
        expect(mgr.isLocked("file.ts")).toBe(false);
      });
    });

    describe("concurrent access", () => {
      test("multiple agents on different resources never conflict", () => {
        const mgr = new ResourceLockManager();
        const resources = ["a.ts", "b.ts", "c.ts", "d.ts", "e.ts"];
        const agents = ["a1", "a2", "a3", "a4", "a5"];
        for (let i = 0; i < resources.length; i++) {
          const result = mgr.tryAcquire(resources[i]!, agents[i]!);
          expect(result.acquired).toBe(true);
        }
        expect(mgr.getLockCount()).toBe(resources.length);
      });
    });
  });
});
