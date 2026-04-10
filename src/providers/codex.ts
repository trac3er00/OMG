/**
 * Codex CLI provider adapter.
 * Implements BaseCliProvider for the `codex` CLI binary.
 * Mirrors runtime/providers/codex_provider.py.
 */

import { execFile } from "node:child_process";
import { promisify } from "node:util";
import type { HostSurface } from "../runtime/canonical-surface.js";
import { getHostSurface } from "../runtime/canonical-surface.js";
import type { CliHealthStatus } from "../runtime/cli-provider.js";
import { BaseCliProvider } from "../runtime/cli-provider.js";
import type { HostType } from "../types/config.js";

const execFileAsync = promisify(execFile);
const AUTH_CHECK_TIMEOUT_MS = 5_000;

export class CodexProvider extends BaseCliProvider {
  readonly hostType: HostType = "codex";
  readonly surface: HostSurface = getHostSurface("codex");

  async healthCheck(): Promise<CliHealthStatus> {
    const available = await this.isAvailable();
    if (!available) {
      return this.makeHealthStatus(
        false,
        false,
        false,
        "codex CLI not found on PATH",
        "Install: npm install -g @openai/codex",
      );
    }

    try {
      await this.checkAuth();
      return this.makeHealthStatus(
        true,
        true,
        true,
        "codex CLI available and authenticated",
      );
    } catch {
      return this.makeHealthStatus(
        true,
        false,
        false,
        "codex CLI found but not authenticated",
        "Run: codex auth login",
      );
    }
  }

  getMcpConfig(
    serverCommand: string,
    serverArgs: string[],
  ): Record<string, unknown> {
    return {
      mcp_servers: {
        "omg-control": {
          command: serverCommand,
          args: serverArgs,
        },
      },
    };
  }

  async isAvailable(): Promise<boolean> {
    try {
      await execFileAsync("which", ["codex"]);
      return true;
    } catch {
      return false;
    }
  }

  protected async checkAuth(): Promise<void> {
    await execFileAsync("codex", ["auth", "status"], {
      timeout: AUTH_CHECK_TIMEOUT_MS,
    });
  }
}
