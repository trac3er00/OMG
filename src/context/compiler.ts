import type { HostType } from "../types/config.js";
import type { ContextPacket } from "./engine.js";

function toCodexFragment(packet: ContextPacket): string {
  const pointers =
    packet.provenance_pointers.length > 0
      ? packet.provenance_pointers.map((pointer) => `- ${pointer}`).join("\n")
      : "- (none)";

  return [
    "# OMG Context Packet",
    "",
    `- run_id: ${packet.run_id}`,
    `- packet_version: ${packet.packet_version}`,
    `- delta_only: ${String(packet.delta_only)}`,
    "",
    "## Summary",
    packet.summary,
    "",
    "## Provenance Pointers",
    pointers,
  ].join("\n");
}

function toClaudeText(packet: ContextPacket): string {
  return [
    "<omg_context_packet>",
    `  <run_id>${packet.run_id}</run_id>`,
    `  <packet_version>${packet.packet_version}</packet_version>`,
    `  <delta_only>${String(packet.delta_only)}</delta_only>`,
    `  <summary>${packet.summary}</summary>`,
    "</omg_context_packet>",
  ].join("\n");
}

function toGenericJson(hostType: HostType, packet: ContextPacket): string {
  return JSON.stringify({ host: hostType, packet }, null, 2);
}

export function compileContextForHost(
  packet: ContextPacket,
  hostType: HostType,
): string {
  switch (hostType) {
    case "codex":
      return toCodexFragment(packet);
    case "claude":
      return toClaudeText(packet);
    case "gemini":
    case "kimi":
    case "ollama":
    case "opencode":
      return toGenericJson(hostType, packet);
  }
}
