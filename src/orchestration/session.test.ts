import { describe, expect, test } from "bun:test";
import {
  OrchestrationSession,
  OrchestrationTaskSchema,
  type OrchestrationTask,
} from "./session.js";

function fixedDate(): Date {
  return new Date("2026-01-15T10:00:00Z");
}

function createTestTasks(): OrchestrationTask[] {
  return [
    OrchestrationTaskSchema.parse({
      id: "task-a",
      prompt: "Implement the authentication module",
      deps: [],
      category: "deep",
      skills: [],
      priority: "high",
      timeout_ms: 5_000,
    }),
    OrchestrationTaskSchema.parse({
      id: "task-b",
      prompt: "Add simple unit tests for auth",
      deps: ["task-a"],
      skills: [],
      priority: "medium",
      timeout_ms: 5_000,
    }),
  ];
}

describe("OrchestrationSession", () => {
  test("create() returns a session with idle status", () => {
    const session = OrchestrationSession.create({
      mode: "ultrawork",
      idGenerator: () => "test-session-1",
      now: fixedDate,
    });

    expect(session.sessionId).toBe("test-session-1");
    expect(session.mode).toBe("ultrawork");
    expect(session.getStatus()).toBe("idle");
  });

  test("snapshot() returns valid structure before orchestration", () => {
    const session = OrchestrationSession.create({
      mode: "team",
      idGenerator: () => "test-session-2",
      now: fixedDate,
    });

    const snap = session.snapshot();
    expect(snap.sessionId).toBe("test-session-2");
    expect(snap.mode).toBe("team");
    expect(snap.status).toBe("idle");
    expect(snap.agents).toHaveLength(0);
    expect(snap.tasksTotal).toBe(0);
    expect(snap.tasksCompleted).toBe(0);
    expect(snap.elapsedMs).toBe(0);
    expect(snap.budgetPressure).toBeDefined();
    expect(snap.budgetPressure.tokens).toBe(0);
  });

  test("cancel() on idle session is a no-op", async () => {
    const session = OrchestrationSession.create({
      idGenerator: () => "test-session-3",
      now: fixedDate,
    });

    await session.cancel();
    expect(session.getStatus()).toBe("idle");
  });

  test("acquireLock and releaseLock work for resource coordination", () => {
    const session = OrchestrationSession.create({
      idGenerator: () => "test-session-4",
      now: fixedDate,
    });

    const acquired = session.acquireLock("file.ts", "agent-1", "high");
    expect(acquired).toBe(true);

    const acquiredAgain = session.acquireLock("file.ts", "agent-2", "low");
    expect(acquiredAgain).toBe(false);

    const released = session.releaseLock("file.ts", "agent-1");
    expect(released).toBe(true);

    const freshAcquire = session.acquireLock("config.ts", "agent-3", "medium");
    expect(freshAcquire).toBe(true);

    const releaseUnheld = session.releaseLock("config.ts", "agent-99");
    expect(releaseUnheld).toBe(false);
  });

  test("OrchestrationTaskSchema validates required fields", () => {
    const valid = OrchestrationTaskSchema.parse({
      id: "test-task",
      prompt: "do something",
    });
    expect(valid.id).toBe("test-task");
    expect(valid.deps).toEqual([]);
    expect(valid.priority).toBe("medium");
    expect(valid.timeout_ms).toBe(120_000);
    expect(valid.skills).toEqual([]);

    expect(() =>
      OrchestrationTaskSchema.parse({ id: "", prompt: "x" }),
    ).toThrow();
    expect(() =>
      OrchestrationTaskSchema.parse({ id: "x", prompt: "" }),
    ).toThrow();
  });

  test("session emits events during orchestration lifecycle", async () => {
    const events: string[] = [];
    const session = OrchestrationSession.create({
      mode: "sequential",
      idGenerator: () => "test-session-5",
      now: fixedDate,
      concurrency: 1,
      projectDir: "/tmp",
    });

    session.on("event", (event: { type: string }) => {
      events.push(event.type);
    });

    const tasks = createTestTasks();

    try {
      for await (const _result of session.orchestrate(tasks)) {
        break;
      }
    } catch {
      void 0;
    }

    expect(events.length).toBeGreaterThan(0);
    expect(events[0]).toBe("session_started");
  });

  test("mode defaults are correct", () => {
    const ultrawork = OrchestrationSession.create({
      mode: "ultrawork",
      idGenerator: () => "u",
    });
    expect(ultrawork.mode).toBe("ultrawork");

    const team = OrchestrationSession.create({
      mode: "team",
      idGenerator: () => "t",
    });
    expect(team.mode).toBe("team");

    const seq = OrchestrationSession.create({
      mode: "sequential",
      idGenerator: () => "s",
    });
    expect(seq.mode).toBe("sequential");

    const defaultMode = OrchestrationSession.create({ idGenerator: () => "d" });
    expect(defaultMode.mode).toBe("ultrawork");
  });
});
