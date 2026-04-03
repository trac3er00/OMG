import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { withRetry } from "./retry.js";

const execFileAsync = promisify(execFile);
const GIT_TIMEOUT_MS = 10_000;

async function gitExec(
  args: string[],
  opts: { cwd?: string; timeout?: number } = {},
): Promise<{ stdout: string; stderr: string }> {
  return withRetry(
    () =>
      execFileAsync("git", args, {
        ...opts,
        encoding: "utf8" as const,
      }) as Promise<{ stdout: string; stderr: string }>,
    {
      maxAttempts: 3,
      baseDelayMs: 100,
      retryOn: (error) => {
        const code = (error as NodeJS.ErrnoException).code;
        return code === "EAGAIN" || code === "EBUSY" || code === "ECONNRESET";
      },
    },
  );
}

export interface GitStatusResult {
  readonly staged: string[];
  readonly unstaged: string[];
  readonly untracked: string[];
  readonly branch: string;
}

export interface GitCommitEntry {
  readonly hash: string;
  readonly subject: string;
  readonly author: string;
  readonly date: string;
}

export interface FileSplit {
  readonly file: string;
  readonly content: string;
}

export interface HunkSplit {
  readonly file: string;
  readonly oldStart: number;
  readonly oldCount: number;
  readonly newStart: number;
  readonly newCount: number;
  readonly context: string;
  readonly lines: string[];
}

export class GitInspector {
  constructor(private readonly cwd: string = ".") {}

  async getStatus(): Promise<GitStatusResult> {
    const { stdout } = await gitExec(["status", "--porcelain"], {
      cwd: this.cwd,
      timeout: GIT_TIMEOUT_MS,
    });

    const staged: string[] = [];
    const unstaged: string[] = [];
    const untracked: string[] = [];

    for (const line of stdout.split("\n")) {
      if (!line) continue;

      const indexStatus = line[0] ?? " ";
      const workTreeStatus = line[1] ?? " ";
      const filePath = line.slice(3);

      if (indexStatus === "?" && workTreeStatus === "?") {
        untracked.push(filePath);
      } else {
        if (indexStatus !== " " && indexStatus !== "?") {
          staged.push(filePath);
        }
        if (workTreeStatus !== " " && workTreeStatus !== "?") {
          unstaged.push(filePath);
        }
      }
    }

    const branch = await this.getBranch();
    return { staged, unstaged, untracked, branch };
  }

  async getDiff(staged = false): Promise<string> {
    const args = staged ? ["diff", "--cached"] : ["diff"];
    const { stdout } = await gitExec(args, {
      cwd: this.cwd,
      timeout: GIT_TIMEOUT_MS,
    });
    return stdout;
  }

  async getLog(n = 10): Promise<GitCommitEntry[]> {
    const { stdout } = await gitExec(
      ["log", `--max-count=${String(n)}`, "--format=%H|%s|%an|%ai"],
      { cwd: this.cwd, timeout: GIT_TIMEOUT_MS },
    );

    const commits: GitCommitEntry[] = [];
    for (const line of stdout.trim().split("\n")) {
      if (!line) continue;
      const parts = line.split("|", 4);
      if (parts.length === 4) {
        commits.push({
          hash: parts[0] ?? "",
          subject: parts[1] ?? "",
          author: parts[2] ?? "",
          date: parts[3] ?? "",
        });
      }
    }
    return commits;
  }

  async getBranch(): Promise<string> {
    try {
      const { stdout } = await gitExec(["rev-parse", "--abbrev-ref", "HEAD"], {
        cwd: this.cwd,
        timeout: GIT_TIMEOUT_MS,
      });
      return stdout.trim();
    } catch {
      return "unknown";
    }
  }
}

// Regex: @@ -oldStart,oldCount +newStart,newCount @@ context
const HUNK_HEADER_RE = /^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\s*(.*)/;

export class CommitSplitter {
  splitByFile(diff: string): FileSplit[] {
    const splits: FileSplit[] = [];
    let currentFile = "";
    let currentLines: string[] = [];

    for (const line of diff.split("\n")) {
      if (line.startsWith("diff --git")) {
        if (currentFile && currentLines.length > 0) {
          splits.push({ file: currentFile, content: currentLines.join("\n") });
        }
        const parts = line.split(" ");
        currentFile = (parts[3] ?? "").replace(/^b\//, "");
        currentLines = [line];
      } else {
        currentLines.push(line);
      }
    }

    if (currentFile && currentLines.length > 0) {
      splits.push({ file: currentFile, content: currentLines.join("\n") });
    }

    return splits;
  }

  splitByHunk(diff: string): HunkSplit[] {
    const hunks: HunkSplit[] = [];
    let currentFile = "";
    let currentHunk: HunkSplit | null = null;
    let hunkLines: string[] = [];

    const flushHunk = (): void => {
      if (currentHunk && hunkLines.length > 0) {
        hunks.push({ ...currentHunk, lines: hunkLines });
      }
      currentHunk = null;
      hunkLines = [];
    };

    for (const line of diff.split("\n")) {
      if (line.startsWith("diff --git")) {
        flushHunk();
        const parts = line.split(" ");
        currentFile = (parts[3] ?? "").replace(/^b\//, "");
        continue;
      }

      if (line.startsWith("@@")) {
        flushHunk();
        const match = HUNK_HEADER_RE.exec(line);
        if (match) {
          currentHunk = {
            file: currentFile,
            oldStart: parseInt(match[1] ?? "0", 10),
            oldCount: match[2] !== undefined ? parseInt(match[2], 10) : 1,
            newStart: parseInt(match[3] ?? "0", 10),
            newCount: match[4] !== undefined ? parseInt(match[4], 10) : 1,
            context: (match[5] ?? "").trim(),
            lines: [],
          };
        }
        continue;
      }

      if (currentHunk !== null) {
        if (
          line.startsWith("+") ||
          line.startsWith("-") ||
          line.startsWith(" ")
        ) {
          hunkLines.push(line);
        }
      }
    }

    flushHunk();
    return hunks;
  }
}
