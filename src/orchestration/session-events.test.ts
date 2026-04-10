import { EventEmitter } from "node:events";
import { describe, expect, test } from "bun:test";
import type { SessionEvent } from "./session-events.js";
import { emitSessionEvent, latestSessionEvents } from "./session-events.js";

describe("session-events", () => {
  test("emitSessionEvent records and emits the event", () => {
    const emitter = new EventEmitter();
    const retainedEvents: SessionEvent[] = [];
    const taskRegisteredEvents: SessionEvent[] = [];
    const allEvents: SessionEvent[] = [];

    emitter.on("task_registered", (event) => taskRegisteredEvents.push(event));
    emitter.on("event", (event) => allEvents.push(event));

    const event = emitSessionEvent({
      emitter,
      type: "task_registered",
      payload: { taskId: "task-1" },
      sessionId: "session-1",
      now: () => new Date("2026-04-10T12:00:00.000Z"),
      events: retainedEvents,
      maxEvents: 2,
    });

    expect(event.type).toBe("task_registered");
    expect(retainedEvents).toHaveLength(1);
    expect(taskRegisteredEvents).toHaveLength(1);
    expect(allEvents).toHaveLength(1);
    expect(retainedEvents[0]).toEqual(allEvents[0]);
  });

  test("emitSessionEvent trims retained history to maxEvents", () => {
    const emitter = new EventEmitter();
    const events: SessionEvent[] = [];

    emitSessionEvent({
      emitter,
      type: "first",
      payload: {},
      sessionId: "session-1",
      now: () => new Date("2026-04-10T12:00:00.000Z"),
      events,
      maxEvents: 2,
    });
    emitSessionEvent({
      emitter,
      type: "second",
      payload: {},
      sessionId: "session-1",
      now: () => new Date("2026-04-10T12:00:01.000Z"),
      events,
      maxEvents: 2,
    });
    emitSessionEvent({
      emitter,
      type: "third",
      payload: {},
      sessionId: "session-1",
      now: () => new Date("2026-04-10T12:00:02.000Z"),
      events,
      maxEvents: 2,
    });

    expect(events.map((event) => event.type)).toEqual(["second", "third"]);
  });

  test("latestSessionEvents returns the latest requested window", () => {
    const events = [
      { type: "a", timestamp: "1", sessionId: "s", payload: {} },
      { type: "b", timestamp: "2", sessionId: "s", payload: {} },
      { type: "c", timestamp: "3", sessionId: "s", payload: {} },
    ];

    expect(latestSessionEvents(events, 2).map((event) => event.type)).toEqual([
      "b",
      "c",
    ]);
    expect(latestSessionEvents(events, 0)).toEqual(events);
  });
});
