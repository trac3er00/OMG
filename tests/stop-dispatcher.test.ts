import { describe, expect, test } from "bun:test";
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import {
  checkDiffBudget,
  checkFalseFix,
  checkRecentFailures,
  checkSimplifier,
  checkTestExecution,
  checkTestValidatorCoverage,
  checkVerification,
  checkWriteFailures
} from "../hooks/stop_dispatcher.ts";
import { run, tempDir } from "./helpers.ts";

function baseData(): any {
  return {
    _stop_ctx: {
      recent_entries: [],
      recent_commands: [],
      has_source_writes: false,
      has_material_writes: false
    },
    _stop_advisories: []
  };
}

describe("stop dispatcher", () => {
  test("blocks when source writes happen without verification", () => {
    const data = baseData();
    data._stop_ctx.has_source_writes = true;
    expect(checkVerification(data)).toEqual(["NO verification commands were executed after source writes."]);
  });

  test("blocks when last three commands all failed", () => {
    const data = baseData();
    data._stop_ctx.recent_entries = [
      { tool: "Bash", command: "one", exit_code: 1 },
      { tool: "Bash", command: "two", exit_code: 2 },
      { tool: "Bash", command: "three", exit_code: 3 }
    ];
    expect(checkRecentFailures(data)[0]).toContain("Last 3 commands ALL FAILED");
  });

  test("checks test execution and source/test pairing", () => {
    const data = baseData();
    data._stop_ctx.has_material_writes = true;
    data._stop_ctx.has_source_writes = true;
    data._changed_files = ["tests/auth.test.ts"];
    data._has_test = false;
    expect(checkTestExecution(data)[0]).toContain("test suite was never executed");

    data._changed_files = ["src/auth/service.ts"];
    expect(checkTestValidatorCoverage(data)[0]).toContain("TEST-VALIDATOR");

    data._changed_files = ["src/auth/service.ts", "tests/auth.test.ts"];
    expect(checkTestValidatorCoverage(data)).toEqual([]);
  });

  test("detects false fixes and write failures", () => {
    const data = baseData();
    data._stop_ctx.has_material_writes = true;
    data._changed_files = ["tests/auth.test.ts", "scripts/release.sh"];
    expect(checkFalseFix(data)[0]).toContain("FALSE FIX DETECTED");

    data._stop_ctx.recent_entries = [{ tool: "Write", file: "src/bad.ts", success: false }];
    expect(checkWriteFailures(data)[0]).toContain("src/bad.ts");
  });

  test("emits simplifier advisory and diff budget block", () => {
    const dir = tempDir("omg-stop-");
    const sloppy = join(dir, "sloppy.ts");
    writeFileSync(sloppy, "// a\n// b\n// c\n// d\nx = 1;\ny = 2;\n");
    const data = baseData();
    data._stop_ctx.source_write_entries = [{ tool: "Write", file: sloppy }];
    const advisory = run(["bun", "-e", `import { checkSimplifier } from './hooks/stop_dispatcher.ts'; checkSimplifier(${JSON.stringify(data)});`], {
      cwd: join(import.meta.dir, "..")
    });
    expect(advisory.stderr.toString()).toContain("@simplifier");
    expect(checkSimplifier(data)).toEqual([]);

    run(["git", "init"], { cwd: dir });
    run(["git", "config", "user.email", "omg@example.com"], { cwd: dir });
    run(["git", "config", "user.name", "OMG"], { cwd: dir });
    writeFileSync(join(dir, "a.ts"), "const a = 1;\n");
    writeFileSync(join(dir, "b.ts"), "const b = 1;\n");
    writeFileSync(join(dir, "c.ts"), "const c = 1;\n");
    writeFileSync(join(dir, "d.ts"), "const d = 1;\n");
    run(["git", "add", "."], { cwd: dir });
    run(["git", "commit", "-m", "init"], { cwd: dir });
    writeFileSync(join(dir, "a.ts"), `${"x\n".repeat(80)}`);
    writeFileSync(join(dir, "b.ts"), `${"x\n".repeat(40)}`);
    writeFileSync(join(dir, "c.ts"), `${"x\n".repeat(40)}`);
    writeFileSync(join(dir, "d.ts"), `${"x\n".repeat(40)}`);
    expect(checkDiffBudget(baseData(), dir)[0]).toContain("Diff exceeds budget");
  });
});
