import { execSync } from "node:child_process";
import * as path from "node:path";
import type { CommandModule } from "yargs";

interface PackInfo {
  readonly name: string;
  readonly description: string;
  readonly category: string;
}

interface ScaffoldResult {
  readonly success: boolean;
  readonly files: readonly string[];
  readonly rules?: readonly string[];
  readonly error?: string;
}

interface DomainsArgs {
  readonly subcommand: string | undefined;
  readonly pack: string | undefined;
  readonly target: string | undefined;
}

function buildListCommand(projectDir: string): string {
  const escaped = projectDir.replace(/'/g, "\\'");
  return [
    "python3",
    "-c",
    `'import sys, json; sys.path.insert(0, "${escaped}"); from runtime.domain_packs import list_packs; print(json.dumps(list_packs()))'`,
  ].join(" ");
}

function buildInitCommand(
  projectDir: string,
  packName: string,
  target: string,
): string {
  const escaped = projectDir.replace(/'/g, "\\'");
  const escapedPack = packName.replace(/'/g, "\\'");
  const escapedTarget = target.replace(/'/g, "\\'");
  return [
    "python3",
    "-c",
    `'import sys, json; sys.path.insert(0, "${escaped}"); from runtime.domain_packs import scaffold_project; r = scaffold_project("${escapedPack}", "${escapedTarget}"); print(json.dumps(r))'`,
  ].join(" ");
}

export function runDomains(
  subcommand?: string,
  packName?: string,
  target?: string,
): void {
  const projectDir = process.cwd();

  if (!subcommand || subcommand === "list") {
    try {
      const output = execSync(buildListCommand(projectDir), {
        encoding: "utf8",
        cwd: projectDir,
        timeout: 30_000,
      }).trimEnd();
      const packs = JSON.parse(output) as PackInfo[];
      console.log("\n\u{1F4E6} Available Domain Packs\n");
      if (packs.length === 0) {
        console.log("  No domain packs found.");
      } else {
        for (const p of packs) {
          console.log(
            `  ${p.name.padEnd(20)} [${p.category}] ${p.description}`,
          );
        }
      }
    } catch {
      console.log("  No domain packs available.");
    }
    return;
  }

  if (subcommand === "init") {
    if (!packName) {
      console.error("Usage: npx omg domains init <pack-name> [--target <dir>]");
      return;
    }
    const resolvedTarget = target ?? path.join(projectDir, packName);
    try {
      const output = execSync(
        buildInitCommand(projectDir, packName, resolvedTarget),
        { encoding: "utf8", cwd: projectDir, timeout: 30_000 },
      ).trimEnd();
      const result = JSON.parse(output) as ScaffoldResult;
      if (result.success) {
        console.log(`\u2705 Scaffold generated at: ${resolvedTarget}`);
        console.log(`   Files: ${result.files.length} created`);
        if (result.rules && result.rules.length > 0) {
          console.log(`   Rules: ${result.rules.length} installed`);
        }
      } else {
        console.error(`\u274C Failed: ${result.error ?? "unknown error"}`);
      }
    } catch (e) {
      console.error(`Failed to scaffold: ${e}`);
    }
    return;
  }

  console.log(
    "Usage: npx omg domains list | npx omg domains init <pack-name> [--target <dir>]",
  );
}

export const domainsCommand: CommandModule<object, DomainsArgs> = {
  command: "domains [subcommand] [pack]",
  describe: "Domain pack discovery and scaffolding",
  builder: (yargs) =>
    yargs
      .positional("subcommand", {
        type: "string",
        description: "Subcommand: list or init",
        default: "list",
      })
      .positional("pack", {
        type: "string",
        description: "Pack name (for init)",
      })
      .option("target", {
        type: "string",
        description: "Target directory for scaffold output",
      }),
  handler: (argv): void => {
    runDomains(argv.subcommand, argv.pack, argv.target);
  },
};
