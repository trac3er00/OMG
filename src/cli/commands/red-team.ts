import { execSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import type { CommandModule } from "yargs";

export interface RedTeamOptions {
  readonly scope?: string;
  readonly severityFloor?: string;
  readonly output?: string | undefined;
}

interface RedTeamArgs {
  scope: string;
  "severity-floor": string;
  output: string | undefined;
}

interface Finding {
  readonly severity: string;
  readonly category: string;
  readonly file: string;
  readonly line: number;
  readonly description: string;
  readonly remediation: string;
  readonly code_snippet: string;
}

interface ReportSummary {
  readonly total: number;
  readonly critical: number;
  readonly high: number;
  readonly medium: number;
  readonly low: number;
}

interface Report {
  readonly findings: readonly Finding[];
  readonly summary: ReportSummary;
  readonly files_scanned: number;
  readonly total_lines: number;
  readonly error?: string;
  readonly raw?: string;
}

function buildPythonCommand(
  projectDir: string,
  scope: string,
  severityFloor: string,
): string {
  const escapedDir = projectDir.replace(/'/g, "\\'");
  const escapedScope = scope.replace(/'/g, "\\'");
  const escapedFloor = severityFloor.replace(/'/g, "\\'");
  return [
    "python3",
    "-c",
    `'import sys, json; sys.path.insert(0, "${escapedDir}"); ` +
      `from runtime.adversarial_review import AdversarialReview; ` +
      `r = AdversarialReview(severity_floor="${escapedFloor}").scan("${escapedScope}"); ` +
      `print(json.dumps(r.to_dict(), indent=2))'`,
  ].join(" ");
}

function runScanner(
  projectDir: string,
  scope: string,
  severityFloor: string,
): Report {
  let reportJson: string;
  try {
    const cmd = buildPythonCommand(projectDir, scope, severityFloor);
    reportJson = execSync(cmd, {
      encoding: "utf8",
      cwd: projectDir,
      timeout: 60_000,
    }).trimEnd();
  } catch (e) {
    reportJson = JSON.stringify({
      findings: [],
      summary: { total: 0, critical: 0, high: 0, medium: 0, low: 0 },
      files_scanned: 0,
      total_lines: 0,
      error: String(e),
    });
  }

  try {
    return JSON.parse(reportJson) as Report;
  } catch {
    return {
      findings: [],
      summary: { total: 0, critical: 0, high: 0, medium: 0, low: 0 },
      files_scanned: 0,
      total_lines: 0,
      raw: reportJson,
    };
  }
}

export function runRedTeam(options: RedTeamOptions = {}): void {
  const { scope = ".", severityFloor = "medium", output } = options;
  const projectDir = process.cwd();

  const report = runScanner(projectDir, scope, severityFloor);

  if (output) {
    writeFileSync(output, JSON.stringify(report, null, 2) + "\n", "utf8");
    console.log(`Red team report saved to: ${output}`);
  }

  const { findings, summary } = report;

  console.log("\n\u{1F534} Red Team Security Report");
  console.log(`Scope: ${scope} | Severity floor: ${severityFloor}`);
  console.log(
    `Files scanned: ${report.files_scanned} | Lines: ${report.total_lines}`,
  );
  console.log(
    `Findings: ${findings.length} total` +
      ` (critical: ${summary.critical ?? 0}` +
      `, high: ${summary.high ?? 0}` +
      `, medium: ${summary.medium ?? 0})`,
  );

  if (report.error) {
    console.log(`\n⚠ Scanner error: ${report.error}`);
    return;
  }

  if (findings.length > 0) {
    console.log("\nTop findings:");
    const topFindings = findings.slice(0, 10);
    for (const f of topFindings) {
      console.log(`  [${f.severity}] ${f.category}: ${f.description}`);
      console.log(`    File: ${f.file}:${f.line}`);
      console.log(`    Fix: ${f.remediation}`);
    }
    if (findings.length > 10) {
      console.log(`  ... and ${findings.length - 10} more`);
    }
  } else {
    console.log("\n\u2705 No findings above severity floor.");
  }
}

export const redTeamCommand: CommandModule<object, RedTeamArgs> = {
  command: "red-team [scope]",
  describe: "Run adversarial security review",
  builder: (yargs) =>
    yargs
      .positional("scope", {
        type: "string",
        description: "File or directory to scan",
        default: ".",
      })
      .option("severity-floor", {
        type: "string",
        choices: ["low", "medium", "high", "critical"] as const,
        description: "Minimum severity level for findings",
        default: "medium",
      })
      .option("output", {
        type: "string",
        description: "Write full JSON report to this path",
      }),
  handler: (argv): void => {
    runRedTeam({
      scope: argv.scope,
      severityFloor: argv["severity-floor"],
      output: argv.output,
    });
  },
};
