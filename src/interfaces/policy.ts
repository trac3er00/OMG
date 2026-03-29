export type PolicyAction = "allow" | "warn" | "deny" | "block" | "ask";
export type RiskLevel = "low" | "medium" | "high" | "critical";

export interface PolicyDecision {
  readonly action: PolicyAction;
  readonly reason: string;
  readonly riskLevel: RiskLevel;
  readonly tags: readonly string[];
  readonly metadata?: Readonly<Record<string, unknown>>;
}

export interface PolicyEngine {
  evaluateBashCommand(cmd: string): Promise<PolicyDecision>;
  evaluateFileAccess(tool: string, filePath: string): Promise<PolicyDecision>;
}

export type MutationOperation = "write" | "edit" | "multiedit" | "bash_mutation";
