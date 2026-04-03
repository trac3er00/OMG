import { describe, expect, test } from "bun:test";
import { HudState } from "./hud.js";
import { AgentState } from "./agent-manager.js";
import type { SessionSnapshot, SessionEvent } from "./session.js";

function makeSnapshot(
  overrides: Partial<SessionSnapshot> = {},
): SessionSnapshot {
  return {
    sessionId: "orch-test123",
    mode: "ultrawork",
    status: "running",
    startedAt: "2026-01-15T10:00:00Z",
    elapsedMs: 15_000,
    agents: [],
    tasksTotal: 5,
    tasksCompleted: 2,
    tasksFailed: 0,
    tasksSkipped: 0,
    budgetPressure: { tokens: 0.3, wall_time_ms: 0.1, memory_mb: 0.05 },
    events: [],
    ...overrides,
  };
}

function makeEvent(
  type: string,
  payload: Record<string, unknown> = {},
): SessionEvent {
  return {
    type,
    timestamp: "2026-01-15T10:00:05Z",
    sessionId: "orch-test123",
    payload,
  };
}

describe("HudState", () => {
  test("create() returns a HudState instance", () => {
    const hud = HudState.create();
    expect(hud).toBeInstanceOf(HudState);
  });

  test("render() with no snapshot shows inactive message", () => {
    const hud = HudState.create();
    const output = hud.render();
    expect(output).toContain("No orchestration session active");
  });

  test("render() with snapshot shows session header", () => {
    const hud = HudState.create();
    hud.update(makeSnapshot());
    const output = hud.render();
    expect(output).toContain("OMG Orchestration");
    expect(output).toContain("orch-test123");
    expect(output).toContain("ULTRAWORK");
    expect(output).toContain("RUNNING");
  });

  test("render() shows progress bar with correct counts", () => {
    const hud = HudState.create();
    hud.update(makeSnapshot({ tasksCompleted: 3, tasksTotal: 10 }));
    const output = hud.render();
    expect(output).toContain("3/10");
    expect(output).toContain("3 done");
  });

  test("render() shows failed and skipped counts when present", () => {
    const hud = HudState.create();
    hud.update(makeSnapshot({ tasksFailed: 2, tasksSkipped: 1 }));
    const output = hud.render();
    expect(output).toContain("2 failed");
    expect(output).toContain("1 skipped");
  });

  test("render() shows budget gauges", () => {
    const hud = HudState.create();
    hud.update(
      makeSnapshot({
        budgetPressure: { tokens: 0.5, wall_time_ms: 0.8, memory_mb: 0.95 },
      }),
    );
    const output = hud.render();
    expect(output).toContain("Tokens");
    expect(output).toContain("50%");
    expect(output).toContain("Wall Time");
    expect(output).toContain("80%");
    expect(output).toContain("Memory");
    expect(output).toContain("95%");
  });

  test("render() shows active agents in table", () => {
    const hud = HudState.create();
    hud.update(
      makeSnapshot({
        agents: [
          {
            agentId: "agent-abc123",
            taskId: "implement-auth",
            state: AgentState.RUNNING,
            category: "deep",
            prompt: "implement auth",
            startedAt: "2026-01-15T10:00:00Z",
            elapsedMs: 5_000,
          },
        ],
      }),
    );
    const output = hud.render();
    expect(output).toContain("agent-abc123");
    expect(output).toContain("implement-auth");
    expect(output).toContain("deep");
  });

  test("render() shows event log", () => {
    const hud = HudState.create();
    hud.update(
      makeSnapshot({
        events: [
          makeEvent("session_started", { mode: "ultrawork" }),
          makeEvent("agent_spawned", { taskId: "task-1", agentId: "a1" }),
        ],
      }),
    );
    const output = hud.render();
    expect(output).toContain("Recent Events");
    expect(output).toContain("session_started");
    expect(output).toContain("agent_spawned");
  });

  test("event log truncates to maxEventLines", () => {
    const hud = HudState.create({ maxEventLines: 3 });
    const manyEvents = Array.from({ length: 20 }, (_, i) =>
      makeEvent(`event_${i}`, { i }),
    );
    hud.update(makeSnapshot({ events: manyEvents }));
    const output = hud.render();

    const eventLines = output.split("\n").filter((l) => l.includes("event_"));
    expect(eventLines.length).toBeLessThanOrEqual(3);
  });

  test("budget gauge hides when showBudget is false", () => {
    const hud = HudState.create({ showBudget: false });
    hud.update(makeSnapshot());
    const output = hud.render();
    expect(output).not.toContain("Budget");
    expect(output).not.toContain("Tokens");
  });

  test("event log hides when showEvents is false", () => {
    const hud = HudState.create({ showEvents: false });
    hud.update(
      makeSnapshot({
        events: [makeEvent("test_event")],
      }),
    );
    const output = hud.render();
    expect(output).not.toContain("Recent Events");
  });

  test("pushEvent() adds events independently of snapshots", () => {
    const hud = HudState.create();
    hud.update(makeSnapshot());
    hud.pushEvent(makeEvent("custom_event", { data: "hello" }));
    const output = hud.render();
    expect(output).toContain("custom_event");
  });

  test("sequential mode renders correctly", () => {
    const hud = HudState.create();
    hud.update(makeSnapshot({ mode: "sequential" }));
    const output = hud.render();
    expect(output).toContain("SEQUENTIAL");
  });

  test("team mode renders correctly", () => {
    const hud = HudState.create();
    hud.update(makeSnapshot({ mode: "team" }));
    const output = hud.render();
    expect(output).toContain("TEAM");
  });

  test("completed status shows green", () => {
    const hud = HudState.create();
    hud.update(makeSnapshot({ status: "completed" }));
    const output = hud.render();
    expect(output).toContain("COMPLETED");
  });

  test("zero total tasks shows empty progress bar", () => {
    const hud = HudState.create();
    hud.update(makeSnapshot({ tasksTotal: 0, tasksCompleted: 0 }));
    const output = hud.render();
    expect(output).toContain("0/0");
  });
});
