import { describe, expect, test } from "bun:test";
import { PassThrough } from "node:stream";
import { createInitCommand } from "./init.js";

function decode(chunks: Uint8Array[]): string {
  return chunks.map((chunk) => new TextDecoder().decode(chunk)).join("");
}

async function runInitWithInput(options: {
  input: string;
  argv?: Record<string, unknown>;
  runInitWizard?: () => Promise<void>;
}) {
  const stdout = new PassThrough();
  const stderr = new PassThrough();
  const stdoutChunks: Uint8Array[] = [];
  const stderrChunks: Uint8Array[] = [];
  const calls: number[] = [];
  const env: NodeJS.ProcessEnv = {};
  const answers = options.input.split("\n");

  stdout.on("data", (chunk: Uint8Array) => stdoutChunks.push(chunk));
  stderr.on("data", (chunk: Uint8Array) => stderrChunks.push(chunk));

  const command = createInitCommand({
    input: process.stdin,
    output: stdout,
    env,
    createReadline: (() => ({
      question: async () => `${answers.shift() ?? ""}`,
      close: () => {},
    })) as never,
    log: (message = "") => {
      stdout.write(`${message}\n`);
    },
    error: (message = "") => {
      stderr.write(`${message}\n`);
    },
    cwd: () => "/tmp/demo-project",
    runInitWizard: async () => {
      calls.push(Date.now());
      if (options.runInitWizard) {
        await options.runInitWizard();
      }
    },
  });
  await command.handler?.({
    yes: false,
    json: false,
    configure: false,
    advanced: false,
    fast: false,
    ...(options.argv ?? {}),
  } as never);

  stdout.end();
  stderr.end();

  return {
    stdout: decode(stdoutChunks),
    stderr: decode(stderrChunks),
    env,
    calls: calls.length,
  };
}

describe("init command", () => {
  test("guided beginner flow stays enter-driven and under ten steps", async () => {
    const result = await runInitWithInput({
      input: "\n\n\n\n",
    });

    const stepMatches = result.stdout.match(/Step \d+(?: of \d+)?:/g) ?? [];

    expect(stepMatches.length).toBeLessThanOrEqual(10);
    expect(result.stdout).toContain("OMG Universal Onboarding");
    expect(result.stdout).toContain("Choose how much guidance you want");
    expect(result.stdout).toContain(
      "We'll keep the current folder name unless you want something else.",
    );
    expect(result.stdout).toContain(
      "You're in guided mode, so we'll confirm before OMG makes any changes.",
    );
    expect(result.env.OMG_INIT_SKILL_LEVEL).toBe("beginner");
    expect(result.env.OMG_INIT_FLOW_MODE).toBe("guided");
    expect(result.env.OMG_INIT_PROJECT_NAME).toBe("demo-project");
    expect(result.env.OMG_INIT_PRESET).toBe("standard");
    expect(result.calls).toBe(1);
  });

  test("expert --fast flow stays compact and skips verbose guidance", async () => {
    const result = await runInitWithInput({
      input: "\n\n\n",
      argv: { fast: true },
    });

    const compactSteps = result.stdout.match(/\[\d+\/\d+\]/g) ?? [];

    expect(compactSteps.length).toBeLessThanOrEqual(5);
    expect(result.stdout).toContain("OMG Fast Init");
    expect(result.stdout).toContain("[1/3] Project");
    expect(result.stdout).not.toContain("Choose how much guidance you want");
    expect(result.stdout).not.toContain(
      "We'll keep the current folder name unless you want something else.",
    );
    expect(result.env.OMG_INIT_SKILL_LEVEL).toBe("expert");
    expect(result.env.OMG_INIT_FLOW_MODE).toBe("fast");
    expect(result.env.OMG_INIT_PRESET).toBe("standard");
    expect(result.calls).toBe(1);
  });

  test("clear retry messaging recovers from a simulated failure", async () => {
    let attempts = 0;

    const result = await runInitWithInput({
      input: "\n\n\n\n\n",
      runInitWizard: async () => {
        attempts += 1;
        if (attempts === 1) {
          throw new Error("simulated install failure");
        }
      },
    });

    expect(attempts).toBe(2);
    expect(result.stderr).toContain(
      "Setup hit a problem: simulated install failure",
    );
    expect(result.stdout).toContain("Retrying setup...");
    expect(result.calls).toBe(2);
  });
});
