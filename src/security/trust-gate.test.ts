import { describe, test, expect } from "bun:test";
import { applyTrustGate } from "./trust-gate.js";

describe("applyTrustGate", () => {
  test("research tier has zero trust score and warnings", () => {
    const result = applyTrustGate(
      "Web page content from external source",
      "research",
    );
    expect(result.warnings.length).toBeGreaterThan(0);
    expect(result.trustScore).toBe(0.0);
  });

  test("local tier passes with no warnings and full trust", () => {
    const result = applyTrustGate("Local file content", "local");
    expect(result.warnings.length).toBe(0);
    expect(result.trustScore).toBe(1.0);
  });

  test("browser tier has zero trust score", () => {
    const result = applyTrustGate("Browser DOM content", "browser");
    expect(result.trustScore).toBe(0.0);
    expect(result.warnings.length).toBeGreaterThan(0);
  });

  test("balanced tier has partial trust score", () => {
    const result = applyTrustGate("Tool output content", "balanced");
    expect(result.trustScore).toBe(0.7);
    expect(result.warnings.length).toBeGreaterThan(0);
  });

  test("invalid tier throws descriptive error", () => {
    expect(() => applyTrustGate("content", "invalid_tier")).toThrow(
      "Invalid trust tier",
    );
  });

  test("result includes content field", () => {
    const result = applyTrustGate("test content", "local");
    expect(result.content).toBe("test content");
  });
});
