import type { PolicyDecision, RiskLevel } from "../interfaces/policy.js";

const DESTRUCTIVE_BASH_PATTERNS: readonly RegExp[] = [
  /\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f?|-[a-zA-Z]*f[a-zA-Z]*r?)\s+(\/|~|\.\.|\$HOME|\$\{HOME\})/,
  /\brm\s+-rf\b/,
  /\brm\s+-fr\b/,
  /\bdd\s+if=\/dev\/(zero|random|urandom)\s+of=/,
  /\bdd\s+.*of=\/dev\/(sd[a-z]|hd[a-z]|nvme\d+n\d+)/,
  /\bmkfs\./,
  /\bshred\s+-/,
  /\bwipefs\b/,
  /:\s*\(\s*\)\s*\{\s*:\|:&\s*\}\s*;\s*:/,
  /function\s+\w+\s*\(\s*\)\s*\{\s*\w+\s*\|\s*\w+\s*&/,
  />\s*\/dev\/(sda|sdb|sdc|hda|hdb|nvme)\b/,
  /\btc\s+qdisc\s+add.*netem\s+loss\s+100%/,
  /echo\s+.*>\s*\/(proc|sys)\//,
];

const PIPE_TO_SHELL_PATTERNS: readonly RegExp[] = [
  /curl\s[^|]*\|\s*(sudo\s+)?(ba)?sh(\s|$)/i,
  /wget\s[^|]*\|\s*(sudo\s+)?(ba)?sh(\s|$)/i,
  /(curl|wget)\s+[^|]*\|\s*python[23]?(\s|$)/i,
  /(curl|wget)\s+[^|]*\|\s*(perl|ruby)(\s|$)/i,
  /\|\s*bash\s*$/i,
  /\|\s*sh\s*$/i,
  /bash\s+<\s*\(/,
  /sh\s+<\s*\(/,
];

const INJECTION_MARKER_PATTERNS: readonly RegExp[] = [
  /IGNORE\s+(PREVIOUS\s+)?INSTRUCTIONS/i,
  /OVERRIDE\s+(SYSTEM|INSTRUCTIONS)/i,
  /NEW\s+TASK:|SYSTEM\s+OVERRIDE/i,
  /\[INST\]|\[\/INST\]/,
  /<\|im_start\|>|<\|im_end\|>/,
  /ASSISTANT:\s*You\s+are\s+now/i,
];

const CACHE_POISONING_PATTERNS: readonly RegExp[] = [
  /(?:>|>>|tee\b|cp\b|mv\b|rm\b|sed\s+-i\b).{0,120}(?:\/)?\.omg\/state\//i,
  /(?:>|>>|tee\b|cp\b|mv\b|rm\b|sed\s+-i\b).{0,120}(?:\/)?\.omg\/shadow\/active-run/i,
  /\b(?:cache|state)\s*(?:poison|override|overwrite|tamper)\b/i,
];

const SECRET_FILE_PATTERNS: readonly RegExp[] = [
  /(^|\/)\.env(\..+)?$/i,
  /(^|\/)\.aws\/(credentials|config)$/i,
  /(^|\/)\.kube\/config$/i,
  /(^|\/)id_(rsa|ed25519|ecdsa)(\.pub)?$/i,
  /(^|\/)\.ssh\//i,
  /\.(pem|key|p12|pfx|jks|keystore)$/i,
  /(^|\/)secrets?\//i,
  /(^|\/)(credentials?|passwords?|tokens?)\./i,
];

function decision(action: PolicyDecision["action"], reason: string, riskLevel: RiskLevel, tags: readonly string[]): PolicyDecision {
  return { action, reason, riskLevel, tags };
}

function deny(reason: string, riskLevel: RiskLevel = "high"): PolicyDecision {
  return decision("deny", reason, riskLevel, ["firewall"]);
}

function warn(reason: string): PolicyDecision {
  return decision("warn", reason, "medium", ["firewall"]);
}

function allow(): PolicyDecision {
  return decision("allow", "Command allowed", "low", ["firewall"]);
}

function matchesAny(patterns: readonly RegExp[], value: string): boolean {
  return patterns.some((pattern) => pattern.test(value));
}

export async function evaluateBashCommand(command: string): Promise<PolicyDecision> {
  const cmd = String(command ?? "");
  if (!cmd.trim()) {
    return allow();
  }

  if (matchesAny(CACHE_POISONING_PATTERNS, cmd)) {
    return deny("Cache poisoning attempt: writing to .omg/state/ from shell", "critical");
  }

  if (matchesAny(DESTRUCTIVE_BASH_PATTERNS, cmd)) {
    return deny("Destructive bash command blocked", "critical");
  }

  if (matchesAny(PIPE_TO_SHELL_PATTERNS, cmd)) {
    return deny("Pipe-to-shell execution blocked (code injection risk)", "critical");
  }

  if (matchesAny(SECRET_FILE_PATTERNS, cmd)) {
    return deny("Secret file access blocked", "high");
  }

  if (matchesAny(INJECTION_MARKER_PATTERNS, cmd)) {
    return warn("Potential injection marker detected in command");
  }

  return allow();
}

export async function evaluateFileAccess(tool: string, filePath: string): Promise<PolicyDecision> {
  const normalized = String(filePath ?? "").replaceAll("\\", "/").trim();
  if (normalized && matchesAny(SECRET_FILE_PATTERNS, normalized)) {
    return deny(`Secret file access blocked: ${tool} on ${filePath}`, "high");
  }
  return allow();
}
