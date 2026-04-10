/**
 * Kimi CLI provider adapter.
 * Implements BaseCliProvider for the `kimi` CLI binary.
 * Mirrors runtime/providers/kimi_provider.py.
 */

import { execFile } from "node:child_process";
import { access, readFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import type { HostSurface } from "../runtime/canonical-surface.js";
import { getHostSurface } from "../runtime/canonical-surface.js";
import type { CliHealthStatus } from "../runtime/cli-provider.js";
import { BaseCliProvider } from "../runtime/cli-provider.js";
import type { HostType } from "../types/config.js";

const execFileAsync = promisify(execFile);

export class KimiProvider extends BaseCliProvider {
  readonly hostType: HostType = "kimi";
  readonly surface: HostSurface = getHostSurface("kimi");

  async healthCheck(): Promise<CliHealthStatus> {
    const available = await this.isAvailable();
    if (!available) {
      return this.makeHealthStatus(
        false,
        false,
        false,
        "kimi CLI not found on PATH",
        "Install: npm install -g @anthropic-ai/kimi-code",
      );
    }

    const authOk = await this.checkAuth();
    if (authOk) {
      return this.makeHealthStatus(
        true,
        true,
        true,
        "kimi CLI available and authenticated",
      );
    }
    return this.makeHealthStatus(
      true,
      false,
      false,
      "kimi CLI found but not authenticated",
      "Check ~/.kimi/config.toml for token",
    );
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
      await execFileAsync("which", ["kimi"]);
      return true;
    } catch {
      return false;
    }
  }

  protected async checkAuth(): Promise<boolean> {
    try {
      const configPath = join(homedir(), ".kimi", "config.toml");
      await access(configPath);
      const content = await readFile(configPath, "utf-8");
      return content.includes("token");
    } catch {
      return false;
    }
  }
}
