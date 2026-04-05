/**
 * CLI provider interface.
 * Abstract base for all CLI host adapters.
 * Mirrors runtime/cli_provider.py abstract base class.
 */

import type { HostType } from "../types/config.js";
import type { HostSurface } from "./canonical-surface.js";

export interface CliHealthStatus {
  readonly available: boolean;
  readonly authOk: boolean;
  readonly liveConnection: boolean;
  readonly statusMessage: string;
  readonly installHint?: string;
}

export interface CliProviderConfig {
  readonly hostType: HostType;
  readonly projectDir: string;
  readonly surface: HostSurface;
}

export interface ICliProvider {
  readonly hostType: HostType;
  readonly surface: HostSurface;

  healthCheck(): Promise<CliHealthStatus>;
  getMcpConfig(serverCommand: string, serverArgs: string[]): unknown;
  getConfigPath(projectDir: string): string;
}

export abstract class BaseCliProvider implements ICliProvider {
  abstract readonly hostType: HostType;
  abstract readonly surface: HostSurface;

  abstract healthCheck(): Promise<CliHealthStatus>;
  abstract getMcpConfig(serverCommand: string, serverArgs: string[]): unknown;

  getConfigPath(projectDir: string): string {
    return `${projectDir}/${this.surface.configPath}`;
  }

  protected makeHealthStatus(
    available: boolean,
    authOk: boolean,
    liveConnection: boolean,
    message: string,
    hint?: string,
  ): CliHealthStatus {
    const status: {
      available: boolean;
      authOk: boolean;
      liveConnection: boolean;
      statusMessage: string;
      installHint?: string;
    } = {
      available,
      authOk,
      liveConnection,
      statusMessage: message,
    };
    if (hint !== undefined) {
      status.installHint = hint;
    }
    return status;
  }
}
