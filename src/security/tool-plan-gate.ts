import { join } from "node:path";

import type { PolicyDecision } from "../interfaces/policy.js";
import { atomicWriteJson, readJsonFile } from "../state/atomic-io.js";
import { StateResolver } from "../state/state-resolver.js";

export interface ToolPlanEntry {
  readonly runId: string;
  readonly tool: string;
  readonly filePath?: string;
  readonly command?: string;
  readonly timestamp: string;
  readonly allowed: boolean;
  readonly riskScore: number;
  readonly decision?: PolicyDecision;
}

export class ToolPlanGate {
  private readonly resolver: StateResolver;
  private readonly planPath: string;

  constructor(projectDir: string, runId: string) {
    this.resolver = new StateResolver(projectDir);
    this.planPath = this.resolver.resolve(join("jobs", `tool-plan-${runId}.json`));
  }

  async record(entry: Omit<ToolPlanEntry, "timestamp">): Promise<void> {
    const existing = readJsonFile<ToolPlanEntry[]>(this.planPath) ?? [];
    const timestamped: ToolPlanEntry = {
      runId: entry.runId,
      tool: entry.tool,
      timestamp: new Date().toISOString(),
      allowed: entry.allowed,
      riskScore: entry.riskScore,
      ...(entry.filePath != null ? { filePath: entry.filePath } : {}),
      ...(entry.command != null ? { command: entry.command } : {}),
      ...(entry.decision != null ? { decision: entry.decision } : {}),
    };
    existing.push(timestamped);
    atomicWriteJson(this.planPath, existing);
  }

  async getEntries(): Promise<ToolPlanEntry[]> {
    return readJsonFile<ToolPlanEntry[]>(this.planPath) ?? [];
  }
}
