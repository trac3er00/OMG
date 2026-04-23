import { readdir, stat } from "node:fs/promises";
import { basename, extname, join } from "node:path";
import type { WowResult } from "../output.js";

export interface RefactorSuggestion {
  type: "structure" | "naming" | "duplication" | "complexity";
  description: string;
  path?: string;
  priority: "low" | "medium" | "high";
}

export interface RefactorDiffPreview {
  path: string;
  reason: string;
  diff: string;
}

export interface RefactorResult extends WowResult {
  suggestions: RefactorSuggestion[];
  filesAnalyzed: number;
  diffPreview: RefactorDiffPreview[];
}

interface RepoScan {
  rootFiles: string[];
  rootDirs: string[];
  filePaths: string[];
  fileSizes: Array<{ path: string; size: number }>;
}

const DIRECTORY_IGNORELIST = new Set([
  ".git",
  ".idea",
  ".next",
  ".sisyphus",
  ".turbo",
  ".vscode",
  "coverage",
  "dist",
  "node_modules",
]);

const ROOT_SCRIPT_EXTENSIONS = new Set([".js", ".jsx", ".ts", ".tsx"]);
const LARGE_FILE_BYTES = 50_000;
const MAX_FILES_TO_ANALYZE = 500;

function getNamingStyle(
  filePath: string,
): "kebab" | "snake" | "camel" | "pascal" | null {
  const name = basename(filePath, extname(filePath));
  if (!name) return null;
  if (name.includes("-")) return "kebab";
  if (name.includes("_")) return "snake";
  if (/^[A-Z][A-Za-z0-9]*$/.test(name)) return "pascal";
  if (/^[a-z][A-Za-z0-9]*$/.test(name) && /[A-Z]/.test(name)) return "camel";
  return null;
}

function renderDiffPreview(
  goal: string,
  suggestion: RefactorSuggestion,
): RefactorDiffPreview {
  const targetPath = suggestion.path ?? ".wow-refactor-plan";
  const summaryLine = `${suggestion.priority.toUpperCase()} ${suggestion.type}: ${suggestion.description}`;
  return {
    path: targetPath,
    reason: `Preview only for goal: ${goal}`,
    diff: [
      `diff --git a/${targetPath} b/${targetPath}`,
      `--- a/${targetPath}`,
      `+++ b/${targetPath}`,
      "@@",
      `+# ${summaryLine}`,
      "+# Preview only - this flow does not apply changes.",
    ].join("\n"),
  };
}

async function collectRepoScan(repoDir: string): Promise<RepoScan> {
  const rootEntries = await readdir(repoDir, { withFileTypes: true });
  const scan: RepoScan = {
    rootFiles: rootEntries
      .filter((entry) => entry.isFile())
      .map((entry) => entry.name),
    rootDirs: rootEntries
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name),
    filePaths: [],
    fileSizes: [],
  };

  const queue = rootEntries
    .filter(
      (entry) => entry.isDirectory() && !DIRECTORY_IGNORELIST.has(entry.name),
    )
    .map((entry) => join(repoDir, entry.name));

  for (const file of scan.rootFiles) {
    const filePath = join(repoDir, file);
    const info = await stat(filePath);
    scan.filePaths.push(file);
    scan.fileSizes.push({ path: file, size: info.size });
  }

  while (queue.length > 0 && scan.filePaths.length < MAX_FILES_TO_ANALYZE) {
    const currentDir = queue.shift();
    if (!currentDir) continue;
    const entries = await readdir(currentDir, { withFileTypes: true });

    for (const entry of entries) {
      if (scan.filePaths.length >= MAX_FILES_TO_ANALYZE) break;

      const entryPath = join(currentDir, entry.name);
      const relativePath = entryPath.slice(repoDir.length + 1);

      if (entry.isDirectory()) {
        if (!DIRECTORY_IGNORELIST.has(entry.name)) {
          queue.push(entryPath);
        }
        continue;
      }

      if (!entry.isFile()) continue;

      const info = await stat(entryPath);
      scan.filePaths.push(relativePath);
      scan.fileSizes.push({ path: relativePath, size: info.size });
    }
  }

  return scan;
}

async function analyzeRepo(
  repoDir: string,
): Promise<Pick<RefactorResult, "suggestions" | "filesAnalyzed">> {
  const suggestions: RefactorSuggestion[] = [];

  try {
    const scan = await collectRepoScan(repoDir);
    const namingStyles = new Set(
      scan.filePaths
        .map((filePath) => getNamingStyle(filePath))
        .filter((style): style is NonNullable<typeof style> => style !== null),
    );

    if (!scan.rootFiles.includes("README.md")) {
      suggestions.push({
        type: "structure",
        description: "Missing README.md",
        path: "README.md",
        priority: "high",
      });
    }

    if (!scan.rootFiles.includes(".gitignore")) {
      suggestions.push({
        type: "structure",
        description: "Missing .gitignore",
        path: ".gitignore",
        priority: "medium",
      });
    }

    const rootScriptFiles = scan.rootFiles.filter((file) =>
      ROOT_SCRIPT_EXTENSIONS.has(extname(file)),
    );
    if (rootScriptFiles.length > 10) {
      suggestions.push({
        type: "structure",
        description:
          "Consider organizing root-level source files into subdirectories",
        priority: "low",
      });
    }

    if (
      scan.rootDirs.includes("node_modules") &&
      !scan.rootFiles.includes(".gitignore")
    ) {
      suggestions.push({
        type: "structure",
        description: "node_modules should be in .gitignore",
        path: ".gitignore",
        priority: "high",
      });
    }

    if (namingStyles.size > 1) {
      suggestions.push({
        type: "naming",
        description: `Inconsistent file naming styles detected: ${Array.from(namingStyles).sort().join(", ")}`,
        priority: "medium",
      });
    }

    const duplicateBasenames = new Map<string, string[]>();
    for (const filePath of scan.filePaths) {
      const key = basename(filePath);
      const matches = duplicateBasenames.get(key) ?? [];
      matches.push(filePath);
      duplicateBasenames.set(key, matches);
    }

    for (const [name, paths] of duplicateBasenames.entries()) {
      if (paths.length > 1) {
        suggestions.push({
          type: "duplication",
          description: `Duplicate file basename found for ${name}`,
          path: paths[0],
          priority: "medium",
        });
      }
    }

    const largeFiles = scan.fileSizes
      .filter((file) => file.size >= LARGE_FILE_BYTES)
      .sort((left, right) => right.size - left.size)
      .slice(0, 3);

    for (const file of largeFiles) {
      suggestions.push({
        type: "complexity",
        description: `Large file may benefit from decomposition (${file.size} bytes)`,
        path: file.path,
        priority: file.size >= LARGE_FILE_BYTES * 2 ? "high" : "medium",
      });
    }

    return {
      suggestions,
      filesAnalyzed: scan.filePaths.length,
    };
  } catch {
    return {
      suggestions,
      filesAnalyzed: 0,
    };
  }
}

export async function runRefactorFlow(
  goal: string,
  repoDir: string,
): Promise<RefactorResult> {
  const startTime = Date.now();
  const { suggestions, filesAnalyzed } = await analyzeRepo(repoDir);

  return {
    flowName: "refactor",
    success: true,
    proofScore: 60,
    buildTime: Date.now() - startTime,
    suggestions,
    filesAnalyzed,
    diffPreview: suggestions.map((suggestion) =>
      renderDiffPreview(goal, suggestion),
    ),
  };
}
