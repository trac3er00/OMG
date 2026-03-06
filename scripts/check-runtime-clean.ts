#!/usr/bin/env bun
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { ROOT_DIR } from "../runtime/common.ts";

const DOT = String.fromCharCode(46);
const DASH = String.fromCharCode(45);

function fromCodes(...codes: number[]) {
  return String.fromCharCode(...codes);
}

function escapeRegex(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const PY = `${DOT}${fromCodes(112, 121)}`;
const PYTHON = fromCodes(112, 121, 116, 104, 111, 110);
const PYTEST = fromCodes(112, 121, 116, 101, 115, 116);
const OMG_PY = `scripts/omg${PY}`;
const CHECK_DIRS = [
  ".github",
  ".claude-plugin",
  "commands",
  "control_plane",
  "hooks",
  "hud",
  "lab",
  "omg_natives",
  "plugins",
  "registry",
  "runtime",
  "scripts",
  "tools",
  "README.md",
  "settings.json",
  "package.json",
  "OMG-setup.sh"
];
const SKIP_FILES = new Set(["scripts/check-runtime-clean.ts", "bun.lock"]);
const BLOCKED_EXTENSIONS = [PY];
const BLOCKED_PATTERNS = [
  new RegExp(`\\b${escapeRegex(PYTHON)}3?\\b`, "i"),
  new RegExp(`\\b${escapeRegex(PYTEST)}\\b`, "i"),
  new RegExp(escapeRegex(OMG_PY)),
  new RegExp(escapeRegex(PY)),
  /\bopencode\b/i,
  /\bOpenCode\b/
];

function walk(path: string, files: string[] = []): string[] {
  const full = join(ROOT_DIR, path);
  const stats = statSync(full);
  if (stats.isFile()) {
    files.push(path);
    return files;
  }
  for (const entry of readdirSync(full)) {
    if (entry === "build" || entry === "node_modules" || entry === ".git") {
      continue;
    }
    walk(join(path, entry), files);
  }
  return files;
}

function main() {
  const files = CHECK_DIRS.flatMap((path) => walk(path));
  const violations: string[] = [];
  for (const file of files) {
    if (SKIP_FILES.has(file)) {
      continue;
    }
    if (BLOCKED_EXTENSIONS.some((extension) => file.endsWith(extension))) {
      violations.push(`blocked extension: ${file}`);
      continue;
    }
    const content = readFileSync(join(ROOT_DIR, file), "utf8");
    for (const pattern of BLOCKED_PATTERNS) {
      if (pattern.test(content)) {
        violations.push(`blocked content in ${file}: ${pattern}`);
      }
    }
  }
  if (violations.length > 0) {
    process.stderr.write(`${violations.join("\n")}\n`);
    return 1;
  }
  return 0;
}

if (import.meta.main) {
  process.exit(main());
}
