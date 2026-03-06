import { describe, expect, test } from "bun:test";
import { mkdtempSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ROOT_DIR, run } from "./helpers.ts";

describe("release package", () => {
  test("packed tarball installs through npm postinstall and includes plugin scripts", () => {
    const pack = run(["npm", "pack", "--ignore-scripts"], { cwd: ROOT_DIR });
    expect(pack.exitCode).toBe(0);

    const tarball = readdirSync(ROOT_DIR).find((name) => name.endsWith(".tgz"));
    expect(tarball).toBeTruthy();

    const probe = run(["tar", "-tvf", tarball!], { cwd: ROOT_DIR });
    expect(probe.stdout).toContain("package/.claude-plugin/scripts/install.sh");

    const installDir = mkdtempSync(join(tmpdir(), "omg-pack-"));
    run(["npm", "init", "-y"], { cwd: installDir });
    const install = run(["npm", "install", join(ROOT_DIR, tarball!)], { cwd: installDir });
    expect(install.exitCode).toBe(0);
  });
});
