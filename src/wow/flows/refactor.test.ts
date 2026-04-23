import { describe, expect, test } from "bun:test";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { runRefactorFlow } from "./refactor.js";

function runGit(cwd: string, args: string[]): string {
  const command = Bun.spawnSync(["git", ...args], {
    cwd,
    stdout: "pipe",
    stderr: "pipe",
  });

  const output = new TextDecoder().decode(command.stdout).trim();
  const error = new TextDecoder().decode(command.stderr).trim();

  if (command.exitCode !== 0) {
    throw new Error(error || output || `git ${args.join(" ")} failed`);
  }

  return output;
}

describe("Refactor Flow", () => {
  test('runRefactorFlow("refactor this repo", "/tmp") succeeds and returns structured output', async () => {
    const result = await runRefactorFlow("refactor this repo", "/tmp");

    expect(result.flowName).toBe("refactor");
    expect(result.success).toBe(true);
    expect(Array.isArray(result.suggestions)).toBe(true);
    expect(Array.isArray(result.diffPreview)).toBe(true);
    expect(typeof result.filesAnalyzed).toBe("number");
    expect(result.filesAnalyzed).toBeGreaterThanOrEqual(0);
  });

  test("returns actionable suggestions for common repo issues", async () => {
    const repoDir = await mkdtemp(join(tmpdir(), "wow-refactor-suggest-"));

    await mkdir(join(repoDir, "node_modules", "left-pad"), { recursive: true });
    await mkdir(join(repoDir, "src"), { recursive: true });
    await writeFile(join(repoDir, "camelCase.js"), "export const value = 1;\n");
    await writeFile(
      join(repoDir, "snake_case.js"),
      "export const other = 2;\n",
    );
    await writeFile(
      join(repoDir, "src", "index.js"),
      "export const index = true;\n",
    );

    for (let index = 0; index < 11; index += 1) {
      await writeFile(
        join(repoDir, `file-${index}.js`),
        `export const file${index} = ${index};\n`,
      );
    }

    const result = await runRefactorFlow("refactor this repo", repoDir);
    const descriptions = result.suggestions.map(
      (suggestion) => suggestion.description,
    );

    expect(result.success).toBe(true);
    expect(result.flowName).toBe("refactor");
    expect(result.filesAnalyzed).toBeGreaterThanOrEqual(13);
    expect(descriptions).toContain("Missing README.md");
    expect(descriptions).toContain("Missing .gitignore");
    expect(descriptions).toContain("node_modules should be in .gitignore");
    expect(descriptions).toContain(
      "Consider organizing root-level source files into subdirectories",
    );
    expect(
      descriptions.some((description) =>
        description.includes("Inconsistent file naming styles detected"),
      ),
    ).toBe(true);
    expect(result.diffPreview.length).toBe(result.suggestions.length);
    expect(result.diffPreview[0]?.diff).toContain(
      "Preview only - this flow does not apply changes.",
    );
  });

  test("does not modify files in analyzed repository", async () => {
    const repoDir = await mkdtemp(join(tmpdir(), "wow-refactor-clean-"));

    await mkdir(join(repoDir, "src"), { recursive: true });
    await writeFile(join(repoDir, "README.md"), "# Temp Repo\n");
    await writeFile(join(repoDir, ".gitignore"), "dist\n");
    await writeFile(
      join(repoDir, "src", "index.ts"),
      "export const ready = true;\n",
    );

    runGit(repoDir, ["init"]);
    runGit(repoDir, ["add", "."]);
    runGit(repoDir, [
      "-c",
      "user.name=OMG Test",
      "-c",
      "user.email=omg@example.com",
      "commit",
      "-m",
      "initial",
    ]);

    const statusBefore = runGit(repoDir, ["status", "--short"]);
    const result = await runRefactorFlow("refactor this repo", repoDir);
    const statusAfter = runGit(repoDir, ["status", "--short"]);

    expect(statusBefore).toBe("");
    expect(result.success).toBe(true);
    expect(statusAfter).toBe("");
  });
});
