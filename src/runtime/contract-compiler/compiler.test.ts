import { describe, expect, test } from "bun:test";
import { compileContract, emitForHost, validateContract, validateSchema, type ContractSchema } from "./index.js";

const VALID_SCHEMA: ContractSchema = {
  version: "3.0.0",
  capabilities: [
    "compilation_targets",
    "hooks",
    "subagents",
    "skills",
    "agents_fragments",
    "rules",
    "automations",
    "mcp",
  ],
  hosts: ["claude", "codex", "gemini", "kimi"],
  tools: {
    "control-plane": {
      description: "Canonical control-plane skill",
      hosts: ["codex", "claude"],
    },
  },
};

function asRecord(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null) {
    throw new Error("Expected object payload");
  }
  return value as Record<string, unknown>;
}

describe("contract compiler schema + validation", () => {
  test("validateSchema accepts a valid contract schema", () => {
    const result = validateSchema(VALID_SCHEMA);
    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  test("validateContract checks required capabilities", () => {
    const invalid: ContractSchema = {
      ...VALID_SCHEMA,
      capabilities: ["skills"],
    };
    const result = validateContract(invalid);
    expect(result.valid).toBe(false);
    expect(result.blockers.some((blocker) => blocker.includes("compilation_targets"))).toBe(true);
  });
});

describe("host emission", () => {
  test("compile for Claude emits valid .claude-plugin/mcp.json format", () => {
    const artifact = emitForHost(VALID_SCHEMA, "claude");
    expect(artifact.targetPath).toBe(".claude-plugin/mcp.json");
    const payload = asRecord(artifact.payload);
    const mcpServers = asRecord(payload.mcpServers);
    const omgControl = asRecord(mcpServers["omg-control"]);
    expect(omgControl.command).toBe("bun");
    expect(Array.isArray(omgControl.args)).toBe(true);
  });

  test("compile for Codex emits valid .agents/skills/omg/ directory format", () => {
    const artifact = emitForHost(VALID_SCHEMA, "codex");
    expect(artifact.targetPath).toBe(".agents/skills/omg/");

    const payload = asRecord(artifact.payload);
    const files = asRecord(payload.files);
    expect(typeof files["AGENTS.fragment.md"]).toBe("string");
    expect(typeof files["codex-rules.md"]).toBe("string");
    expect(typeof files["control-plane/SKILL.md"]).toBe("string");
    expect(typeof files["control-plane/openai.yaml"]).toBe("string");
  });
});

describe("compileContract", () => {
  test("compiles selected hosts after validation", () => {
    const result = compileContract(VALID_SCHEMA, ["claude", "codex"]);
    expect(result.valid).toBe(true);
    expect(result.blockers).toHaveLength(0);
    expect(result.artifacts).toHaveLength(2);
    expect(result.artifacts.map((artifact) => artifact.host)).toEqual(["claude", "codex"]);
  });
});
