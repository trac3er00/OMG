import { appendJsonLine } from "../state/atomic-io.js";
import { StateResolver } from "../state/state-resolver.js";
import { join } from "node:path";
import { existsSync, readFileSync } from "node:fs";
import { GovernanceGraphRuntime, type EnforcementMode } from "./graph.js";
import { detectCollusion } from "./collusion.js";
import { GovernanceLedger } from "./ledger.js";
import {
  GovernanceBlockError,
  DEFAULT_ENFORCEMENT,
  type GovernanceEnforcement,
  type ForceOverrideRecord,
} from "./enforcement.js";

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

export interface GovernanceCheckResult {
  readonly allowed: boolean;
  readonly mode: EnforcementMode;
  readonly warnings: string[];
  readonly ledgerEntry: string;
}

type ToolExecutor = (
  tool: string,
  args: Readonly<Record<string, unknown>>,
) => unknown | Promise<unknown>;

interface ToolFabricDeps {
  readonly appendLedgerLine?: (path: string, entry: LedgerEntry) => void;
}

export interface ToolFabricExecuteOptions {
  readonly enforcement?: GovernanceEnforcement;
  readonly force?: boolean;
  readonly onForceOverride?: (record: ForceOverrideRecord) => void;
}

export class ToolFabric {
  private readonly lanes = new Map<string, LanePolicy>();
  private readonly ledgerPath: string;
  private readonly governanceGraph: GovernanceGraphRuntime;
  private readonly governanceLedger: GovernanceLedger;
  private readonly appendLedgerLine: (path: string, entry: LedgerEntry) => void;

  constructor(projectDir: string, deps: ToolFabricDeps = {}) {
    const resolver = new StateResolver(projectDir);
    this.ledgerPath = resolver.resolve(join("ledger", "tool-fabric.jsonl"));
    this.governanceGraph = new GovernanceGraphRuntime(
      projectDir,
      "tool-fabric",
    );
    this.governanceLedger = new GovernanceLedger(projectDir);
    this.appendLedgerLine = deps.appendLedgerLine ?? appendJsonLine;
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

    this.appendLedgerLine(this.ledgerPath, entry);

    return result;
  }

  async executeTool(
    tool: string,
    args: Record<string, unknown>,
    laneName = "default",
    executor?: ToolExecutor,
    opts: ToolFabricExecuteOptions = {},
  ): Promise<ToolExecutionResult> {
    const decision = await this.evaluateRequest(tool, args, laneName);

    if (decision.action === "deny") {
      return this.applyExecutionEnforcement(decision, tool, opts);
    }

    if (decision.action !== "allow" || !executor) {
      return { decision };
    }

    const output = await executor(tool, args);
    return { decision, output };
  }

  async preDispatchGovernanceCheck(
    agents: string[],
    taskId: string,
  ): Promise<GovernanceCheckResult> {
    const normalizedAgents = [
      ...new Set(agents.map((agent) => agent.trim()).filter(Boolean)),
    ];
    for (const agentId of normalizedAgents) {
      if (this.governanceGraph.getNode(agentId) == null) {
        this.governanceGraph.addNode(agentId);
      }
    }

    const validation =
      this.governanceGraph.validateAgentCombination(normalizedAgents);
    const collusion = detectCollusion(normalizedAgents, {
      ledger: this.governanceLedger,
      taskId,
      mode: validation.mode,
    });
    const warnings = [...validation.warnings, ...validation.violations];

    if (collusion.detected) {
      warnings.push(
        `collusion detected: ${collusion.pattern ?? "unknown pattern"}`,
        "elevated approval required",
      );
    }

    const advisory = validation.mode === "advisory";
    const blocked =
      !advisory && (!validation.allowed || collusion.action === "block");

    if (advisory && warnings.length > 0) {
      console.warn(
        `[governance] advisory pre-dispatch warning for ${taskId}: ${warnings.join("; ")}`,
      );
    }

    const ledgerEntry = this.governanceLedger.append({
      agent_id: "tool-fabric-governance",
      node_id: taskId,
      from_state: "planning",
      to_state: blocked ? "blocked" : "planning",
      evidence_refs: [
        `mode:${validation.mode}`,
        `agents:${normalizedAgents.join(",")}`,
        ...warnings.map((warning) => `warning:${warning}`),
      ],
    });

    return {
      allowed: !blocked,
      mode: validation.mode,
      warnings,
      ledgerEntry: ledgerEntry.entry_id,
    };
  }

  getLedgerEntries(): readonly LedgerEntry[] {
    if (!existsSync(this.ledgerPath)) {
      return [];
    }

    return readFileSync(this.ledgerPath, "utf8")
      .split("\n")
      .filter((line) => line.trim().length > 0)
      .map((line, index) => {
        try {
          return JSON.parse(line) as LedgerEntry;
        } catch (error) {
          const message =
            error instanceof Error ? error.message : String(error);
          throw new Error(
            `Failed to parse tool fabric ledger entry ${index + 1}: ${message}`,
          );
        }
      });
  }

  close(): void {
    // no-op: retained for API parity
  }

  private applyExecutionEnforcement(
    decision: ToolFabricResult,
    tool: string,
    opts: ToolFabricExecuteOptions,
  ): ToolExecutionResult {
    const enforcement = opts.enforcement ?? DEFAULT_ENFORCEMENT;

    if (opts.force) {
      const record: ForceOverrideRecord = {
        gate: "ToolFabric",
        tool,
        reason: decision.reason,
        timestamp: new Date().toISOString(),
        override: "force",
      };
      opts.onForceOverride?.(record);
      return {
        decision: {
          ...decision,
          action: "warn",
          reason: `FORCE OVERRIDE: ${decision.reason}`,
        },
      };
    }

    if (enforcement === "enforced") {
      throw new GovernanceBlockError("ToolFabric", decision.reason);
    }

    return { decision };
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

  private hasRequiredEvidence(
    evidence: unknown,
    requiredKeys: readonly string[],
  ): boolean {
    if (!evidence || typeof evidence !== "object") {
      return false;
    }

    const evidenceMap = evidence as Record<string, unknown>;
    return requiredKeys.every((key) => key in evidenceMap);
  }
}
