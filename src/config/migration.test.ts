import { describe, expect, test } from "bun:test";
import {
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
  existsSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomBytes } from "node:crypto";
import { migrateConfig } from "./migration.js";

function makeProjectDir(): string {
  const dir = join(tmpdir(), `omg-migration-${randomBytes(6).toString("hex")}`);
  mkdirSync(dir, { recursive: true });
  return dir;
}

describe("migrateConfig v2.9.0 -> v3.0.0-rc", () => {
  test("dry-run reports required fields without mutating files", () => {
    const projectDir = makeProjectDir();
    const settingsPath = join(projectDir, "settings.json");
    const stateDir = join(projectDir, ".omg", "state");
    const mcpPath = join(projectDir, ".mcp.json");

    mkdirSync(stateDir, { recursive: true });
    writeFileSync(
      settingsPath,
      JSON.stringify({ _omg: { preset: "legacy" } }, null, 2) + "\n",
      "utf8",
    );
    writeFileSync(
      mcpPath,
      JSON.stringify({ mcpServers: {} }, null, 2) + "\n",
      "utf8",
    );
    writeFileSync(
      join(stateDir, "session_health.json"),
      JSON.stringify(
        { schema: "SessionHealth", schema_version: "1.0.0", status: "ok" },
        null,
        2,
      ) + "\n",
      "utf8",
    );

    const beforeSettings = readFileSync(settingsPath, "utf8");
    const beforeMcp = readFileSync(mcpPath, "utf8");

    const report = migrateConfig({
      from: "2.9.0",
      to: "3.0.0-rc",
      projectDir,
      dryRun: true,
      apply: false,
    });

    expect(Array.isArray(report.files_affected)).toBe(true);
    expect(typeof report.changes_required).toBe("object");
    expect(typeof report.rollback_path).toBe("string");
    expect(Array.isArray(report.errors)).toBe(true);
    expect(report.errors).toHaveLength(0);

    expect(report.files_affected).toContain("settings.json");
    expect(report.files_affected).toContain(".mcp.json");

    expect(readFileSync(settingsPath, "utf8")).toBe(beforeSettings);
    expect(readFileSync(mcpPath, "utf8")).toBe(beforeMcp);

    rmSync(projectDir, { recursive: true, force: true });
  });

  test("apply creates rollback backup and writes planned changes", () => {
    const projectDir = makeProjectDir();
    const settingsPath = join(projectDir, "settings.json");

    writeFileSync(
      settingsPath,
      JSON.stringify({ _omg: { preset: "legacy" } }, null, 2) + "\n",
      "utf8",
    );

    const report = migrateConfig({
      from: "2.9.0",
      to: "3.0.0-rc",
      projectDir,
      apply: true,
      dryRun: false,
    });

    expect(report.errors).toHaveLength(0);
    expect(existsSync(report.rollback_path)).toBe(true);
    expect(readFileSync(settingsPath, "utf8")).toContain(
      '"preset": "standard"',
    );

    rmSync(projectDir, { recursive: true, force: true });
  });
});
