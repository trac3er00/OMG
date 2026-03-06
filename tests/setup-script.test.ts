import { describe, expect, test } from "bun:test";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT_DIR, run, tempDir } from "./helpers.ts";

describe("setup script", () => {
  test("help lists Bun-oriented subcommands", () => {
    const proc = run(["bash", "OMG-setup.sh", "--help"]);
    const out = proc.stdout.toString() + proc.stderr.toString();
    expect(proc.exitCode).toBe(0);
    expect(out).toContain("install");
    expect(out).toContain("--install-as-plugin");
  });

  test("install dry-run is non-mutating", () => {
    const dir = tempDir("omg-setup-dry-");
    const proc = run(["bash", "OMG-setup.sh", "install", "--dry-run", "--non-interactive"], {
      env: { CLAUDE_CONFIG_DIR: join(dir, ".claude") }
    });
    expect(proc.exitCode).toBe(0);
    expect(proc.stdout.toString() + proc.stderr.toString()).toContain("DRY RUN");
  });

  test("install writes Bun runtime files and uninstall removes them", () => {
    const dir = tempDir("omg-setup-");
    const claudeDir = join(dir, ".claude");
    const settingsPath = join(claudeDir, "settings.json");
    mkdirSync(claudeDir, { recursive: true });
    Bun.write(settingsPath, JSON.stringify({ permissions: { allow: ["Read"], ask: [], deny: [] }, hooks: {} }, null, 2));

    const install = run(["bash", "OMG-setup.sh", "install", "--non-interactive", "--merge-policy=apply"], {
      env: { CLAUDE_CONFIG_DIR: claudeDir }
    });
    expect(install.exitCode).toBe(0);
    expect(existsSync(join(claudeDir, "omg-runtime", "scripts", "omg.ts"))).toBe(true);
    expect(existsSync(join(claudeDir, "hooks", "circuit-breaker.ts"))).toBe(true);
    const mergedSettings = JSON.parse(readFileSync(settingsPath, "utf8"));
    expect(JSON.stringify(mergedSettings)).toContain("session-end-capture.ts");

    const uninstall = run(["bash", "OMG-setup.sh", "uninstall", "--non-interactive"], {
      env: { CLAUDE_CONFIG_DIR: claudeDir }
    });
    expect(uninstall.exitCode).toBe(0);
    expect(existsSync(join(claudeDir, "omg-runtime"))).toBe(false);
  });

  test("plugin install writes bundle marker", () => {
    const dir = tempDir("omg-plugin-");
    const claudeDir = join(dir, ".claude");
    const proc = run(["bash", "OMG-setup.sh", "install", "--install-as-plugin", "--non-interactive", "--merge-policy=skip"], {
      env: { CLAUDE_CONFIG_DIR: claudeDir }
    });
    expect(proc.exitCode).toBe(0);
    expect(existsSync(join(claudeDir, "plugins", "cache", "oh-advanced-layer", "omg", ".omg-plugin-bundle"))).toBe(true);
  });

  test("deprecated install wrapper forwards help", () => {
    const proc = run(["bash", "install.sh", "--help"], { cwd: ROOT_DIR });
    const out = proc.stdout.toString() + proc.stderr.toString();
    expect(proc.exitCode).toBe(0);
    expect(out.toLowerCase()).toContain("deprecated");
    expect(out).toContain("OMG-setup.sh");
  });
});
