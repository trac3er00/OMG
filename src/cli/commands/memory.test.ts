import { describe, expect, it } from "bun:test";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { runMemoryTierStatus } from "./memory";

function captureStdout(run: () => void): string {
  const lines: string[] = [];
  const originalLog = console.log;
  console.log = (...args: unknown[]) => {
    lines.push(args.map(String).join(" "));
  };

  try {
    run();
  } finally {
    console.log = originalLog;
  }

  return lines.join("\n");
}

function withTempStatusFile(payload: unknown, run: () => void): string {
  const originalCwd = process.cwd();
  const tempDir = mkdtempSync(join(tmpdir(), "memory-tier-status-"));
  mkdirSync(join(tempDir, ".omg", "state"), { recursive: true });
  writeFileSync(
    join(tempDir, ".omg", "state", "tier-status.json"),
    `${JSON.stringify(payload, null, 2)}\n`,
    "utf8",
  );

  try {
    process.chdir(tempDir);
    return captureStdout(run);
  } finally {
    process.chdir(originalCwd);
    rmSync(tempDir, { recursive: true, force: true });
  }
}

describe("runMemoryTierStatus", () => {
  it("shows all three tiers", () => {
    const output = withTempStatusFile(
      [
        {
          name: "auto",
          count: 3,
          size_bytes: 1536,
          last_promoted: "2026-04-07T10:00:00Z",
          last_demoted: null,
          item_values: ["secret-a"],
        },
        {
          name: "micro",
          count: 2,
          size_bytes: 2048,
          last_promoted: null,
          last_demoted: "2026-04-07T11:00:00Z",
          item_values: ["secret-b"],
        },
        {
          name: "ship",
          count: 1,
          size_bytes: 0,
          last_promoted: null,
          last_demoted: null,
          item_values: ["secret-c"],
        },
      ],
      () => runMemoryTierStatus(),
    );

    expect(output).toContain("CMMS Tier Status");
    expect(output).toContain("AUTO");
    expect(output).toContain("MICRO");
    expect(output).toContain("SHIP");
    expect(output).not.toContain("secret-a");
    expect(output).not.toContain("secret-b");
    expect(output).not.toContain("secret-c");
  });

  it("emits valid json", () => {
    const output = withTempStatusFile(
      {
        auto: {
          count: 1,
          size_bytes: 12,
          last_promoted: null,
          last_demoted: null,
        },
        micro: {
          count: 2,
          size_bytes: 34,
          last_promoted: null,
          last_demoted: null,
        },
        ship: {
          count: 3,
          size_bytes: 56,
          last_promoted: null,
          last_demoted: null,
        },
      },
      () => runMemoryTierStatus({ json: true }),
    );

    const parsed = JSON.parse(output) as Array<{
      name: string;
      count: number;
      size_bytes: number;
      last_promoted: string | null;
      last_demoted: string | null;
    }>;

    expect(Array.isArray(parsed)).toBe(true);
    expect(parsed).toHaveLength(3);
    expect(parsed.map((entry) => entry.name)).toEqual([
      "auto",
      "micro",
      "ship",
    ]);
    expect(parsed[0]).toMatchObject({ count: 1, size_bytes: 12 });
  });

  it("filters by tier", () => {
    const output = withTempStatusFile(
      [
        {
          name: "auto",
          count: 7,
          size_bytes: 100,
          last_promoted: null,
          last_demoted: null,
        },
        {
          name: "micro",
          count: 8,
          size_bytes: 200,
          last_promoted: null,
          last_demoted: null,
        },
        {
          name: "ship",
          count: 9,
          size_bytes: 300,
          last_promoted: null,
          last_demoted: null,
        },
      ],
      () => runMemoryTierStatus({ tier: "auto" }),
    );

    expect(output).toContain("AUTO");
    expect(output).not.toContain("MICRO");
    expect(output).not.toContain("SHIP");
  });
});
