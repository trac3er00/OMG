import type { PolicyDecision } from "../interfaces/policy.js";
import { evaluateBashCommand, evaluateFileAccess } from "./firewall.js";

export interface PolicyRequest {
  readonly tool: string;
  readonly input: Readonly<Record<string, unknown>>;
}

const FILE_GUARDED_TOOLS = new Set(["Read", "Write", "Edit", "MultiEdit"]);

export async function evaluatePolicy(request: PolicyRequest): Promise<PolicyDecision> {
  const { tool, input } = request;

  if (tool === "Bash") {
    const command = String(input["command"] ?? "");
    return evaluateBashCommand(command);
  }

  if (FILE_GUARDED_TOOLS.has(tool)) {
    const filePath = String(input["file_path"] ?? input["path"] ?? "");
    if (filePath) {
      return evaluateFileAccess(tool, filePath);
    }
  }

  return {
    action: "allow",
    reason: "No policy violation detected",
    riskLevel: "low",
    tags: ["policy-engine"],
  };
}
