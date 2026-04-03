import { describe, test, expect } from "bun:test";
import {
  DOMAIN_PROFILES,
  getDomainProfile,
  getVerificationTool,
  DomainAgentProfileSchema,
} from "./adapters.js";

describe("domains/adapters", () => {
  test("web_app profile uses playwright", () => {
    const profile = getDomainProfile("web_app");
    expect(profile?.harness_layer3_tool).toBe("playwright");
    expect(profile?.agent_category).toBe("visual-engineering");
  });

  test("cli_tool profile uses tmux", () => {
    const profile = getDomainProfile("cli_tool");
    expect(profile?.harness_layer3_tool).toBe("tmux");
  });

  test("backend_api profile uses curl", () => {
    const profile = getDomainProfile("backend_api");
    expect(profile?.harness_layer3_tool).toBe("curl");
  });

  test("unknown domain returns null", () => {
    expect(getDomainProfile("unknown")).toBeNull();
  });

  test("all domain profiles validate against schema", () => {
    for (const profile of Object.values(DOMAIN_PROFILES)) {
      expect(DomainAgentProfileSchema.safeParse(profile).success).toBe(true);
    }
  });

  test("getVerificationTool returns tool for known domain", () => {
    expect(getVerificationTool("web_app")).toBe("playwright");
    expect(getVerificationTool("cli_tool")).toBe("tmux");
    expect(getVerificationTool("backend_api")).toBe("curl");
  });

  test("getVerificationTool returns curl for unknown domain", () => {
    expect(getVerificationTool("unknown")).toBe("curl");
  });

  test("each profile has verification commands", () => {
    for (const profile of Object.values(DOMAIN_PROFILES)) {
      expect(profile.verification_commands.length).toBeGreaterThan(0);
    }
  });
});
