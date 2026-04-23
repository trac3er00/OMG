import { describe, expect, it } from "bun:test";

import { classify } from "./index.js";
import { isClassificationResult } from "./types.js";

describe("classify", () => {
  it("classifies a landing page request as low-risk build work", () => {
    const result = classify("make a landing page");

    expect(isClassificationResult(result)).toBe(true);
    expect(result.intent).toBe("build");
    expect(result.risk).toBe("low");
    expect(result.complexity).toBe("simple");
    expect(result.confidence).toBeGreaterThanOrEqual(0.8);
    expect(result.signals).toContain("intent:build");
    expect(result.signals).toContain("risk:low:landing page");
    expect(result.signals).toContain("complexity:simple:landing page");
  });

  it("classifies refactor auth module as refactor intent with high risk", () => {
    const result = classify("refactor auth module");

    expect(result.intent).toBe("refactor");
    expect(result.risk).toBe("high");
    expect(result.complexity).toBe("moderate");
    expect(result.confidence).toBe(0.9);
    expect(result.signals).toContain("intent:refactor");
    expect(result.signals).toContain("risk:high:auth");
    expect(result.signals).toContain("complexity:moderate:module");
  });

  it("classifies delete all user data as critical expert-level modification", () => {
    const result = classify("delete all user data");

    expect(result.intent).toBe("modify");
    expect(result.risk).toBe("critical");
    expect(result.complexity).toBe("expert");
    expect(result.confidence).toBe(0.9);
    expect(result.signals).toContain("risk:critical:delete");
    expect(result.signals).toContain("risk:high:all users");
    expect(result.signals).toContain("complexity:expert:all");
  });

  it("classifies production deployment as high-risk deployment work", () => {
    const result = classify("deploy to production");

    expect(result.intent).toBe("deploy");
    expect(result.risk).toBe("high");
    expect(result.complexity).toBe("moderate");
    expect(result.confidence).toBe(0.8);
    expect(result.signals).toContain("intent:deploy");
    expect(result.signals).toContain("risk:high:production");
  });

  it("classifies bug investigation as low-risk investigation work", () => {
    const result = classify("investigate the bug");

    expect(result.intent).toBe("investigate");
    expect(result.risk).toBe("low");
    expect(result.complexity).toBe("simple");
    expect(result.confidence).toBe(0.7);
    expect(result.signals).toContain("intent:investigate");
  });

  it("classifies API security work as secure intent with high risk", () => {
    const result = classify("secure the API endpoints");

    expect(result.intent).toBe("secure");
    expect(result.risk).toBe("high");
    expect(result.complexity).toBe("moderate");
    expect(result.confidence).toBe(0.9);
    expect(result.signals).toContain("intent:secure");
    expect(result.signals).toContain("risk:high:api");
    expect(result.signals).toContain("complexity:moderate:endpoints");
  });

  it("returns defaults for an empty goal", () => {
    const result = classify("");

    expect(result.intent).toBe("build");
    expect(result.risk).toBe("low");
    expect(result.complexity).toBe("simple");
    expect(result.confidence).toBe(0.6);
    expect(result.signals).toEqual([]);
  });
});
