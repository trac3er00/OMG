import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export const SUPPORTED_DEPLOY_TARGETS = [
  "vercel",
  "netlify",
  "fly",
  "railway",
  "unknown",
] as const;

export type DeployTarget = (typeof SUPPORTED_DEPLOY_TARGETS)[number];

export type DeployResult = {
  readonly url?: string;
  readonly success: boolean;
  readonly message?: string;
  readonly error?: string;
};

type DeployManifest = {
  readonly target: DeployTarget;
  readonly url?: string;
  readonly deployedAt: string;
  readonly gitCommit?: string;
  readonly previous?: Omit<DeployManifest, "previous">;
};

type DeployCommandConfig = {
  readonly cli: string;
  readonly args: readonly string[];
  readonly supportsRollback: boolean;
};

const TARGET_MARKERS: readonly {
  readonly target: DeployTarget;
  readonly file: string;
}[] = [
  { target: "vercel", file: "vercel.json" },
  { target: "netlify", file: "netlify.toml" },
  { target: "fly", file: "fly.toml" },
] as const;

const DEPLOY_COMMANDS: Record<DeployTarget, DeployCommandConfig> = {
  vercel: {
    cli: "vercel",
    args: ["deploy", "--prod", "--yes"],
    supportsRollback: true,
  },
  netlify: {
    cli: "netlify",
    args: ["deploy", "--prod"],
    supportsRollback: false,
  },
  fly: {
    cli: "fly",
    args: ["deploy", "--remote-only"],
    supportsRollback: false,
  },
  railway: {
    cli: "railway",
    args: ["up", "--detach"],
    supportsRollback: false,
  },
  unknown: {
    cli: "",
    args: [],
    supportsRollback: false,
  },
};

function isDeployTarget(value: string): value is DeployTarget {
  return SUPPORTED_DEPLOY_TARGETS.includes(value as DeployTarget);
}

function getManifestPath(projectDir: string): string {
  const stateDir = join(projectDir, ".omg", "deploy");
  mkdirSync(stateDir, { recursive: true });
  return join(stateDir, "latest.json");
}

function readManifest(projectDir: string): DeployManifest | null {
  const manifestPath = join(projectDir, ".omg", "deploy", "latest.json");
  if (!existsSync(manifestPath)) {
    return null;
  }

  try {
    const raw = JSON.parse(
      readFileSync(manifestPath, "utf8"),
    ) as Partial<DeployManifest>;
    if (!raw.target || !isDeployTarget(raw.target) || !raw.deployedAt) {
      return null;
    }
    return raw as DeployManifest;
  } catch {
    return null;
  }
}

function writeManifest(projectDir: string, manifest: DeployManifest): void {
  writeFileSync(
    getManifestPath(projectDir),
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  );
}

function commandExists(command: string): boolean {
  const result = spawnSync("which", [command], {
    encoding: "utf8",
    stdio: ["ignore", "ignore", "ignore"],
    timeout: 5_000,
  });
  return result.status === 0;
}

function readGitCommit(projectDir: string): string | undefined {
  const result = spawnSync("git", ["rev-parse", "HEAD"], {
    cwd: projectDir,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
    timeout: 5_000,
  });
  const commit = `${result.stdout ?? ""}`.trim();
  return result.status === 0 && commit.length > 0 ? commit : undefined;
}

