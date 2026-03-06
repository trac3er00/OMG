import { describe, expect, test } from "bun:test";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { globMatch, grep, html, normalize, shell, stripTags } from "../omg_natives/index.ts";

describe("omg_natives", () => {
  test("normalizes text and strips tags", () => {
    expect(normalize("  hello\r\nworld  ")).toBe("hello\nworld");
    expect(stripTags("<p>hello</p> world")).toBe("hello world");
    expect(html("<strong>hi</strong>").text).toBe("hi");
  });

  test("globs and greps content", () => {
    const dir = mkdtempSync(join(tmpdir(), "omg-natives-"));
    try {
      writeFileSync(join(dir, "alpha.ts"), "const value = 1;\nconsole.log(value);\n");
      writeFileSync(join(dir, "beta.md"), "# heading\n");
      expect(globMatch("*.ts", dir)).toEqual(["alpha.ts"]);
      expect(grep("console", join(dir, "alpha.ts"))).toEqual(["console.log(value);"]);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("runs shell commands", () => {
    const result = shell("printf 'ok'");
    expect(result.exitCode).toBe(0);
    expect(result.stdout).toBe("ok");
  });
});
