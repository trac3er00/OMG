import { spawnSync } from "node:child_process";
import { existsSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import type { CommandModule } from "yargs";

interface ProofArgs {
  readonly html?: boolean;
}

interface EvidenceEntry {
  readonly name: string;
  readonly path: string;
  readonly mtime: string;
}

function listEvidenceEntries(): EvidenceEntry[] {
  const evidenceDir = join(process.cwd(), ".omg", "evidence");
  if (!existsSync(evidenceDir)) {
    return [];
  }

  return readdirSync(evidenceDir)
    .map((name) => {
      const fullPath = join(evidenceDir, name);
      const stats = statSync(fullPath);
      return {
        name,
        path: fullPath,
        mtime: stats.mtime.toISOString(),
      };
    })
    .sort((a, b) => b.mtime.localeCompare(a.mtime));
}

function openInBrowser(targetPath: string): void {
  const platform = process.platform;
  if (platform === "darwin") {
    spawnSync("open", [targetPath], { stdio: "ignore", timeout: 5_000 });
    return;
  }
  if (platform === "win32") {
    spawnSync("cmd", ["/c", "start", "", targetPath], {
      stdio: "ignore",
      timeout: 5_000,
    });
    return;
  }
  spawnSync("xdg-open", [targetPath], { stdio: "ignore", timeout: 5_000 });
}

function runProofOpen(argv: ProofArgs): void {
  const entries = listEvidenceEntries();
  if (entries.length === 0) {
    console.log("No proof artifacts found in .omg/evidence/");
    return;
  }

  if (argv.html) {
    const htmlEntry =
      entries.find((entry) => entry.name.endsWith(".html")) ?? entries[0];
    openInBrowser(htmlEntry.path);
    console.log(`Opened: ${htmlEntry.path}`);
    return;
  }

  console.log("Proof artifacts (.omg/evidence):");
  for (const entry of entries) {
    console.log(`  - ${entry.mtime}  ${entry.name}`);
  }
}

export const proofCommand: CommandModule<object, ProofArgs> = {
  command: "proof",
  describe: "Inspect latest proof artifacts",
  builder: (yargs) =>
    yargs
      .option("html", {
        type: "boolean",
        description: "Open latest proof artifact in browser",
        default: false,
      })
      .command(
        "open",
        "Open/list proof artifacts",
        (openYargs) =>
          openYargs.option("html", {
            type: "boolean",
            description: "Open latest proof artifact in browser",
            default: false,
          }),
        (openArgv) => {
          runProofOpen(openArgv);
        },
      ),
  handler: (argv): void => {
    runProofOpen(argv);
  },
};
