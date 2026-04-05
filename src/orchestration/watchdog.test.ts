import { describe, expect, test } from "bun:test";
import { WorkerWatchdog } from "./watchdog.js";

describe("WorkerWatchdog", () => {
  test("detects stall after threshold exceeded", () => {
    const clock = { now: 1_000 };
    const watchdog = WorkerWatchdog.create({ now: () => clock.now });

    watchdog.heartbeat("worker-a");
    clock.now += 2_500;

    expect(watchdog.detectStall("worker-a", 2_000)).toBe(true);
  });

  test("fresh heartbeat clears stall status", () => {
    const clock = { now: 2_000 };
    const watchdog = WorkerWatchdog.create({ now: () => clock.now });

    watchdog.heartbeat("worker-a");
    clock.now += 4_000;
    expect(watchdog.detectStall("worker-a", 3_000)).toBe(true);

    watchdog.heartbeat("worker-a");
    clock.now += 500;
    expect(watchdog.detectStall("worker-a", 3_000)).toBe(false);
  });

  test("worker without heartbeat is considered stalled", () => {
    const watchdog = WorkerWatchdog.create({ now: () => 5_000 });
    expect(watchdog.detectStall("unknown-worker", 1_000)).toBe(true);
  });
});
