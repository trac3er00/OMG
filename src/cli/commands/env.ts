import { spawnSync } from "node:child_process";
import type { CommandModule } from "yargs";

interface EnvDoctorArgs {
  readonly json?: boolean;
}

interface EnvCheckResult {
  readonly name: string;
  readonly status: "found" | "missing";
  readonly version?: string;
}

const TOOL_CHECKS = [
  { name: "bun", cmd: "bun --version" },
  { name: "node", cmd: "node --version" },
  { name: "python", cmd: "python3 --version" },
  { name: "git", cmd: "git --version" },
  { name: "claude", cmd: "claude --version" },
  { name: "codex", cmd: "codex --version" },
  { name: "gemini", cmd: "gemini --version" },
  { name: "kimi", cmd: "kimi --version" },
] as const;

const COLORS = {
  green: "\u001b[32m",
  red: "\u001b[31m",
  yellow: "\u001b[33m",
  reset: "\u001b[0m",
} as const;

function runCheck(commandText: string, name: string): EnvCheckResult {
  const [command, ...args] = commandText.split(/\s+/).filter(Boolean);
  if (!command) {
    return { name, status: "missing" };
  }

  const result = spawnSync(command, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 5_000,
  });

  const output = `${result.stdout ?? ""}\n${result.stderr ?? ""}`.trim();
  if (result.error || result.status !== 0) {
    return { name, status: "missing" };
  }

  return output
    ? { name, status: "found", version: output.split("\n")[0].trim() }
    : { name, status: "found" };
}

function printHuman(checks: readonly EnvCheckResult[]): void {
  const found = checks.filter((check) => check.status === "found").length;
  const missing = checks.length - found;
  console.log(`Environment diagnostics (${found}/${checks.length} found)`);

  for (const check of checks) {
    if (check.status === "found") {
      const suffix = check.version
        ? ` ${COLORS.yellow}${check.version}${COLORS.reset}`
        : "";
      console.log(`  ${COLORS.green}✔${COLORS.reset} ${check.name}${suffix}`);
      continue;
    }
    console.log(`  ${COLORS.red}✖${COLORS.reset} ${check.name} (missing)`);
  }

  if (missing > 0) {
    console.log(
      `${COLORS.red}${missing} required tool(s) are missing from PATH.${COLORS.reset}`,
    );
  }
}

export const envDoctorCommand: CommandModule<object, EnvDoctorArgs> = {
  command: "env doctor",
  describe: "Run environment diagnostics",
  builder: (yargs) =>
    yargs.option("json", {
      type: "boolean",
      description: "Output diagnostics as JSON",
      default: false,
    }),
  handler: (argv): void => {
    const checks = TOOL_CHECKS.map((entry) => runCheck(entry.cmd, entry.name));
    const payload = { checks };

    if (argv.json) {
      console.log(JSON.stringify(payload, null, 2));
      return;
    }

    printHuman(checks);
  },
};
