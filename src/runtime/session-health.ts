import type { RiskLevel } from "../interfaces/policy.js";
import { DefenseStateManager } from "../security/defense-state.js";
import { computeASI, type SessionObservation } from "../reliability/drift.js";

export interface SessionHealth {
  readonly status: "healthy" | "degraded" | "critical";
  readonly tool_count: number;
  readonly risk_level: RiskLevel;
  readonly drift_detected?: boolean;
  readonly drift_asi?: number;
  readonly drift_type?: "semantic" | "coordination" | "behavioral";
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

  getHealth(
    sessionId?: string,
    observations: readonly SessionObservation[] = [],
  ): SessionHealth {
    const defense = this.defenseManager.load();
    let status = riskToStatus(defense.riskLevel);

    const driftReport =
      observations.length > 1 ? computeASI([...observations]) : undefined;
    if (driftReport?.detected) {
      status = driftReport.scores.asi < 0.3 ? "critical" : "degraded";
    }

    return {
      status,
      tool_count: this.toolCount,
      risk_level: defense.riskLevel,
      ...(driftReport
        ? {
            drift_detected: driftReport.detected,
            drift_asi: driftReport.scores.asi,
            drift_type: driftReport.dominantDriftType,
          }
        : {}),
      ...(sessionId !== undefined ? { session_id: sessionId } : {}),
    };
  }
}
