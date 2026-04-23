import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import type { CommandModule } from "yargs";

interface UpdateArgs {
  readonly dryRun?: boolean;
  readonly json?: boolean;
  readonly projectDir?: string;
}

function runUpdate(
  projectDir: string,
  dryRun: boolean,
): Record<string, unknown> {
  const result = spawnSync(
    "python3",
    [
      "-c",
      [
        "import json, os",
        "from runtime.operate import update_deployment",
        'print(json.dumps(update_deployment(os.environ[\"OMG_PROJECT_DIR\"], os.environ.get(\"OMG_DRY_RUN\") == \"1\")))',
      ].join("; "),
    ],
    {
      cwd: process.cwd(),
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 300_000,
      env: {
        ...process.env,
        OMG_PROJECT_DIR: projectDir,
        OMG_DRY_RUN: dryRun ? "1" : "0",
      },
    },
  );

  const stdout = `${result.stdout ?? ""}`.trim();
  const stderr = `${result.stderr ?? ""}`.trim();

  if (result.status !== 0) {
    throw new Error(
      [
        `update flow failed (exit=${result.status ?? "unknown"})`,
        stderr,
        stdout,
      ]
        .filter((segment) => segment.length > 0)
        .join("\n"),
    );
  }

  if (!stdout) {
    throw new Error("update flow returned empty output");
  }

  return JSON.parse(stdout) as Record<string, unknown>;
}

export const updateCommand: CommandModule<object, UpdateArgs> = {
  command: "update",
  describe: "Run test-aware deployment update flow",
  builder: {
    "dry-run": {
      type: "boolean",
      description: "Show update plan without executing deploy",
      default: false,
    },
    json: {
      type: "boolean",
      description: "Output update result as JSON",
      default: false,
    },
    "project-dir": {
      type: "string",
      description: "Project directory override",
    },
  },
  handler: (argv): void => {
    const projectDir = resolve(argv.projectDir ?? process.cwd());
    const payload = runUpdate(projectDir, Boolean(argv.dryRun));

    if (argv.json) {
      console.log(JSON.stringify(payload, null, 2));
      return;
    }

    console.log(`Update status: ${String(payload.success ?? false)}`);
    console.log(`Target: ${String(payload.target ?? "unknown")}`);
    console.log(`Message: ${String(payload.message ?? "")}`);
    const changedFiles = Array.isArray(payload.changed_files)
      ? payload.changed_files.map((item) => String(item)).filter(Boolean)
      : [];
    if (changedFiles.length > 0) {
      console.log(`Changed files: ${changedFiles.join(", ")}`);
    }
    if (payload.url) {
      console.log(`URL: ${String(payload.url)}`);
    }

    if (!payload.success) {
      process.exitCode = 1;
    }
  },
};
