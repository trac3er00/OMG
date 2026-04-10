import { existsSync } from "node:fs";
import { join } from "node:path";

export type PackageManager =
  | "npm"
  | "yarn"
  | "pnpm"
  | "bun"
  | "pip"
  | "cargo"
  | "go"
  | "unknown";

export interface PackageManagerCommands {
  readonly install: string;
  readonly run: (script: string) => string;
  readonly test: string;
  readonly build: string;
  readonly add: (pkg: string) => string;
}

export interface DebugSuggestion {
  readonly pattern: string;
  readonly message: string;
  readonly fix: string;
}

const DETECTION_RULES: readonly {
  readonly file: string;
  readonly requires?: string;
  readonly pm: PackageManager;
}[] = [
  { file: "bun.lock", requires: "package.json", pm: "bun" },
  { file: "bun.lockb", requires: "package.json", pm: "bun" },
  { file: "yarn.lock", requires: "package.json", pm: "yarn" },
  { file: "pnpm-lock.yaml", requires: "package.json", pm: "pnpm" },
  { file: "Cargo.toml", pm: "cargo" },
  { file: "go.mod", pm: "go" },
  { file: "pyproject.toml", pm: "pip" },
  { file: "requirements.txt", pm: "pip" },
];

export function detectPackageManager(projectRoot: string): PackageManager {
  const exists = (name: string) => existsSync(join(projectRoot, name));

  for (const rule of DETECTION_RULES) {
    if (exists(rule.file)) {
      if (rule.requires && !exists(rule.requires)) continue;
      return rule.pm;
    }
  }

  if (exists("package.json")) return "npm";

  return "unknown";
}

export function detectPackageManagerFromFiles(
  files: readonly string[],
): PackageManager {
  const set = new Set(files);

  for (const rule of DETECTION_RULES) {
    if (set.has(rule.file)) {
      if (rule.requires && !set.has(rule.requires)) continue;
      return rule.pm;
    }
  }

  if (set.has("package.json")) return "npm";

  return "unknown";
}

export function getCommands(pm: PackageManager): PackageManagerCommands {
  switch (pm) {
    case "npm":
      return {
        install: "npm install",
        run: (s) => `npm run ${s}`,
        test: "npm test",
        build: "npm run build",
        add: (p) => `npm install ${p}`,
      };
    case "yarn":
      return {
        install: "yarn install",
        run: (s) => `yarn ${s}`,
        test: "yarn test",
        build: "yarn build",
        add: (p) => `yarn add ${p}`,
      };
    case "pnpm":
      return {
        install: "pnpm install",
        run: (s) => `pnpm run ${s}`,
        test: "pnpm test",
        build: "pnpm run build",
        add: (p) => `pnpm add ${p}`,
      };
    case "bun":
      return {
        install: "bun install",
        run: (s) => `bun run ${s}`,
        test: "bun test",
        build: "bun run build",
        add: (p) => `bun add ${p}`,
      };
    case "pip":
      return {
        install: "pip install -r requirements.txt",
        run: (s) => `python -m ${s}`,
        test: "pytest",
        build: "python -m build",
        add: (p) => `pip install ${p}`,
      };
    case "cargo":
      return {
        install: "cargo build",
        run: (s) => `cargo run --bin ${s}`,
        test: "cargo test",
        build: "cargo build --release",
        add: (p) => `cargo add ${p}`,
      };
    case "go":
      return {
        install: "go mod download",
        run: (s) => `go run ${s}`,
        test: "go test ./...",
        build: "go build ./...",
        add: (p) => `go get ${p}`,
      };
    default:
      return {
        install: "echo 'unknown package manager'",
        run: (s) => `echo 'cannot run ${s}'`,
        test: "echo 'no test runner detected'",
        build: "echo 'no build tool detected'",
        add: (p) => `echo 'cannot add ${p}'`,
      };
  }
}

interface ErrorPattern {
  readonly regex: RegExp;
  readonly pattern: string;
  readonly message: string;
  readonly fix: (match: RegExpMatchArray, pm: PackageManager) => string;
}

