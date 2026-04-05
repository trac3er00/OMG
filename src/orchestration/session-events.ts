import type { EventEmitter } from "node:events";

export interface SessionEvent {
  readonly type: string;
  readonly timestamp: string;
  readonly sessionId: string;
  readonly payload: Readonly<Record<string, unknown>>;
}

export function emitSessionEvent(params: {
  readonly emitter: EventEmitter;
  readonly type: string;
  readonly payload: Record<string, unknown>;
  readonly sessionId: string;
  readonly now: () => Date;
  readonly events: SessionEvent[];
  readonly maxEvents: number;
}): SessionEvent {
  const event: SessionEvent = {
    type: params.type,
    timestamp: params.now().toISOString(),
    sessionId: params.sessionId,
    payload: params.payload,
  };

  params.events.push(event);
  if (params.events.length > params.maxEvents) {
    params.events.splice(0, params.events.length - params.maxEvents);
  }

  params.emitter.emit(params.type, event);
  params.emitter.emit("event", event);
  return event;
}

export function latestSessionEvents(
  events: readonly SessionEvent[],
  count: number,
): readonly SessionEvent[] {
  return events.slice(-Math.max(0, count));
}
