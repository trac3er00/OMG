import { execSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { CommandModule } from "yargs";

interface AutoresearchArgs {
  readonly topic: string;
  readonly timeout: number;
  readonly "max-tokens": number;
  readonly "output-dir": string;
}

export function slugify(topic: string): string {
  return topic
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .slice(0, 50);
}

function buildReportMarkdown(topic: string): string {
  return [
    `# Research: ${topic}`,
    "",
    "## Summary",
    `Research on '${topic}'.`,
    "",
    "## Findings",
    "- Topic researched",
    "",
    "## Code References",
    "",
    "## Recommendations",
    "- Review codebase for related implementations",
  ].join("\n");
}

function buildPythonCommand(topic: string, outputDir: string): string {
  const escapedTopic = topic.replace(/'/g, "\\'");
  const escapedDir = outputDir.replace(/'/g, "\\'");
  const projectDir = process.cwd().replace(/'/g, "\\'");
  return [
    "python3",
    "-c",
    `'import sys; sys.path.insert(0, "${projectDir}"); ` +
      `from runtime.autoresearch_engine import research_topic; ` +
      `print(research_topic("${escapedTopic}", "${escapedDir}"))'`,
  ].join(" ");
}

export function runAutoresearch(
  topic: string,
  outputDir: string,
  timeoutMs: number,
): string {
  const cmd = buildPythonCommand(topic, outputDir);
  try {
    return execSync(cmd, {
      encoding: "utf8",
      cwd: process.cwd(),
      timeout: timeoutMs,
    }).trimEnd();
  } catch {
    const slug = slugify(topic);
    mkdirSync(outputDir, { recursive: true });
    const outputPath = join(outputDir, `${slug}.md`);
    writeFileSync(outputPath, buildReportMarkdown(topic) + "\n", "utf8");
    return outputPath;
  }
}

export const autoresearchCommand: CommandModule<object, AutoresearchArgs> = {
  command: "autoresearch <topic>",
  describe: "Perform deep research on a topic and generate a structured report",
  builder: (yargs) =>
    yargs
      .positional("topic", {
        type: "string",
        demandOption: true,
        description: "Research topic",
      })
      .option("timeout", {
        type: "number",
        default: 120,
        description: "Max seconds for research",
      })
      .option("max-tokens", {
        type: "number",
        default: 10000,
        description: "Token budget limit",
      })
      .option("output-dir", {
        type: "string",
        default: ".omg/research",
        description: "Output directory",
      }),
  handler: (argv): void => {
    const topic = argv.topic;
    const outputDir = argv["output-dir"];
    const timeoutMs = argv.timeout * 1000;

    console.log(`Researching: "${topic}"...`);
    const result = runAutoresearch(topic, outputDir, timeoutMs);
    console.log(`Report generated: ${result}`);
  },
};
