/**
 * OpenCode compatibility provider adapter.
 * Implements BaseCliProvider for the `opencode` CLI binary.
 * Mirrors runtime/providers/opencode_provider.py.
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

export class OpenCodeProvider extends BaseCliProvider {
  readonly hostType: HostType = "opencode";
  readonly surface: HostSurface = getHostSurface("opencode");

  async healthCheck(): Promise<CliHealthStatus> {
    const available = await this.isAvailable();
    if (!available) {
      return this.makeHealthStatus(
        false,
        false,
        false,
        "opencode CLI not found on PATH",
        "Install: go install github.com/opencode/opencode@latest",
      );
    }

    const authOk = await this.checkAuth();
    if (authOk) {
      return this.makeHealthStatus(
        true,
        true,
        true,
        "opencode CLI available and authenticated",
      );
    }
    return this.makeHealthStatus(
      true,
      false,
      false,
      "opencode CLI found but not authenticated",
      "Check ~/.local/share/opencode/auth.json",
    );
  }

  getMcpConfig(
    serverCommand: string,
    serverArgs: string[],
  ): Record<string, unknown> {
    return {
      mcp: {
        "omg-control": {
          type: "stdio",
          command: serverCommand,
          args: serverArgs,
        },
      },
    };
  }

  async isAvailable(): Promise<boolean> {
    try {
      await execFileAsync("which", ["opencode"]);
      return true;
    } catch {
      return false;
    }
  }

  protected async checkAuth(): Promise<boolean> {
    try {
      const authPath = join(
        homedir(),
        ".local",
        "share",
        "opencode",
        "auth.json",
      );
      await access(authPath);
      const content = await readFile(authPath, "utf-8");
      const parsed: unknown = JSON.parse(content);
      return (
        parsed !== null &&
        typeof parsed === "object" &&
        Object.keys(parsed).length > 0
      );
    } catch {
      return false;
    }
  }
}
