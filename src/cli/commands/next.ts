import { execSync } from "node:child_process";
import { writeFileSync } from "node:fs";
import type { CommandModule } from "yargs";

export interface NextOptions {
  readonly focus?: string | undefined;
  readonly quick?: boolean | undefined;
  readonly output?: string | undefined;
}

interface NextArgs {
  focus: string | undefined;
  quick: boolean;
  output: string | undefined;
}

interface Suggestion {
  readonly category: string;
  readonly description: string;
  readonly impact: number;
  readonly effort: number;
  readonly risk: number;
}

interface Report {
  readonly suggestions: readonly Suggestion[];
  readonly scores: Record<string, number>;
  readonly error?: string;
  readonly raw?: string;
}

function buildPythonCommand(
  projectDir: string,
  focus: string | undefined,
): string {
  const escapedDir = projectDir.replace(/'/g, "\\'");
  const focusArg = focus ? `"${focus.replace(/"/g, '\\"')}"` : "None";
  return [
    "python3",
    "-c",
    `'import sys, json; sys.path.insert(0, "${escapedDir}"); ` +
      `from runtime.project_analyzer import ProjectAnalyzer; ` +
      `a = ProjectAnalyzer("${escapedDir}"); ` +
      `r = a.analyze(focus=${focusArg}); ` +
      `print(json.dumps(r.to_dict(), indent=2))'`,
  ].join(" ");
}

function runAnalyzer(projectDir: string, focus: string | undefined): Report {
  let reportJson: string;
  try {
    const cmd = buildPythonCommand(projectDir, focus);
    reportJson = execSync(cmd, {
      encoding: "utf8",
      cwd: projectDir,
      timeout: 120_000,
    }).trimEnd();
  } catch (e) {
    reportJson = JSON.stringify({
      suggestions: [],
      scores: {},
      error: String(e),
    });
  }

  try {
    return JSON.parse(reportJson) as Report;
  } catch {
    return {
      suggestions: [],
      scores: {},
      raw: reportJson,
    };
  }
}

export function runNext(options: NextOptions = {}): void {
  const { focus, quick = false, output } = options;
  const projectDir = process.cwd();

  void quick;

  const report = runAnalyzer(projectDir, focus);

  if (output) {
    writeFileSync(output, JSON.stringify(report, null, 2) + "\n", "utf8");
    console.log(`Analysis saved to: ${output}`);
  }

  if (report.error) {
    console.log(`\n\u26A0 Analyzer error: ${report.error}`);
    return;
  }

  const scores = report.scores ?? {};
  const scoreEntries = Object.entries(scores);
  if (scoreEntries.length > 0) {
    console.log("\n\u{1F4CA} Project Health Scores");
    for (const [dim, score] of scoreEntries) {
      const filled = Math.round(score / 10);
      const bar = "\u2588".repeat(filled) + "\u2591".repeat(10 - filled);
      console.log(`  ${dim.padEnd(20)} [${bar}] ${score}/100`);
    }
  }

  const suggestions = report.suggestions ?? [];
  const top5 = suggestions.slice(0, 5);
  if (top5.length > 0) {
    const focusLabel = focus ? ` (focus: ${focus})` : "";
    console.log(
      `\n\u{1F4A1} Top ${top5.length} Improvement Suggestions${focusLabel}`,
    );
    for (let i = 0; i < top5.length; i++) {
      const s = top5[i]!;
      console.log(`\n${i + 1}. [${s.category}] ${s.description}`);
      console.log(
        `   Impact: ${s.impact}/100 | Effort: ${s.effort}/100 | Risk: ${s.risk}/100`,
      );
    }
  } else {
    console.log("\n\u2705 No high-priority improvements found.");
  }
}

export const nextCommand: CommandModule<object, NextArgs> = {
  command: "next",
  describe: "Analyze project health and surface next improvements",
  builder: (yargs) =>
    yargs
      .option("focus", {
        type: "string",
        description: "Narrow analysis to a specific dimension",
      })
      .option("quick", {
        type: "boolean",
        description: "Skip deep analysis for faster results",
        default: false,
      })
      .option("output", {
        type: "string",
        description: "Write full JSON report to this path",
      }),
  handler: (argv): void => {
    runNext({
      focus: argv.focus,
      quick: argv.quick,
      output: argv.output,
    });
  },
};
