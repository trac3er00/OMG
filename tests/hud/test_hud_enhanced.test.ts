import { describe, it, expect } from "bun:test";

describe("HUD Enhanced", () => {
  it("formatStatusLine with no events returns idle", async () => {
    const { formatStatusLine } = await import("../../hud/omg-hud-enhanced.mjs");
    expect(formatStatusLine([])).toBe("[OMG: idle]");
  });

  it("formatStatusLine with agent_start shows agent count", async () => {
    const { formatStatusLine } = await import("../../hud/omg-hud-enhanced.mjs");
    const events = [
      {
        type: "agent_start",
        data: { agent_id: "a1", task: "explore" },
        timestamp: Date.now(),
      },
    ];
    const result = formatStatusLine(events);
    expect(result).toContain("1 agents");
  });

  it("formatStatusLine with agent_start and agent_stop removes agent", async () => {
    const { formatStatusLine } = await import("../../hud/omg-hud-enhanced.mjs");
    const events = [
      {
        type: "agent_start",
        data: { agent_id: "a1", task: "explore" },
        timestamp: Date.now(),
      },
      {
        type: "agent_stop",
        data: { agent_id: "a1", result: "done" },
        timestamp: Date.now(),
      },
    ];
    const result = formatStatusLine(events);
    expect(result).toBe("[OMG: idle]");
  });

  it("formatStatusLine with multiple agents shows correct count", async () => {
    const { formatStatusLine } = await import("../../hud/omg-hud-enhanced.mjs");
    const events = [
      {
        type: "agent_start",
        data: { agent_id: "a1", task: "explore" },
        timestamp: Date.now(),
      },
      {
        type: "agent_start",
        data: { agent_id: "a2", task: "build" },
        timestamp: Date.now(),
      },
    ];
    const result = formatStatusLine(events);
    expect(result).toContain("2 agents");
  });

  it("formatStatusLine with cost_update shows cost", async () => {
    const { formatStatusLine } = await import("../../hud/omg-hud-enhanced.mjs");
    const events = [
      {
        type: "cost_update",
        data: { tokens: 1000, usd: 0.05, budget_remaining_pct: 80 },
        timestamp: Date.now(),
      },
    ];
    const result = formatStatusLine(events);
    expect(result).toContain("$0.050");
  });

  it("formatStatusLine with phase_change shows phase", async () => {
    const { formatStatusLine } = await import("../../hud/omg-hud-enhanced.mjs");
    const events = [
      {
        type: "phase_change",
        data: { phase: "planning", detail: "" },
        timestamp: Date.now(),
      },
    ];
    const result = formatStatusLine(events);
    expect(result).toContain("planning");
  });

  it("formatStatusLine with all event types shows combined output", async () => {
    const { formatStatusLine } = await import("../../hud/omg-hud-enhanced.mjs");
    const events = [
      {
        type: "agent_start",
        data: { agent_id: "a1", task: "explore" },
        timestamp: Date.now(),
      },
      {
        type: "cost_update",
        data: { tokens: 5000, usd: 0.123, budget_remaining_pct: 50 },
        timestamp: Date.now(),
      },
      {
        type: "phase_change",
        data: { phase: "execution", detail: "step 2" },
        timestamp: Date.now(),
      },
    ];
    const result = formatStatusLine(events);
    expect(result).toContain("1 agents");
    expect(result).toContain("$0.123");
    expect(result).toContain("execution");
    expect(result).toStartWith("[OMG: ");
    expect(result).toEndWith("]");
  });

  it("readEvents returns empty array when file missing", async () => {
    const { readEvents } = await import("../../hud/omg-hud-enhanced.mjs");
    const events = readEvents();
    expect(Array.isArray(events)).toBe(true);
  });
});
