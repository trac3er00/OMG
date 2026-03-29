import type { RiskLevel } from "../interfaces/policy.js";
import { DefenseStateManager } from "../security/defense-state.js";

export interface SessionHealth {
  readonly status: "healthy" | "degraded" | "critical";
  readonly tool_count: number;
  readonly risk_level: RiskLevel;
  readonly session_id?: string;
}

function riskToStatus(risk: RiskLevel): SessionHealth["status"] {
  switch (risk) {
    case "critical":
      return "critical";
    case "high":
      return "degraded";
    case "medium":
      return "degraded";
    case "low":
      return "healthy";
  }
}

export class SessionHealthProvider {
  private readonly defenseManager: DefenseStateManager;
  private readonly toolCount: number;

  constructor(defenseManager: DefenseStateManager, toolCount?: number) {
    this.defenseManager = defenseManager;
    this.toolCount = toolCount ?? 0;
  }

  static create(projectDir: string, toolCount?: number): SessionHealthProvider {
    const defenseManager = new DefenseStateManager(projectDir);
    return new SessionHealthProvider(defenseManager, toolCount);
  }

  getHealth(sessionId?: string): SessionHealth {
    const defense = this.defenseManager.load();
    const status = riskToStatus(defense.riskLevel);

    return {
      status,
      tool_count: this.toolCount,
      risk_level: defense.riskLevel,
      ...(sessionId !== undefined ? { session_id: sessionId } : {}),
    };
  }
}
