export type PolicyDecision = "allow" | "ask" | "deny";

export interface HookEmulationInput {
  tool: string;
  input: Record<string, unknown>;
}

export interface PolicyResult {
  decision: PolicyDecision;
  reason: string;
  emulated: true;
}

// Security rules equivalent to hooks/firewall.py
const DESTRUCTIVE_BASH_PATTERNS = [
  /rm\s+-rf\s+\//,
  /chmod\s+777/,
  /dd\s+if=/,
  /mkfs\s/,
  /shred\s/,
];

const SUSPICIOUS_BASH_PATTERNS = [
  /\benv\b.*>/,
  /\bprintenv\b/,
  /curl\s+.*\|\s*sh/,
  /wget\s+.*\|\s*sh/,
];

const SENSITIVE_FILE_PATTERNS = [
  /\.env$/,
  /\.key$/,
  /\.pem$/,
  /id_rsa/,
  /credentials/,
  /secret/i,
];

export function evaluatePolicy(opts: HookEmulationInput): PolicyResult {
  const { tool, input } = opts;

  if (tool === "Bash" && typeof input.command === "string") {
    const cmd = input.command;
    for (const pattern of DESTRUCTIVE_BASH_PATTERNS) {
      if (pattern.test(cmd)) {
        return {
          decision: "deny",
          reason: `Destructive command pattern detected: ${pattern.toString()}`,
          emulated: true,
        };
      }
    }
    for (const pattern of SUSPICIOUS_BASH_PATTERNS) {
      if (pattern.test(cmd)) {
        return {
          decision: "ask",
          reason: `Suspicious command pattern requires approval: ${pattern.toString()}`,
          emulated: true,
        };
      }
    }
  }

  if ((tool === "Write" || tool === "Edit") && typeof input.path === "string") {
    const filePath = input.path;
    for (const pattern of SENSITIVE_FILE_PATTERNS) {
      if (pattern.test(filePath)) {
        return {
          decision: "ask",
          reason: `Sensitive file modification requires approval: ${filePath}`,
          emulated: true,
        };
      }
    }
  }

  return { decision: "allow", reason: "No policy violations detected", emulated: true };
}

export function checkMutationGate(opts: HookEmulationInput): PolicyResult {
  const { tool, input } = opts;

  if (tool === "Write" && typeof input.path === "string") {
    const p = input.path;
    if (/^\/(etc|usr|bin|sbin)\//.test(p)) {
      return { decision: "deny", reason: `System directory write blocked: ${p}`, emulated: true };
    }
    if (/\.git\/hooks\//.test(p)) {
      return {
        decision: "ask",
        reason: `Git hook modification requires approval: ${p}`,
        emulated: true,
      };
    }
  }

  return { decision: "allow", reason: "No mutation gate violations", emulated: true };
}

export function runHookEmulation(opts: HookEmulationInput): PolicyResult {
  const policyResult = evaluatePolicy(opts);
  const mutationResult = checkMutationGate(opts);

  // Return most restrictive
  const order: PolicyDecision[] = ["deny", "ask", "allow"];
  if (order.indexOf(policyResult.decision) < order.indexOf(mutationResult.decision)) {
    return policyResult;
  }
  return mutationResult;
}
