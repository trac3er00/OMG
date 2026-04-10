import { describe, expect, test } from "bun:test";
import { SkepticCritic } from "./router-critics.js";

describe("SkepticCritic", () => {
  test("warns when the claim is empty", () => {
    const result = new SkepticCritic().evaluate("   ", ["artifact.txt"]);

    expect(result.verdict).toBe("warn");
    expect(result.reason).toContain("empty");
  });

  test("rejects unsupported confidence language", () => {
    const result = new SkepticCritic().evaluate("Trust me, it works", [
      "proof",
    ]);

    expect(result.verdict).toBe("reject");
    expect(result.reason).toContain("trust me");
  });

  test("accepts claims backed by non-empty evidence pointers", () => {
    const result = new SkepticCritic().evaluate("Tests passed", [
      "  junit.xml  ",
      "",
      " log.txt ",
    ]);

    expect(result.verdict).toBe("accept");
    expect(result.reason).toContain("2 evidence pointer");
  });
});
