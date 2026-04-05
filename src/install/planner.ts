import { execFile } from "node:child_process";
import { join } from "node:path";

export type CanonicalInstallHost = "claude" | "codex" | "gemini" | "kimi";

export interface DetectedHosts {
  readonly claude: boolean;
  readonly codex: boolean;
  readonly gemini: boolean;
  readonly kimi: boolean;
}

export interface InstallStep {
  readonly id: string;
  readonly host: CanonicalInstallHost;
  readonly description: string;
  readonly targetPath: string;
}

export interface InstallPlan {
  readonly steps: InstallStep[];
  readonly preview: string[];
}

interface PlannerDeps {
  readonly probePath: (command: string) => Promise<boolean>;
  readonly cwd: () => string;
  readonly homeDir: () => string;
}

const HOST_TO_CLI: Record<CanonicalInstallHost, string> = {
  claude: "claude",
  codex: "codex",
  gemini: "gemini",
  kimi: "kimi",
};

const CANONICAL_HOSTS: CanonicalInstallHost[] = ["claude", "codex", "gemini", "kimi"];

function probeCommandOnPath(command: string): Promise<boolean> {
  return new Promise<boolean>((resolve) => {
    execFile("which", [command], (error) => {
      resolve(!error);
    });
  });
}

export class InstallPlanner {
  private constructor(private readonly deps: PlannerDeps) {}

  static create(overrides: Partial<PlannerDeps> = {}): InstallPlanner {
    return new InstallPlanner({
      probePath: overrides.probePath ?? probeCommandOnPath,
      cwd: overrides.cwd ?? (() => process.cwd()),
      homeDir: overrides.homeDir ?? (() => process.env.HOME ?? ""),
    });
  }

  async detectHosts(): Promise<DetectedHosts> {
    const checks = await Promise.all(
      CANONICAL_HOSTS.map(async (host) => ({
        host,
        installed: await this.deps.probePath(HOST_TO_CLI[host]),
      })),
    );

    const installedHosts = new Map<CanonicalInstallHost, boolean>(
      checks.map((check) => [check.host, check.installed]),
    );

    return {
      claude: installedHosts.get("claude") ?? false,
      codex: installedHosts.get("codex") ?? false,
      gemini: installedHosts.get("gemini") ?? false,
      kimi: installedHosts.get("kimi") ?? false,
    };
  }

  planInstall(hosts: DetectedHosts): InstallPlan {
    const steps: InstallStep[] = [];

    if (hosts.claude) {
      steps.push({
        id: "configure-claude",
        host: "claude",
        description: "Write .mcp.json for Claude Code",
        targetPath: join(this.deps.cwd(), ".mcp.json"),
      });
    }

    if (hosts.codex) {
      steps.push({
        id: "configure-codex",
        host: "codex",
        description: "Write ~/.codex/config.toml for Codex",
        targetPath: join(this.deps.homeDir(), ".codex", "config.toml"),
      });
    }

    if (hosts.gemini) {
      steps.push({
        id: "configure-gemini",
        host: "gemini",
        description: "Write ~/.gemini/settings.json for Gemini",
        targetPath: join(this.deps.homeDir(), ".gemini", "settings.json"),
      });
    }

    if (hosts.kimi) {
      steps.push({
        id: "configure-kimi",
        host: "kimi",
        description: "Write ~/.kimi/mcp.json for Kimi",
        targetPath: join(this.deps.homeDir(), ".kimi", "mcp.json"),
      });
    }

    return {
      steps,
      preview: steps.map((step) => `- ${step.host}: ${step.targetPath}`),
    };
  }
}
