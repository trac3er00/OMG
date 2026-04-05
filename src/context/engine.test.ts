import { describe, expect, test } from "bun:test";
import { rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { ContextEngine } from "./engine.js";
import { getContextLimit } from "./limits.js";

describe("ContextEngine.buildPacket", () => {
  test("returns packet with all required fields", () => {
    const dir = join(tmpdir(), `ctx-test-${Date.now()}`);
    const engine = new ContextEngine(dir);
    const packet = engine.buildPacket("omg-run-001");

    expect(typeof packet.packet_version).toBe("string");
    expect(packet.packet_version.length).toBeGreaterThan(0);
    expect(typeof packet.summary).toBe("string");
    expect(Array.isArray(packet.artifact_pointers)).toBe(true);
    expect(Array.isArray(packet.provenance_pointers)).toBe(true);
    expect(Array.isArray(packet.artifact_handles)).toBe(true);
    expect(typeof packet.clarification_status).toBe("object");
    expect(typeof packet.ambiguity_state).toBe("object");
    expect(typeof packet.provenance_only).toBe("boolean");
    expect(typeof packet.governance).toBe("object");
    expect(typeof packet.release_metadata).toBe("object");
    expect(typeof packet.coordinator_run_id).toBe("string");
    expect(typeof packet.profile_digest).toBe("object");
    expect(typeof packet.budget).toBe("object");
    expect(typeof packet.deterministic_contract).toBe("object");
    expect(packet.run_id).toBe("omg-run-001");
    expect(typeof packet.delta_only).toBe("boolean");

    rmSync(dir, { recursive: true, force: true });
  });

  test("packet version is non-empty string", () => {
    const dir = join(tmpdir(), `ctx-test2-${Date.now()}`);
    const engine = new ContextEngine(dir);
    const packet = engine.buildPacket("test-run");
    expect(packet.packet_version.length).toBeGreaterThan(0);
    rmSync(dir, { recursive: true, force: true });
  });
});

describe("Context limits", () => {
  test("Claude 4.6 context = 1M tokens", () => {
    const limit = getContextLimit("claude-sonnet-4-6");
    expect(limit.context_tokens).toBe(1_000_000);
  });

  test("Claude 3.5 Sonnet has context window", () => {
    const limit = getContextLimit("claude-3-5-sonnet");
    expect(limit.context_tokens).toBeGreaterThan(0);
  });

  test("GPT-4 has context window", () => {
    const limit = getContextLimit("gpt-4");
    expect(limit.context_tokens).toBeGreaterThan(0);
  });

  test("unknown model returns default", () => {
    const limit = getContextLimit("unknown-model-xyz");
    expect(limit.context_tokens).toBeGreaterThan(0);
  });
});
