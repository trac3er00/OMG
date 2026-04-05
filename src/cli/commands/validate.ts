import { readFileSync, existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join } from "node:path";
import type { CommandModule } from "yargs";

interface ValidateArgs {
  readonly json?: boolean;
}

interface ValidateCheck {
  readonly name: string;
  readonly status: "pass" | "fail" | "skip";
  readonly details?: Record<string, unknown>;
}

function checkHostConfigs(): ValidateCheck {
  const files = [".mcp.json", ".gemini/settings.json", ".kimi/mcp.json"];
  const missing = files.filter(
    (file) => !existsSync(join(process.cwd(), file)),
  );
  if (missing.length > 0) {
    return {
      name: "host-config-files",
      status: "fail",
      details: { missing },
    };
  }

  const withoutOmgControl: string[] = [];
  for (const file of files) {
    const content = readFileSync(join(process.cwd(), file), "utf8");
    if (!content.includes("omg-control")) {
      withoutOmgControl.push(file);
    }
  }

  return {
    name: "host-config-files",
    status: withoutOmgControl.length === 0 ? "pass" : "fail",
    details: { checked: files, withoutOmgControl },
  };
}

function checkSkillsDirectories(): ValidateCheck {
  const skillDirs = [
    "skills/claude/SKILL.md",
    "skills/codex/SKILL.md",
    "skills/gemini/SKILL.md",
    "skills/kimi/SKILL.md",
    "skills/opencode/SKILL.md",
  ];

  const missing = skillDirs.filter(
    (path) => !existsSync(join(process.cwd(), path)),
  );
  return {
    name: "skills-directories",
    status: missing.length === 0 ? "pass" : "fail",
    details: { checked: skillDirs, missing },
  };
}

function runCompensatorTests(): ValidateCheck {
  const result = spawnSync("bun", ["test", "src/compensators/"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 180_000,
  });

  const output = `${result.stdout ?? ""}\n${result.stderr ?? ""}`;
  const passMatch = output.match(/(\d+)\s+pass/);
  const failMatch = output.match(/(\d+)\s+fail/);
  return {
    name: "compensators-test-suite",
    status: result.status === 0 ? "pass" : "fail",
    details: {
      passed: passMatch ? Number(passMatch[1]) : 0,
      failed: failMatch ? Number(failMatch[1]) : 0,
      exitCode: result.status,
    },
  };
}

function runContractValidate(): ValidateCheck {
  const cliHelp = spawnSync("bun", ["run", "src/cli/index.ts", "--help"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 10_000,
  });

  const helpText = `${cliHelp.stdout ?? ""}\n${cliHelp.stderr ?? ""}`;
  if (!helpText.includes("omg contract")) {
    return {
      name: "contract-validate",
      status: "skip",
      details: { reason: "command_unavailable" },
    };
  }

  const run = spawnSync(
    "bun",
    ["run", "src/cli/index.ts", "contract", "validate"],
    {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 120_000,
    },
  );

  return {
    name: "contract-validate",
    status: run.status === 0 ? "pass" : "fail",
    details: { exitCode: run.status },
  };
}

export const validateCommand: CommandModule<object, ValidateArgs> = {
  command: "validate",
  describe: "Run validation checks",
  builder: (yargs) =>
    yargs.option("json", {
      type: "boolean",
      description: "Output validation report as JSON",
      default: false,
    }),
  handler: (argv): void => {
    const checks = [
      checkHostConfigs(),
      checkSkillsDirectories(),
      runCompensatorTests(),
      runContractValidate(),
    ];
    const status = checks.every(
      (check) => check.status === "pass" || check.status === "skip",
    )
      ? "pass"
      : "fail";
    const payload = { status, checks } as const;

    if (argv.json) {
      console.log(JSON.stringify(payload, null, 2));
    } else {
      console.log(`validate: ${status}`);
      for (const check of checks) {
        const details = check.details
          ? ` ${JSON.stringify(check.details)}`
          : "";
        console.log(`  - ${check.name}: ${check.status}${details}`);
      }
    }

    if (status === "fail") {
      process.exitCode = 1;
    }
  },
};
