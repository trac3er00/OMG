import { realpathSync } from "node:fs";
import { basename, normalize } from "node:path";

export type PolicyDecision = {
  action: "allow" | "ask" | "deny";
  risk_level: "low" | "med" | "high" | "critical";
  reason: string;
  controls: string[];
};

const DESTRUCTIVE_PATTERNS: Array<[RegExp, string]> = [
  [/rm\s+-[A-Za-z]*r[A-Za-z]*f[A-Za-z]*\s+\/(\s|$|\*)/, "rm -rf /"],
  [/rm\s+-[A-Za-z]*r[A-Za-z]*f[A-Za-z]*\s+~\/?(\s|$|\*)/, "rm -rf ~"],
  [/:\(\)\s*\{\s*:\|:&\s*\}\s*;:/, "fork bomb"],
  [/sudo\s+(dd|mkfs|fdisk|parted|wipefs)\b/, "destructive disk op"],
  [/sudo\s+rm\b/, "sudo rm"]
];

const PIPE_TO_SHELL = [
  /(curl|wget)\s+.*\|\s*(sudo\s+)?(ba)?sh/,
  /(curl|wget)\s+.*\|\s*(bun|node)\b/,
  /base64\s+.*\|\s*(ba)?sh/
];

const SECRET_PATTERNS = [
  /\.(env|pem|key|p12|pfx|jks|keystore|netrc|npmrc|pypirc)\b/i,
  /\/\.aws\/(credentials|config)\b/i,
  /\/\.kube\/config\b/i,
  /\/id_(rsa|ed25519|ecdsa)\b/i,
  /\/\.ssh\//i,
  /\bsecrets?\//i
];

const SECRET_FILE_NAMES = new Set([
  ".env",
  ".env.local",
  ".env.development",
  ".env.production",
  ".env.staging",
  ".env.test",
  ".npmrc",
  ".netrc",
  "id_rsa",
  "id_ed25519",
  "id_ecdsa",
  "id_rsa.pub",
  "id_ed25519.pub",
  "id_ecdsa.pub"
]);

const EXAMPLE_ENV_FILES = new Set([".env.example", ".env.sample", ".env.template"]);

const SENSITIVE_PATH_PATTERNS = [
  /\/\.aws\/(credentials|config)$/i,
  /\/\.kube\/config$/i,
  /\/\.ssh\//i,
  /\/\.gnupg\//i,
  /\/secrets?\//i,
  /\.(pem|key|p12|pfx|jks|keystore)$/i,
  /(^|\/)secret[s]?\./i,
  /(^|\/)credential[s]?\./i,
  /(^|\/)password[s]?\./i,
  /(^|\/)token[s]?\./i,
  /(^|\/)\.docker\/config\.json$/i,
  /(^|\/)\.git-credentials$/i
];

function decision(
  action: PolicyDecision["action"],
  risk_level: PolicyDecision["risk_level"],
  reason: string,
  controls: string[] = []
): PolicyDecision {
  return { action, risk_level, reason, controls };
}

export function evaluateBashCommand(command: string): PolicyDecision {
  if (!command.trim()) {
    return decision("allow", "low", "empty command");
  }
  for (const [pattern, label] of DESTRUCTIVE_PATTERNS) {
    if (pattern.test(command)) {
      return decision("deny", "critical", `Blocked: ${label}`, ["destructive-op"]);
    }
  }
  for (const pattern of PIPE_TO_SHELL) {
    if (pattern.test(command)) {
      return decision("deny", "critical", "Blocked: pipe-to-shell", ["remote-code-exec"]);
    }
  }
  if (/\beval\s+["'$`]/.test(command)) {
    return decision("deny", "high", "Blocked: dynamic eval", ["dynamic-eval"]);
  }
  for (const pattern of SECRET_PATTERNS) {
    if (pattern.test(command) && /\b(cat|less|more|head|tail|grep|awk|bun|node)\b/i.test(command)) {
      return decision("deny", "critical", "Blocked: reading secret file", ["secret-access"]);
    }
  }
  if (/\b(curl|wget|ssh|scp|rsync)\b/.test(command)) {
    return decision("ask", "med", `Network or remote operation: ${command.slice(0, 120)}`, ["human-approval"]);
  }
  if (/\bgit\s+push\b.*(--force|-f)/.test(command)) {
    return decision("ask", "med", "Force push", ["human-approval"]);
  }
  return decision("allow", "low", "command allowed");
}

function safeRealPath(path: string): string {
  try {
    return realpathSync(path);
  } catch {
    return normalize(path);
  }
}

export function evaluateFileAccess(tool: string, filePath: string): PolicyDecision {
  if (!filePath.trim()) {
    return decision("allow", "low", "no file");
  }

  const normalizedPath = safeRealPath(filePath);
  const fileName = basename(normalizedPath).toLowerCase();

  if (EXAMPLE_ENV_FILES.has(fileName) && ["Write", "Edit", "MultiEdit"].includes(tool)) {
    return decision("deny", "high", `Modifying example env file blocked: ${filePath}`, ["immutable-env-template"]);
  }

  if (SECRET_FILE_NAMES.has(fileName)) {
    return decision("deny", "critical", `Secret file blocked: ${filePath}`, ["secret-access"]);
  }

  if (/^\.env(\..+)?$/i.test(fileName) && !EXAMPLE_ENV_FILES.has(fileName)) {
    return decision("deny", "critical", `Environment file blocked: ${filePath}`, ["secret-access"]);
  }

  for (const pattern of SENSITIVE_PATH_PATTERNS) {
    if (pattern.test(normalizedPath)) {
      return decision("deny", "critical", `Sensitive path blocked: ${filePath}`, ["secret-access"]);
    }
  }

  return decision("allow", "low", "file allowed");
}

export function toPretoolHookOutput(decisionValue: PolicyDecision): Record<string, unknown> | null {
  if (decisionValue.action === "allow") {
    return null;
  }
  return {
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: decisionValue.action,
      permissionDecisionReason: decisionValue.reason
    }
  };
}
