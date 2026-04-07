#!/usr/bin/env node
/**
 * OMG Enhanced HUD — Real-time observability statusline.
 *
 * Reads JSONL events emitted by runtime/hud_emitter.py and formats
 * a compact terminal statusline showing active agents, cost, and phase.
 */

import { readFileSync, existsSync } from "fs";

const HUD_EVENTS_PATH = ".omg/state/hud-events.jsonl";

/**
 * Read all HUD events from the JSONL file.
 * Returns an empty array if the file is missing or unreadable.
 */
export function readEvents() {
  if (!existsSync(HUD_EVENTS_PATH)) return [];
  try {
    return readFileSync(HUD_EVENTS_PATH, "utf8")
      .split("\n")
      .filter(Boolean)
      .map((line) => JSON.parse(line));
  } catch {
    return [];
  }
}

/**
 * Format a statusline string from an array of HUD events.
 * Pure function — no file I/O, easy to test.
 */
export function formatStatusLine(events) {
  const agents = new Set();
  let totalTokens = 0;
  let totalUsd = 0;
  let currentPhase = "";

  for (const event of events) {
    if (event.type === "agent_start") agents.add(event.data.agent_id);
    if (event.type === "agent_stop") agents.delete(event.data.agent_id);
    if (event.type === "cost_update") {
      totalTokens = event.data.tokens;
      totalUsd = event.data.usd;
    }
    if (event.type === "phase_change") currentPhase = event.data.phase;
  }

  const agentCount = agents.size;
  const parts = [];
  if (agentCount > 0) parts.push(`\u{1F916} ${agentCount} agents`);
  if (totalUsd > 0) parts.push(`\u{1F4B0} $${totalUsd.toFixed(3)}`);
  if (currentPhase) parts.push(`\u{1F4CD} ${currentPhase}`);

  return parts.length > 0 ? `[OMG: ${parts.join(" | ")}]` : "[OMG: idle]";
}

// CLI mode: print statusline when run directly
const scriptUrl = import.meta.url;
if (
  scriptUrl &&
  process.argv[1] &&
  scriptUrl.endsWith(process.argv[1].replace(/.*\//, ""))
) {
  const events = readEvents();
  console.log(formatStatusLine(events));
}
