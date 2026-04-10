import type { ToolRegistration } from "../../interfaces/mcp.js";
import type { PolicyDecision } from "../../interfaces/policy.js";
import type { MutationCheck } from "../../interfaces/security.js";
import type { ToolFabricResult } from "../../governance/tool-fabric.js";
import type { TrustDecision } from "../../security/trust-review.js";

export interface PolicyEvaluateDeps {
  readonly evaluatePolicy: (request: {
    readonly tool: string;
    readonly input: Readonly<Record<string, unknown>>;
  }) => Promise<PolicyDecision>;
}

export interface MutationGateDeps {
  readonly checkMutationAllowed: (
    tool: string,
    filePath: string | null,
    projectDir: string,
    lockId: string | null,
    exemption: string | null,
    command: string | null,
    runId: string,
  ) => Promise<MutationCheck>;
  readonly projectDir: string;
}

export interface ToolFabricDeps {
  readonly evaluateRequest: (
    tool: string,
    args: Record<string, unknown>,
    lane?: string,
  ) => Promise<ToolFabricResult>;
}

export interface TrustReviewDeps {
  readonly scoreTrustChange: (event: {
    readonly type: string;
    readonly count: number;
  }) => number;
  readonly getTrustDecision: (totalScore: number) => TrustDecision;
}

function asRecord(value: unknown): Readonly<Record<string, unknown>> {
  if (typeof value === "object" && value !== null) {
    return value as Readonly<Record<string, unknown>>;
  }
  return {};
}

function requireToolName(value: unknown): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error("tool must be a non-empty string");
  }

  return value.trim();
}

function requireInputRecord(value: unknown): Readonly<Record<string, unknown>> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("input must be an object");
  }

  return value as Readonly<Record<string, unknown>>;
}

function mapPolicyAction(action: PolicyDecision["action"]): "allow" | "block" {
  return action === "allow" || action === "warn" ? "allow" : "block";
}

export function createPolicyEvaluateTool(
  deps: PolicyEvaluateDeps,
): ToolRegistration {
  return {
    name: "omg_policy_evaluate",
    description: "Evaluate bash/file/artifact policy for a tool invocation",
    inputSchema: {
      type: "object",
      properties: {
        tool: {
          type: "string",
          description: "Tool name to evaluate (e.g. Bash, Read, Write)",
        },
        input: {
          type: "object",
          properties: {
            command: {
              type: "string",
              description: "Bash command to evaluate",
            },
            file_path: {
              type: "string",
              description: "File path to evaluate",
            },
          },
          description: "Tool input context",
        },
      },
      required: ["tool", "input"],
    },
    handler: async (args) => {
      const tool = requireToolName(args.tool);
      const input = requireInputRecord(args.input);
      const decision = await deps.evaluatePolicy({ tool, input });
      return {
        action: mapPolicyAction(decision.action),
        reason: decision.reason,
      };
    },
  };
}

export function createMutationGateTool(
  deps: MutationGateDeps,
): ToolRegistration {
  return {
    name: "omg_mutation_gate",
    description:
      "Check if a file or command mutation is allowed by the mutation gate",
    inputSchema: {
      type: "object",
      properties: {
        tool: {
          type: "string",
          description: "Tool name (e.g. Write, Edit, Bash)",
        },
        file_path: {
          type: "string",
          description: "File path being mutated",
        },
        command: {
          type: "string",
          description: "Bash command being executed",
        },
        run_id: {
          type: "string",
          description: "Current run identifier",
        },
      },
      required: ["tool"],
    },
    handler: async (args) => {
      const tool = String(args.tool ?? "");
      const filePath = args.file_path != null ? String(args.file_path) : null;
      const command = args.command != null ? String(args.command) : null;
      const runId = String(args.run_id ?? "anonymous");

      const result = await deps.checkMutationAllowed(
        tool,
        filePath,
        deps.projectDir,
        null,
        null,
        command,
        runId,
      );

      return {
        allowed: result.allowed,
        reason: result.reason,
      };
    },
  };
}

export function createToolFabricRequestTool(
  deps: ToolFabricDeps,
): ToolRegistration {
  return {
    name: "omg_tool_fabric_request",
    description:
      "Evaluate whether a tool is allowed in a given governance lane",
    inputSchema: {
      type: "object",
      properties: {
        tool: {
          type: "string",
          description: "Tool name to evaluate",
        },
        lane: {
          type: "string",
          description: "Governance lane (default: 'default')",
        },
      },
      required: ["tool"],
    },
    handler: async (args) => {
      const tool = String(args.tool ?? "");
      const lane = args.lane != null ? String(args.lane) : undefined;
      const result = await deps.evaluateRequest(tool, {}, lane);

      return {
        allowed: result.action === "allow",
        lane: result.lane,
        reason: result.reason,
      };
    },
  };
}

export function createTrustReviewTool(deps: TrustReviewDeps): ToolRegistration {
  return {
    name: "omg_trust_review",
    description:
      "Review configuration changes for trust risk and return a risk-based decision",
    inputSchema: {
      type: "object",
      properties: {
        config_changes: {
          type: "object",
          description:
            "Map of change types to counts (e.g. {mcp_server_added: 2})",
          additionalProperties: { type: "number" },
        },
      },
      required: ["config_changes"],
    },
    handler: async (args) => {
      const changes = asRecord(args.config_changes);
      let totalScore = 0;

      for (const [type, count] of Object.entries(changes)) {
        const numCount = typeof count === "number" ? count : 1;
        totalScore += deps.scoreTrustChange({ type, count: numCount });
      }

      return {
        decision: deps.getTrustDecision(totalScore),
        score: totalScore,
      };
    },
  };
}
