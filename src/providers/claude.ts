/**
 * Claude Code provider adapter.
 * Implements BaseCliProvider for the `claude` CLI binary.
 * Mirrors runtime/adapters/claude.py.
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

export class ClaudeProvider extends BaseCliProvider {
  readonly hostType: HostType = "claude";
  readonly surface: HostSurface = getHostSurface("claude");

  async healthCheck(): Promise<CliHealthStatus> {
    const available = await this.isAvailable();
    if (!available) {
      return this.makeHealthStatus(
        false,
        false,
        false,
        "claude CLI not found on PATH",
        "Install: npm install -g @anthropic-ai/claude-code",
      );
    }

    try {
      await execFileAsync("claude", ["auth", "status"], {
        timeout: AUTH_CHECK_TIMEOUT_MS,
      });
      return this.makeHealthStatus(true, true, true, "claude CLI available and authenticated");
    } catch {
      return this.makeHealthStatus(
        true,
        false,
        false,
        "claude CLI found but not authenticated",
        "Run: claude auth login",
      );
    }
  }

  getMcpConfig(serverCommand: string, serverArgs: string[]): Record<string, unknown> {
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
      await execFileAsync("which", ["claude"]);
      return true;
    } catch {
      return false;
    }
  }
}
