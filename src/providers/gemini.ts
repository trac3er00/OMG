/**
 * Gemini CLI provider adapter.
 * Implements BaseCliProvider for the `gemini` CLI binary.
 * Mirrors runtime/providers/gemini_provider.py.
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

export class GeminiProvider extends BaseCliProvider {
  readonly hostType: HostType = "gemini";
  readonly surface: HostSurface = getHostSurface("gemini");

  async healthCheck(): Promise<CliHealthStatus> {
    const available = await this.isAvailable();
    if (!available) {
      return this.makeHealthStatus(
        false,
        false,
        false,
        "gemini CLI not found on PATH",
        "Install: npm install -g @google/gemini-cli",
      );
    }

    try {
      await this.checkAuth();
      return this.makeHealthStatus(
        true,
        true,
        true,
        "gemini CLI available and authenticated",
      );
    } catch {
      return this.makeHealthStatus(
        true,
        false,
        false,
        "gemini CLI found but not authenticated",
        "Run: gemini auth login",
      );
    }
  }

  getMcpConfig(
    serverCommand: string,
    serverArgs: string[],
  ): Record<string, unknown> {
    return {
      mcpServers: {
        "omg-control": {
          command: serverCommand,
          args: serverArgs,
        },
      },
    };
  }

  async isAvailable(): Promise<boolean> {
    try {
      await execFileAsync("which", ["gemini"]);
      return true;
    } catch {
      return false;
    }
  }

  protected async checkAuth(): Promise<void> {
    await execFileAsync("gemini", ["auth", "status"], {
      timeout: AUTH_CHECK_TIMEOUT_MS,
    });
  }
}
