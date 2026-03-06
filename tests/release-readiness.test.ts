import { describe, expect, test } from "bun:test";
import { chmodSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { collectReleaseReadiness } from "../runtime/release_readiness.ts";
import { tempDir } from "./helpers.ts";

function writeFile(path: string, content: string) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content, "utf8");
}

describe("release readiness", () => {
  test("stable readiness reports beta, deprecated provider, and packaging blockers", () => {
    const projectDir = tempDir("omg-release-readiness-");

    writeFile(
      join(projectDir, "package.json"),
      JSON.stringify(
        {
          version: "2.0.0-beta.6",
          scripts: {
            postinstall: "./OMG-setup.sh install --non-interactive",
            update: "./OMG-setup.sh update",
            uninstall: "./OMG-setup.sh uninstall"
          }
        },
        null,
        2
      )
    );
    writeFile(join(projectDir, "README.md"), "# OMG\n\nOpenCode remains part of this release.\n");
    writeFile(join(projectDir, ".npmignore"), "install.sh\n");
    writeFile(join(projectDir, "OMG-setup.sh"), "#!/bin/bash\nexit 0\n");
    chmodSync(join(projectDir, "OMG-setup.sh"), 0o644);

    const result = collectReleaseReadiness(projectDir);

    expect(result.blockers).toContain("beta marker in package.json");
    expect(result.blockers).toContain("deprecated provider token in README.md");
    expect(result.blockers).toContain("packaged install smoke missing: package.json postinstall must use bash ./OMG-setup.sh");
    expect(result.blockers).toContain("packaged install smoke missing: .npmignore excludes .claude-plugin/scripts/install.sh");
    expect(result.blockers).toContain("packaged install smoke missing: .claude-plugin/scripts/install.sh");
    expect(result.blockers).toContain("packaged install smoke missing: OMG-setup.sh is not executable");
  });
});
