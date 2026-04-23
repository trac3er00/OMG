import { describe, expect, test } from "bun:test";
import { formatResult, formatResultHuman, printResult, type WowResult } from "./output.js";

describe("formatResult", () => {
  test("returns structured object with all fields", () => {
    const result: WowResult = {
      url: "https://example.com",
      screenshot: "/path/to/screenshot.png",
      proofScore: 95,
      buildTime: 1234,
      flowName: "test-flow",
      success: true,
    };

    const formatted = formatResult(result);

    expect(formatted).toEqual(result);
    expect(formatted.url).toBe("https://example.com");
    expect(formatted.proofScore).toBe(95);
    expect(formatted.buildTime).toBe(1234);
    expect(formatted.flowName).toBe("test-flow");
    expect(formatted.success).toBe(true);
  });

  test("returns independent copy (not same reference)", () => {
    const result: WowResult = {
      flowName: "test",
      success: true,
    };

    const formatted = formatResult(result);
    expect(formatted).not.toBe(result);
  });
});

describe("formatResultHuman", () => {
  test("with URL shows URL in first 3 lines", () => {
    const result: WowResult = {
      url: "https://example.com/deploy",
      screenshot: "/path/to/screenshot.png",
      proofScore: 85,
      buildTime: 2500,
      flowName: "deploy-flow",
      success: true,
    };

    const output = formatResultHuman(result);
    const lines = output.split("\n");

    expect(lines.length).toBeGreaterThanOrEqual(3);
    expect(lines[0]).toContain("https://example.com/deploy");
    expect(lines[0]).toContain("✅");
  });

  test("with success=false shows error", () => {
    const result: WowResult = {
      flowName: "fail-flow",
      success: false,
      error: "Build failed: missing dependency",
    };

    const output = formatResultHuman(result);

    expect(output).toContain("❌");
    expect(output).toContain("Build failed: missing dependency");
  });

  test("with success=false and no error shows Unknown error", () => {
    const result: WowResult = {
      flowName: "fail-flow",
      success: false,
    };

    const output = formatResultHuman(result);

    expect(output).toContain("❌");
    expect(output).toContain("Unknown error");
  });
});

describe("printResult", () => {
  test("with json=true outputs valid JSON", () => {
    const result: WowResult = {
      url: "https://example.com",
      proofScore: 90,
      flowName: "json-test",
      success: true,
    };

    let output = "";
    const originalLog = console.log;
    console.log = (msg: string) => { output = msg; };

    printResult(result, true);

    console.log = originalLog;

    const parsed = JSON.parse(output);
    expect(parsed.url).toBe("https://example.com");
    expect(parsed.proofScore).toBe(90);
    expect(parsed.flowName).toBe("json-test");
    expect(parsed.success).toBe(true);
  });

  test("with json=false outputs human-readable format", () => {
    const result: WowResult = {
      url: "https://example.com",
      flowName: "human-test",
      success: true,
    };

    let output = "";
    const originalLog = console.log;
    console.log = (msg: string) => { output = msg; };

    printResult(result, false);

    console.log = originalLog;

    expect(output).toContain("✅");
    expect(output).toContain("Deployed:");
    expect(output).toContain("https://example.com");
  });
});