import type { PolicyDecision, RiskLevel } from "../interfaces/policy.js";
import type { DefenseStateData } from "./defense-state.js";
import type { InjectionDetectionResult } from "./injection-defense.js";

export interface ThreatScoreResult {
  readonly level: "low" | "medium" | "high" | "critical";
  readonly score: number;
}

interface ThreatSignal {
  readonly source: "firewall" | "defense-state" | "injection-defense";
  readonly severity: number;
  readonly occurredAtMs: number;
}

export interface ThreatScorerOptions {
  readonly now?: () => number;
  readonly halfLifeMs?: number;
}

function riskSeverity(level: RiskLevel): number {
  switch (level) {
    case "critical":
      return 1;
    case "high":
      return 0.75;
    case "medium":
      return 0.45;
    case "low":
      return 0.15;
  }
}

function actionSeverity(action: PolicyDecision["action"]): number {
  switch (action) {
    case "deny":
    case "block":
      return 0.95;
    case "ask":
      return 0.7;
    case "warn":
      return 0.55;
    case "allow":
      return 0.1;
  }
}

export class ThreatScorer {
  private readonly now: () => number;
  private readonly halfLifeMs: number;
  private readonly signals: ThreatSignal[] = [];

  constructor(options: ThreatScorerOptions = {}) {
    this.now = options.now ?? Date.now;
    this.halfLifeMs = options.halfLifeMs ?? 5 * 60 * 1000;
  }

  addFirewallDecision(decision: PolicyDecision): void {
    this.signals.push({
      source: "firewall",
      severity: actionSeverity(decision.action),
      occurredAtMs: this.now(),
    });
  }

  addDefenseState(state: DefenseStateData): void {
    const weighted = Math.min(
      1,
      riskSeverity(state.riskLevel) + state.contaminationScore * 0.5 + state.injectionHits * 0.1,
    );

    this.signals.push({
      source: "defense-state",
      severity: weighted,
      occurredAtMs: this.now(),
    });
  }

  addInjectionResult(result: InjectionDetectionResult): void {
    const severity = result.detected ? Math.max(result.confidence, 0.25) : 0.05;
    this.signals.push({
      source: "injection-defense",
      severity,
      occurredAtMs: this.now(),
    });
  }

  score(): ThreatScoreResult {
    const now = this.now();
    const decayed = this.signals.reduce((total, signal) => {
      const ageMs = Math.max(now - signal.occurredAtMs, 0);
      const recencyWeight = Math.pow(2, -ageMs / this.halfLifeMs);
      return total + signal.severity * recencyWeight;
    }, 0);

    const normalized = Number(Math.min(100, decayed * 25).toFixed(2));

    if (normalized >= 75) {
      return { level: "critical", score: normalized };
    }
    if (normalized >= 50) {
      return { level: "high", score: normalized };
    }
    if (normalized >= 25) {
      return { level: "medium", score: normalized };
    }
    return { level: "low", score: normalized };
  }
}
