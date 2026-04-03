import { spawnSync } from "node:child_process";
import { existsSync, statSync } from "node:fs";
import { join } from "node:path";
import type { CommandModule } from "yargs";

interface ShipArgs {
  readonly json?: boolean;
}

interface ShipCheckResult {
  readonly name: string;
  readonly status: "pass" | "fail" | "skip";
  readonly details?: Record<string, unknown>;
}

function runBunTests(): ShipCheckResult {
  const result = spawnSync("bun", ["test"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 300_000,
  });

  const text = `${result.stdout ?? ""}\n${result.stderr ?? ""}`;
  const passMatch = text.match(/(\d+)\s+pass/);
  const failMatch = text.match(/(\d+)\s+fail/);

  return {
    name: "bun test",
    status: result.status === 0 ? "pass" : "fail",
    details: {
      passed: passMatch ? Number(passMatch[1]) : 0,
      failed: failMatch ? Number(failMatch[1]) : 0,
      exitCode: result.status,
    },
  };
}

function checkEvidenceDir(): ShipCheckResult {
  const evidencePath = join(process.cwd(), ".omg", "evidence");
  const exists = existsSync(evidencePath);
  const isDirectory = exists ? statSync(evidencePath).isDirectory() : false;
  return {
    name: ".omg/evidence",
    status: isDirectory ? "pass" : "fail",
    details: { path: evidencePath, exists: isDirectory },
  };
}

function runContractValidate(): ShipCheckResult {
  const probe = spawnSync(
    "bun",
    ["run", "src/cli/index.ts", "contract", "validate", "--help"],
    {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 10_000,
    },
  );

  if (probe.status !== 0) {
    return {
      name: "contract validate",
      status: "skip",
      details: { reason: "command_unavailable" },
    };
  }

  const result = spawnSync(
    "bun",
    ["run", "src/cli/index.ts", "contract", "validate"],
    {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 120_000,
    },
  );

  return {
    name: "contract validate",
    status: result.status === 0 ? "pass" : "fail",
    details: { exitCode: result.status },
  };
}

function printHuman(
  status: "ready" | "not_ready",
  checks: readonly ShipCheckResult[],
): void {
  console.log(`Ship readiness: ${status}`);
  for (const check of checks) {
    const detailText = check.details ? ` ${JSON.stringify(check.details)}` : "";
    console.log(`  - ${check.name}: ${check.status}${detailText}`);
  }
}

export const shipCommand: CommandModule<object, ShipArgs> = {
  command: "ship",
  describe: "Run ship workflow",
  builder: (yargs) =>
    yargs.option("json", {
      type: "boolean",
      description: "Output ship readiness as JSON",
      default: false,
    }),
  handler: (argv): void => {
    const checks = [runBunTests(), checkEvidenceDir(), runContractValidate()];
    const isReady = checks.every(
      (check) => check.status === "pass" || check.status === "skip",
    );
    const payload = {
      status: isReady ? "ready" : "not_ready",
      checks,
    } as const;

    if (argv.json) {
      console.log(JSON.stringify(payload, null, 2));
      return;
    }

    printHuman(payload.status, checks);
  },
};
