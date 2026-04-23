import { describe, it, expect } from "bun:test";
import { getProofBand, DIMENSION_WEIGHTS } from "./types";

describe("getProofBand", () => {
  it("returns weak for score 0", () => {
    expect(getProofBand(0)).toBe("weak");
  });

  it("returns weak for score 39", () => {
    expect(getProofBand(39)).toBe("weak");
  });

  it("returns developing for score 40", () => {
    expect(getProofBand(40)).toBe("developing");
  });

  it("returns developing for score 69", () => {
    expect(getProofBand(69)).toBe("developing");
  });

  it("returns strong for score 70", () => {
    expect(getProofBand(70)).toBe("strong");
  });

  it("returns strong for score 89", () => {
    expect(getProofBand(89)).toBe("strong");
  });

  it("returns complete for score 90", () => {
    expect(getProofBand(90)).toBe("complete");
  });

  it("returns complete for score 100", () => {
    expect(getProofBand(100)).toBe("complete");
  });
});

describe("DIMENSION_WEIGHTS", () => {
  it("sums to 100", () => {
    const sum = Object.values(DIMENSION_WEIGHTS).reduce((a, b) => a + b, 0);
    expect(sum).toBe(100);
  });

  it("has entries for all 5 dimensions", () => {
    const dimensions = Object.keys(DIMENSION_WEIGHTS);
    expect(dimensions).toHaveLength(5);
    expect(dimensions).toContain("tests");
    expect(dimensions).toContain("lint");
    expect(dimensions).toContain("typecheck");
    expect(dimensions).toContain("coverage");
    expect(dimensions).toContain("uiDiff");
  });
});