const ERROR_PATTERNS: readonly ErrorPattern[] = [
  {
    regex: /Cannot find module '([^']+)'/,
    pattern: "Cannot find module",
    message: "A required module is missing from your dependencies.",
    fix: (m, pm) => `${getCommands(pm).add(m[1]!)}`,
  },
  {
    regex: /Module not found: (?:Error: )?Can't resolve '([^']+)'/,
    pattern: "Module not found",
    message: "Webpack/bundler cannot resolve a module.",
    fix: (m, pm) => `${getCommands(pm).add(m[1]!)}`,
  },
  {
    regex: /ENOENT[:\s].*no such file or directory.*'([^']+)'/,
    pattern: "ENOENT",
    message: "A file or directory does not exist at the expected path.",
    fix: (m) => `Check that the path exists: ${m[1]}`,
  },
  {
    regex: /ENOENT/,
    pattern: "ENOENT",
    message: "A file or directory does not exist at the expected path.",
    fix: () => "Check the file path referenced in the stack trace.",
  },
  {
    regex: /EACCES[:\s].*permission denied.*'([^']+)'/,
    pattern: "EACCES",
    message: "Permission denied when accessing a file.",
    fix: (m) => `Check permissions for: ${m[1]}`,
  },
  {
    regex: /EACCES/,
    pattern: "EACCES",
    message: "Permission denied when accessing a file.",
    fix: () => "Check file permissions in the referenced path.",
  },
  {
    regex: /EADDRINUSE.*:(\d+)/,
    pattern: "EADDRINUSE",
    message: "The port is already in use by another process.",
    fix: (m) => `Kill the process on port ${m[1]} or use a different port.`,
  },
  {
    regex: /SyntaxError: Unexpected token/,
    pattern: "SyntaxError",
    message: "There is a syntax error in your code or a dependency.",
    fix: () =>
      "Check the file and line referenced in the stack trace for syntax issues.",
  },
  {
    regex: /TypeError: (\w+) is not a function/,
    pattern: "TypeError",
    message: "A value is being called as a function but is not one.",
    fix: (m) =>
      `Verify that '${m[1]}' is correctly imported and is a function.`,
  },
  {
    regex: /ReferenceError: (\w+) is not defined/,
    pattern: "ReferenceError",
    message: "A variable is referenced but not declared.",
    fix: (m) => `Ensure '${m[1]}' is declared or imported before use.`,
  },
  {
    regex: /ERR_MODULE_NOT_FOUND/,
    pattern: "ERR_MODULE_NOT_FOUND",
    message: "Node.js ESM loader cannot find the module.",
    fix: (_m, pm) =>
      `Check import paths and ensure dependencies are installed: ${getCommands(pm).install}`,
  },
  {
    regex: /ENOMEM/,
    pattern: "ENOMEM",
    message: "The system ran out of memory.",
    fix: () =>
      "Increase available memory or reduce the workload. Check for memory leaks.",
  },
  {
    regex: /error\[E(\d+)\]: (.+)/,
    pattern: "Rust compiler error",
    message: "Rust compilation failed.",
    fix: (m) => `Fix Rust error E${m[1]}: ${m[2]}`,
  },
  {
    regex: /cannot find crate for `([^`]+)`/,
    pattern: "Missing Rust crate",
    message: "A Rust crate dependency is missing.",
    fix: (m) => `cargo add ${m[1]}`,
  },
];

export function debugStackTrace(
  trace: string,
  pm: PackageManager = "npm",
): DebugSuggestion[] {
  const suggestions: DebugSuggestion[] = [];
  const seen = new Set<string>();

  for (const ep of ERROR_PATTERNS) {
    const match = trace.match(ep.regex);
    if (match) {
      const key = `${ep.pattern}:${match[0]}`;
      if (seen.has(key)) continue;
      seen.add(key);
      suggestions.push({
        pattern: ep.pattern,
        message: ep.message,
        fix: ep.fix(match, pm),
      });
    }
  }

  return suggestions;
}
