import type { MutationCheck } from "../interfaces/security.js";
import type { MutationOperation, PolicyDecision } from "../interfaces/policy.js";

export const MUTATION_CAPABLE_TOOLS = new Set(["Write", "Edit", "MultiEdit", "Bash", "TodoWrite"]);

const CRITICAL_FILE_PATTERNS = [
  /^\.env($|\.|\/)/,
  /\.(env|secret|secrets|credentials|creds|private)(\.|$)/i,
  /(^|\/)id_(rsa|ed25519|ecdsa|dsa)$/,
  /(^|\/)credentials\.json$/i,
  /(^|\/)\.aws\//,
  /(^|\/)(passwords?|keystore|keychain)\./i,
  /\.(pem|key|p12|pfx|crt|cer)$/,
  /(^|\/)\.ssh\//,
  /\bAWS_SECRET\b/i,
];

const BASH_MUTATION_PATTERNS = [
  /\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\b|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r?\b/,
  /\bdd\s+if=/,
  /\bmkfs\b/,
  /\bshred\b/,
  /curl\s+.*\|\s*(ba)?sh/,
  /wget\s+.*\|\s*(ba)?sh/,
  /\|\s*bash\b/,
  /\|\s*sh\b/,
  /\bfork\s*bomb\b|\(\s*\)\s*\{\s*.*\|\s*&\s*\}/,
  /:\s*\(\s*\)\s*\{.*\}/,
  /\bsed\s+-i\b/,
  /\bperl\s+-i\b/,
  /\bchmod\s+(777|a\+[rwx])/,
  /\bchown\s+-R/,
  /\bsudo\s+rm/,
  /\btruncate\b/,
  />\s*\/dev\/(sda|sdb|hda|null)\b/,
];

export function isMutationCapableTool(tool: string): boolean {
  return MUTATION_CAPABLE_TOOLS.has(tool);
}

export function isCriticalFilePath(filePath: string): boolean {
  const normalized = filePath.replaceAll("\\", "/");
  return CRITICAL_FILE_PATTERNS.some((pattern) => pattern.test(normalized));
}

export function hasBashMutationPattern(command: string): boolean {
  return BASH_MUTATION_PATTERNS.some((pattern) => pattern.test(command));
}

function operationForTool(tool: string): MutationOperation {
  if (tool === "Edit") {
    return "edit";
  }
  if (tool === "MultiEdit") {
    return "multiedit";
  }
  if (tool === "Bash") {
    return "bash_mutation";
  }
  return "write";
}

function makeDecision(
  action: "allow" | "deny",
  reason: string,
  riskLevel: "low" | "medium" | "high" | "critical",
  runId: string,
): PolicyDecision {
  return {
    action,
    reason,
    riskLevel,
    tags: ["mutation-gate"],
    ...(runId ? { metadata: { runId } } : {}),
  };
}

export async function checkMutationAllowed(
  tool: string,
  filePath: string | null,
  projectDir: string,
  lockId: string | null,
  exemption: string | null,
  command: string | null,
  runId: string,
): Promise<MutationCheck> {
  const operation = operationForTool(tool);
  void projectDir;
  void lockId;

  if (!isMutationCapableTool(tool)) {
    return {
      allowed: true,
      reason: "Tool is not mutation-capable",
      operation,
      decision: makeDecision("allow", "Non-mutation tool", "low", runId),
      riskScore: 0,
    };
  }

  if (exemption) {
    return {
      allowed: true,
      reason: `Mutation allowed via exemption: ${exemption}`,
      operation,
      exemption,
      decision: makeDecision("allow", "Exemption granted", "medium", runId),
      riskScore: 30,
    };
  }

  if (tool === "Bash" && command && hasBashMutationPattern(command)) {
    return {
      allowed: false,
      reason: "Blocked: destructive or dangerous bash pattern detected in command",
      operation,
      decision: makeDecision("deny", "Destructive bash pattern", "critical", runId),
      riskScore: 100,
    };
  }

  if (filePath && isCriticalFilePath(filePath)) {
    return {
      allowed: false,
      reason: `Blocked: mutation to critical file '${filePath}' is not allowed`,
      operation,
      decision: makeDecision("deny", "Critical file protection", "critical", runId),
      riskScore: 95,
    };
  }

  return {
    allowed: true,
    reason: "Mutation allowed",
    operation,
    decision: makeDecision("allow", "Mutation permitted", "low", runId),
    riskScore: 10,
  };
}
