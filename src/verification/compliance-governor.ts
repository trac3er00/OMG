export type CommandClass =
  | "test"
  | "build"
  | "vcs"
  | "read"
  | "write"
  | "network"
  | "destructive"
  | "unknown";

export type BashCommandMode = "read" | "mutation" | "external";

const COMMAND_CLASSIFIERS: ReadonlyArray<{
  readonly pattern: RegExp;
  readonly cls: CommandClass;
}> = [
  { pattern: /\b(bun\s+test|pytest|npm\s+test|jest|mocha|vitest)\b/, cls: "test" },
  { pattern: /\b(bun\s+build|npm\s+run\s+build|tsc\s+--build|cargo\s+build)\b/, cls: "build" },
  { pattern: /\bgit\s+(commit|push|pull|merge|rebase|tag|branch)\b/, cls: "vcs" },
  { pattern: /\b(ls|cat|grep|find|head|tail|less|more|wc|diff)\b/, cls: "read" },
  { pattern: /\b(curl|wget|fetch|npm\s+install|bun\s+install)\b/, cls: "network" },
  { pattern: /\b(rm\s+-rf?|shred|dd\s+if=|mkfs)\b/, cls: "destructive" },
  { pattern: /\b(echo|tee|cp|mv|mkdir|touch|chmod|chown)\b/, cls: "write" },
];

const MUTATION_BASH_PATTERNS: readonly RegExp[] = [
  /\b(git\s+(add|commit|push|rebase|cherry-pick|merge|tag(?!\s+(-l|--list)\b)))\b/,
  /\b(rm|mv|cp|tee|touch|mkdir|rmdir|ln)\b/,
  /\b(sed\s+-i|perl\s+-pi)\b/,
  /\b(chmod|chown)\b/,
];

const EXTERNAL_BASH_PATTERNS: readonly RegExp[] = [
  /(?:^|[\s;&|()])(curl|wget)\b/,
  /(?:^|[\s;&|()])(ssh|scp|rsync)\b/,
  /\bgit\s+(clone|fetch|pull)\b/,
];

export function classifyBashCommand(command: string): CommandClass {
  for (const { pattern, cls } of COMMAND_CLASSIFIERS) {
    if (pattern.test(command)) return cls;
  }
  return "unknown";
}

export interface ComplianceCheck {
  readonly allowed: boolean;
  readonly commandClass: CommandClass;
  readonly reason: string;
}

export function checkCommandCompliance(command: string): ComplianceCheck {
  const commandClass = classifyBashCommand(command);
  const blocked = commandClass === "destructive";
  return {
    allowed: !blocked,
    commandClass,
    reason: blocked
      ? `Destructive command blocked: ${command}`
      : `Command class '${commandClass}' is allowed`,
  };
}

export function classifyBashCommandMode(command: string): BashCommandMode {
  const normalized = (command ?? "").trim();
  if (!normalized) return "read";

  const lowered = normalized.toLowerCase();

  for (const pattern of MUTATION_BASH_PATTERNS) {
    if (pattern.test(lowered)) return "mutation";
  }

  for (const pattern of EXTERNAL_BASH_PATTERNS) {
    if (pattern.test(lowered)) return "external";
  }

  return "read";
}
