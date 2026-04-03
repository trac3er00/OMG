import { describe, expect, test } from "bun:test";
import { HudServer } from "./hud-server.js";
import { OrchestrationSession } from "./session.js";

function fixedDate(): Date {
  return new Date("2026-01-15T10:00:00Z");
}

describe("HudServer", () => {
  test("create() produces valid HudServer", () => {
    const session = OrchestrationSession.create({
      idGenerator: () => "hud-test-1",
      now: fixedDate,
    });
    const server = HudServer.create({ session });
    expect(server).toBeInstanceOf(HudServer);
    expect(server.hud).toBeDefined();
  });

  test("renderAnsi() returns HUD string after start()", () => {
    const session = OrchestrationSession.create({
      idGenerator: () => "hud-test-2",
      now: fixedDate,
      mode: "ultrawork",
    });
    const server = HudServer.create({ session });
    server.start();

    const output = server.renderAnsi();
    expect(output).toContain("OMG Orchestration");
    expect(output).toContain("hud-test-2");
    expect(output).toContain("ULTRAWORK");

    server.stop();
  });

  test("snapshotJson() returns structured JSON", () => {
    const session = OrchestrationSession.create({
      idGenerator: () => "hud-test-3",
      now: fixedDate,
      mode: "team",
    });
    const server = HudServer.create({ session });
    server.start();

    const json = server.snapshotJson();
    expect(json.sessionId).toBe("hud-test-3");
    expect(json.mode).toBe("team");
    expect(json.status).toBe("idle");
    expect(json.progress).toBeDefined();
    expect((json.progress as Record<string, number>).total).toBe(0);
    expect(json.budget).toBeDefined();
    expect(json.recentEvents).toBeDefined();

    server.stop();
  });

  test("stop() prevents further updates", () => {
    const session = OrchestrationSession.create({
      idGenerator: () => "hud-test-4",
      now: fixedDate,
    });
    const server = HudServer.create({ session, refreshIntervalMs: 50 });
    server.start();
    server.stop();
    server.stop();
    expect(server.renderAnsi()).toContain("OMG Orchestration");
  });
});
