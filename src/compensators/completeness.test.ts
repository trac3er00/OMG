import { describe, expect, it } from "bun:test";

import {
  checkChecklistCompleteness,
  checkReadCompleteness,
  detectCourtesyCut,
} from "./completeness";

describe("checkReadCompleteness", () => {
  it("returns 100% and no detection when totalLines is 0", () => {
    const result = checkReadCompleteness(0, 0);

    expect(result.detected).toBe(false);
    expect(result.coveragePercent).toBe(100);
    expect(result.warningMessage).toBeUndefined();
  });

  it("does not detect when coverage is exactly 80%", () => {
    const result = checkReadCompleteness(10, 8);

    expect(result.detected).toBe(false);
    expect(result.coveragePercent).toBe(80);
    expect(result.warningMessage).toBeUndefined();
  });

  it("detects and formats warning when coverage is below 80%", () => {
    const result = checkReadCompleteness(10, 7);

    expect(result.detected).toBe(true);
    expect(result.coveragePercent).toBe(70);
    expect(result.warningMessage).toBe(
      "Only 70.0% of file read (7/10 lines). Read the complete file before making changes.",
    );
  });
});

describe("detectCourtesyCut", () => {
  it("does not detect when no truncation patterns are present", () => {
    const output = "All 42 records displayed with full details.";
    const result = detectCourtesyCut(output);

    expect(result.detected).toBe(false);
    expect(result.truncationPatterns).toEqual([]);
    expect(result.warningMessage).toBeUndefined();
  });

  it("detects a single truncation pattern", () => {
    const output = "Showing first 50 lines";
    const result = detectCourtesyCut(output);

    expect(result.detected).toBe(true);
    expect(result.truncationPatterns).toHaveLength(1);
    expect(result.warningMessage).toBe(
      "Output truncation detected (1 pattern(s)). Provide complete output or get explicit user consent for truncation.",
    );
  });

  it("detects multiple truncation patterns in one output", () => {
    const output = "Truncated for brevity... and 20 more";
    const result = detectCourtesyCut(output);

    expect(result.detected).toBe(true);
    expect(result.truncationPatterns).toHaveLength(2);
    expect(result.warningMessage).toContain("2 pattern(s)");
  });

  it("matches patterns case-insensitively", () => {
    const output = "See FULL OUTPUT for details";
    const result = detectCourtesyCut(output);

    expect(result.detected).toBe(true);
    expect(result.truncationPatterns).toHaveLength(1);
  });
});

describe("checkChecklistCompleteness", () => {
  it("returns complete when totalItems is 0", () => {
    const result = checkChecklistCompleteness(0, 0);

    expect(result.detected).toBe(false);
    expect(result.coveragePercent).toBe(100);
    expect(result.warningMessage).toBeUndefined();
  });

  it("detects incomplete checklist and includes warning", () => {
    const result = checkChecklistCompleteness(5, 4);

    expect(result.detected).toBe(true);
    expect(result.coveragePercent).toBe(80);
    expect(result.warningMessage).toBe(
      "Only 4/5 checklist items verified (80.0%). All items must be verified.",
    );
  });

  it("does not detect when all items are checked", () => {
    const result = checkChecklistCompleteness(5, 5);

    expect(result.detected).toBe(false);
    expect(result.coveragePercent).toBe(100);
    expect(result.warningMessage).toBeUndefined();
  });
});
