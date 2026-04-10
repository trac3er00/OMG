export type GovernanceEnforcement = "advisory" | "enforced";

export const DEFAULT_ENFORCEMENT: GovernanceEnforcement = "enforced";

export class GovernanceBlockError extends Error {
  readonly gate: string;
  readonly blockReason: string;
  readonly enforcement: GovernanceEnforcement = "enforced";

  constructor(gate: string, reason: string) {
    super(`[governance:${gate}] BLOCKED: ${reason}`);
    this.name = "GovernanceBlockError";
    this.gate = gate;
    this.blockReason = reason;
  }
}

export interface ForceOverrideRecord {
  readonly gate: string;
  readonly tool: string;
  readonly reason: string;
  readonly timestamp: string;
  readonly override: "force";
}
