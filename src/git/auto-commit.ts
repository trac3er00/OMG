import { execSync } from "child_process";

export interface AutoCommitConfig {
  readonly sessionId: string;
  readonly maxBranchLength?: number;
}

export interface CommitOptions {
  readonly type: string;
  readonly scope: string;
  readonly message: string;
}

export interface CommitResult {
  readonly success: boolean;
  readonly branch?: string;
  readonly commitHash?: string;
  readonly error?: string;
}

export const PROTECTED_BRANCHES = new Set(["main", "master", "develop"]);

function getCurrentBranch(): string {
  try {
    return execSync("git rev-parse --abbrev-ref HEAD", {
      encoding: "utf-8",
    }).trim();
  } catch {
    return "unknown";
  }
}

function branchExists(name: string): boolean {
  try {
    execSync(`git rev-parse --verify "${name}" 2>/dev/null`, {
      encoding: "utf-8",
    });
    return true;
  } catch {
    return false;
  }
}

export function initAutoCommit(config: AutoCommitConfig): CommitResult {
  const branchName = `omg-session-${config.sessionId}`.slice(
    0,
    config.maxBranchLength ?? 50,
  );

  if (branchExists(branchName)) {
    return { success: true, branch: branchName };
  }

  try {
    execSync(`git checkout -b "${branchName}"`, { encoding: "utf-8" });
    return { success: true, branch: branchName };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

export function createAutoCommit(options: CommitOptions): CommitResult {
  const currentBranch = getCurrentBranch();

  if (PROTECTED_BRANCHES.has(currentBranch)) {
    return {
      success: false,
      error: `cannot commit to main branch '${currentBranch}'. Use a session branch instead.`,
    };
  }

  const message = formatConventionalCommit(
    options.type,
    options.scope,
    options.message,
  );

  try {
    execSync(`git commit --allow-empty -m "${message}"`, { encoding: "utf-8" });
    const hash = execSync("git rev-parse HEAD", { encoding: "utf-8" })
      .trim()
      .slice(0, 8);
    return { success: true, commitHash: hash, branch: currentBranch };
  } catch (err) {
    return { success: false, error: String(err) };
  }
}

export function formatConventionalCommit(
  type: string,
  scope: string,
  message: string,
): string {
  return `${type}(${scope}): ${message}`;
}