function extractUrl(text: string): string | undefined {
  const match = text.match(/https?:\/\/[^\s"'`<>]+/);
  return match ? match[0].replace(/[),.;]+$/, "") : undefined;
}

function detectDeployTargetSync(projectDir: string): DeployTarget {
  for (const marker of TARGET_MARKERS) {
    if (existsSync(join(projectDir, marker.file))) {
      return marker.target;
    }
  }
  return "unknown";
}

function normalizeTarget(target: string, projectDir: string): DeployTarget {
  return isDeployTarget(target) ? target : detectDeployTargetSync(projectDir);
}

/** Detect deploy target from project files */
export async function detectDeployTarget(
  projectDir: string = ".",
): Promise<DeployTarget> {
  return detectDeployTargetSync(projectDir);
}

/** Check if deploy CLI is authenticated */
export async function isDeployAuthenticated(
  target: DeployTarget,
): Promise<boolean> {
  if (target === "unknown") {
    return false;
  }

  const config = DEPLOY_COMMANDS[target];
  if (!config.cli || !commandExists(config.cli)) {
    return false;
  }

  let authCmd: string[];
  switch (target) {
    case "vercel":
      authCmd = ["whoami"];
      break;
    case "netlify":
      authCmd = ["status"];
      break;
    default:
      // For fly/railway, assume authenticated if CLI exists
      return true;
  }

  const result = spawnSync(config.cli, authCmd, {
    encoding: "utf8",
    stdio: ["ignore", "ignore", "ignore"],
    timeout: 10_000,
  });

  return result.status === 0;
}

/** Extract deployed URL from deploy output */
export function getDeployedUrl(
  output: string,
  target: DeployTarget,
): string | undefined {
  if (target === "unknown") {
    return undefined;
  }

  // Use the existing extractUrl logic for all targets
  return extractUrl(output);
}

export async function deploy(
  projectDir: string,
  target?: DeployTarget,
): Promise<DeployResult> {
  const resolvedTarget = target ?? (await detectDeployTarget(projectDir));

  if (resolvedTarget === "unknown") {
    return {
      success: false,
      error: "No deploy target detected (no vercel.json or netlify.toml)",
    };
  }

  const authed = await isDeployAuthenticated(resolvedTarget);
  if (!authed) {
    return {
      success: false,
      error: `Not authenticated with ${resolvedTarget}. Run: ${resolvedTarget} login`,
    };
  }

  const config = DEPLOY_COMMANDS[resolvedTarget];

  const result = spawnSync(config.cli, [...config.args], {
    cwd: projectDir,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 300_000,
  });
  const output = `${result.stdout ?? ""}\n${result.stderr ?? ""}`.trim();

  if (result.status !== 0) {
    return {
      success: false,
      error: output || `Deployment failed for ${resolvedTarget}`,
    };
  }

  const url = getDeployedUrl(output, resolvedTarget);
  const existing = readManifest(projectDir);
  const gitCommit = readGitCommit(projectDir);
  const manifest: DeployManifest = {
    target: resolvedTarget,
    deployedAt: new Date().toISOString(),
    ...(url ? { url } : {}),
    ...(gitCommit ? { gitCommit } : {}),
    ...(existing
      ? {
          previous: {
            target: existing.target,
            deployedAt: existing.deployedAt,
            ...(existing.url ? { url: existing.url } : {}),
            ...(existing.gitCommit ? { gitCommit: existing.gitCommit } : {}),
          },
        }
      : {}),
  };

  writeManifest(projectDir, manifest);

  return {
    success: true,
    ...(url ? { url } : {}),
  };
}

export async function deployWithOptions(
  target: string,
  projectDir: string,
  dryRun: boolean,
): Promise<DeployResult> {
  const normalizedTarget = normalizeTarget(target, projectDir);
  const config = DEPLOY_COMMANDS[normalizedTarget];
  const commandText = [config.cli, ...config.args].join(" ");

  if (dryRun) {
    return {
      success: true,
      message:
        `Detected ${normalizedTarget} deployment target. ` +
        `Dry run: would execute ${commandText}. ` +
        `Rollback support: ${config.supportsRollback ? "provider CLI" : "manual provider controls"}.`,
    };
  }

  if (!commandExists(config.cli)) {
    return {
      success: false,
      message: `${config.cli} CLI is not installed. Cannot deploy ${normalizedTarget}.`,
      error: `CLI not found: ${config.cli}`,
    };
  }

  const isAuthenticated = await isDeployAuthenticated(normalizedTarget);
  if (!isAuthenticated) {
    const authInstructions: Record<string, string> = {
      vercel: "Run 'vercel login' to authenticate.",
      netlify: "Run 'netlify login' to authenticate.",
      fly: "Run 'fly auth login' to authenticate.",
      railway: "Run 'railway login' to authenticate.",
    };
    const instruction =
      authInstructions[normalizedTarget] ??
      "Please authenticate with the deploy provider.";
    return {
      success: false,
      message: `Not authenticated with ${normalizedTarget}. ${instruction}`,
      error: `Not authenticated: ${normalizedTarget}`,
    };
  }

  const result = spawnSync(config.cli, [...config.args], {
    cwd: projectDir,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: 300_000,
  });
  const output = `${result.stdout ?? ""}\n${result.stderr ?? ""}`.trim();

  if (result.status !== 0) {
    return {
      success: false,
      message: output || `Deployment failed for ${normalizedTarget}.`,
    };
  }

  const url = extractUrl(output);
  const existing = readManifest(projectDir);
  const gitCommit = readGitCommit(projectDir);
  const manifest: DeployManifest = {
    target: normalizedTarget,
    deployedAt: new Date().toISOString(),
    ...(url ? { url } : {}),
    ...(gitCommit ? { gitCommit } : {}),
    ...(existing
      ? {
          previous: {
            target: existing.target,
            deployedAt: existing.deployedAt,
            ...(existing.url ? { url: existing.url } : {}),
            ...(existing.gitCommit ? { gitCommit: existing.gitCommit } : {}),
          },
        }
      : {}),
  };

  writeManifest(projectDir, manifest);

  return {
    success: true,
    ...(url ? { url } : {}),
    message: url
      ? `Deployment completed successfully: ${url}`
      : `Deployment completed successfully for ${normalizedTarget}.`,
  };
}

export async function rollback(
  target: string,
  projectDir: string,
): Promise<{ success: boolean }> {
  const normalizedTarget = normalizeTarget(target, projectDir);
  const manifest = readManifest(projectDir);

  if (!manifest?.previous || normalizedTarget !== "vercel") {
    return { success: false };
  }

  if (!commandExists(DEPLOY_COMMANDS.vercel.cli) || !manifest.previous.url) {
    return { success: false };
  }

  const result = spawnSync(
    DEPLOY_COMMANDS.vercel.cli,
    ["rollback", manifest.previous.url, "--yes"],
    {
      cwd: projectDir,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 300_000,
    },
  );

  if (result.status !== 0) {
    return { success: false };
  }

  writeManifest(projectDir, manifest.previous);
  return { success: true };
}
