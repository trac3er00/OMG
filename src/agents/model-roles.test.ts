import { describe, expect, test } from "bun:test";
import { getRole, loadModelRoles } from "./model-roles.js";

describe("model roles loader", () => {
  test("loads the configured role set", () => {
    const roles = loadModelRoles();

    expect(roles.default).toEqual({
      model: "claude-opus-4-5",
      temperature: 1,
      description: "Default balanced model for general tasks",
    });
    expect(roles.smol).toEqual({
      model: "claude-haiku-4-5",
      temperature: 0.7,
      description: "Fast cheap model for simple/trivial tasks",
    });
    expect(roles.plan).toEqual({
      model: "claude-sonnet-4-5",
      temperature: 0.8,
      description: "Planning and architecture model",
    });
  });

  test("getRole falls back to default role", () => {
    expect(getRole("default")).toEqual({
      model: "claude-opus-4-5",
      temperature: 1,
      description: "Default balanced model for general tasks",
    });

    expect(getRole("missing-role")).toEqual({
      model: "claude-opus-4-5",
      temperature: 1,
      description: "Default balanced model for general tasks",
    });
  });
});
