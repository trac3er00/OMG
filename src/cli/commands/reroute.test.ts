import { describe, expect, it } from "bun:test";

import { autoReroute, runReroute, shouldReroute } from "./reroute.js";

async function captureStderr(run: () => Promise<void> | void): Promise<string> {
  const lines: string[] = [];
  const originalError = console.error;

  console.error = (...args: unknown[]) => {
    lines.push(args.map(String).join(" "));
  };

  try {
    await run();
  } finally {
    console.error = originalError;
  }

  return lines.join("\n");
}

describe("shouldReroute", () => {
  it("returns true for 39", () => {
    expect(shouldReroute(39)).toBe(true);
  });

  it("returns false for 40", () => {
    expect(shouldReroute(40)).toBe(false);
  });

  it("returns true for 0", () => {
    expect(shouldReroute(0)).toBe(true);
  });

  it("returns false for 100", () => {
    expect(shouldReroute(100)).toBe(false);
  });
});

describe("runReroute", () => {
  it("suggests reroute when ProofScore is below 40", async () => {
    const output = await captureStderr(() =>
      runReroute({ goal: "stabilize reroute flow", proofScore: 39 }),
    );

    expect(output).toContain("ProofScore 39/100 is below threshold (40)");
    expect(output).toContain(
      'Try: omg "stabilize reroute flow" with a different approach',
    );
  });
});

describe("autoReroute", () => {
  it("fails after three attempts when every retry stays below threshold", async () => {
    let calls = 0;

    const result = await autoReroute("recover proof", async () => {
      calls += 1;
      return 25;
    });

    expect(calls).toBe(3);
    expect(result).toEqual({
      attempts: 3,
      finalScore: 25,
      success: false,
    });
  });

  it("stops on the second attempt when a retry clears the threshold", async () => {
    let calls = 0;

    const result = await autoReroute("recover proof", async () => {
      calls += 1;
      return calls === 1 ? 35 : 72;
    });

    expect(calls).toBe(2);
    expect(result).toEqual({
      attempts: 2,
      finalScore: 72,
      success: true,
    });
  });

  it("returns success on the first attempt when the score already passes", async () => {
    let calls = 0;

    const result = await autoReroute("recover proof", async () => {
      calls += 1;
      return 88;
    });

    expect(calls).toBe(1);
    expect(result).toEqual({
      attempts: 1,
      finalScore: 88,
      success: true,
    });
  });
});
