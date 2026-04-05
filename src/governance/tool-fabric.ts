import { appendJsonLine, readJsonLines } from "../state/atomic-io.js";
import { StateResolver } from "../state/state-resolver.js";
import { join } from "node:path";

export interface LanePolicy {
  readonly allowedTools?: readonly string[];
  readonly requiresSignedApproval?: boolean;
  readonly requiresAttestation?: boolean;
  readonly evidenceRequired?: readonly string[];
}

export interface ToolFabricResult {
  readonly action: "allow" | "deny" | "warn";
  readonly reason: string;
  readonly lane: string;
  readonly tool: string;
  readonly timestamp: string;
}

export interface LedgerEntry extends ToolFabricResult {
  readonly args: Record<string, unknown>;
}

export interface ToolExecutionResult {
  readonly decision: ToolFabricResult;
  readonly output?: unknown;
}

type ToolExecutor = (tool: string, args: Readonly<Record<string, unknown>>) => unknown | Promise<unknown>;

export class ToolFabric {
  private readonly lanes = new Map<string, LanePolicy>();
  private readonly ledgerPath: string;

  constructor(projectDir: string) {
    const resolver = new StateResolver(projectDir);
    this.ledgerPath = resolver.resolve(join("ledger", "tool-fabric.jsonl"));
  }

  registerLane(name: string, policy: LanePolicy): void {
    const lane = name.trim().toLowerCase();
    if (!lane) {
      throw new Error("lane name is required");
    }
    this.lanes.set(lane, policy);
  }

  async evaluateRequest(
    tool: string,
    args: Record<string, unknown>,
    laneName = "default",
  ): Promise<ToolFabricResult> {
    const lane = laneName.trim().toLowerCase() || "default";
    const policy = this.lanes.get(lane);
    const timestamp = new Date().toISOString();

    const result = this.decide(tool, args, lane, policy, timestamp);
    const entry: LedgerEntry = { ...result, args };

    try {
      appendJsonLine(this.ledgerPath, entry);
    } catch {
      // best-effort ledger write
    }

    return result;
  }

  async executeTool(
    tool: string,
    args: Record<string, unknown>,
    laneName = "default",
    executor?: ToolExecutor,
  ): Promise<ToolExecutionResult> {
    const decision = await this.evaluateRequest(tool, args, laneName);
    if (decision.action !== "allow" || !executor) {
      return { decision };
    }

    const output = await executor(tool, args);
    return { decision, output };
  }

  getLedgerEntries(): readonly LedgerEntry[] {
    return readJsonLines<LedgerEntry>(this.ledgerPath);
  }

  close(): void {
    // no-op: retained for API parity
  }

  private decide(
    tool: string,
    args: Readonly<Record<string, unknown>>,
    lane: string,
    policy: LanePolicy | undefined,
    timestamp: string,
  ): ToolFabricResult {
    if (!policy?.allowedTools) {
      return {
        action: "allow",
        reason: "Default lane: all tools permitted",
        lane,
        tool,
        timestamp,
      };
    }

    if (!policy.allowedTools.includes(tool)) {
      return {
        action: "deny",
        reason: `Tool '${tool}' is not in allowed tools for lane '${lane}': [${policy.allowedTools.join(", ")}]`,
        lane,
        tool,
        timestamp,
      };
    }

    if (policy.requiresSignedApproval && args.signedApproval !== true) {
      return {
        action: "deny",
        reason: `Lane '${lane}' requires signed approval`,
        lane,
        tool,
        timestamp,
      };
    }

    if (policy.requiresAttestation && args.attested !== true) {
      return {
        action: "deny",
        reason: `Lane '${lane}' requires attestation`,
        lane,
        tool,
        timestamp,
      };
    }

    if (policy.evidenceRequired && policy.evidenceRequired.length > 0) {
      const evidence = args.evidence;
      if (!this.hasRequiredEvidence(evidence, policy.evidenceRequired)) {
        return {
          action: "deny",
          reason: `Lane '${lane}' missing required evidence: [${policy.evidenceRequired.join(", ")}]`,
          lane,
          tool,
          timestamp,
        };
      }
    }

    return {
      action: "allow",
      reason: `Tool '${tool}' is allowed in lane '${lane}'`,
      lane,
      tool,
      timestamp,
    };
  }

  private hasRequiredEvidence(evidence: unknown, requiredKeys: readonly string[]): boolean {
    if (!evidence || typeof evidence !== "object") {
      return false;
    }

    const evidenceMap = evidence as Record<string, unknown>;
    return requiredKeys.every((key) => key in evidenceMap);
  }
}
