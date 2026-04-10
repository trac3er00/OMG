import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

import { GapDetector, type Gap, type ProjectScan } from "./gap-detection.js";
import {
  detectPackageManager,
  getCommands,
  type PackageManager,
} from "./pkg-manager.js";
import { ProactiveExecutor, type ExecutionDecision } from "./proactive.js";
import {
  understandIntent,
  type IntentAnalysis,
  type IntentDomain,
} from "../intent/index.js";

const EXCLUDED_DIRECTORIES = new Set([
  ".git",
  "node_modules",
  ".turbo",
  ".next",
  "dist",
  "build",
  "coverage",
]);

const FRONTEND_FILE_PATTERNS: readonly RegExp[] = [
  /components?/i,
  /pages?/i,
  /views?/i,
  /\.tsx$/i,
  /\.jsx$/i,
  /\.vue$/i,
  /\.svelte$/i,
];

const BACKEND_FILE_PATTERNS: readonly RegExp[] = [
  /routes?/i,
  /controllers?/i,
  /handlers?/i,
  /api\//i,
  /server/i,
];

const DATA_FILE_PATTERNS: readonly RegExp[] = [
  /database/i,
  /schema/i,
  /migration/i,
  /prisma/i,
  /drizzle/i,
  /\.sql$/i,
];

export type ProjectType = IntentDomain | "fullstack";

export interface IntentContext {
  readonly prompt: string;
  readonly analysis: IntentAnalysis;
  readonly proactiveDecision: ExecutionDecision;
}

export interface ProjectAnalysis {
  readonly packageManager: PackageManager;
  readonly gaps: Gap[];
  readonly suggestedNextSteps: string[];
  readonly projectType: ProjectType;
  readonly healthScore: number;
  readonly intentContext: IntentContext;
}

function matchesAny(value: string, patterns: readonly RegExp[]): boolean {
  return patterns.some((pattern) => pattern.test(value));
}

function collectProjectScan(root: string): ProjectScan {
  const files: string[] = [];
  const directories: string[] = [];

  const walk = (currentDir: string) => {
    for (const entry of readdirSync(currentDir, { withFileTypes: true })) {
      if (entry.isDirectory() && EXCLUDED_DIRECTORIES.has(entry.name)) {
        continue;
      }

      const absolutePath = join(currentDir, entry.name);
      const relativePath = relative(root, absolutePath).replace(/\\/g, "/");

      if (entry.isDirectory()) {
        directories.push(relativePath);
        walk(absolutePath);
        continue;
      }

      if (entry.isFile()) {
        files.push(relativePath);
      }
    }
  };

  if (existsSync(root)) {
    walk(root);
  }

  const dependencies = readDependencies(root);

  return {
    files,
    directories,
    dependencies,
    hasPackageJson: existsSync(join(root, "package.json")),
  };
}

function readDependencies(root: string): string[] {
  const packageJsonPath = join(root, "package.json");
  if (!existsSync(packageJsonPath)) {
    return [];
  }

  try {
    const raw = JSON.parse(readFileSync(packageJsonPath, "utf8")) as {
      dependencies?: Record<string, string>;
      devDependencies?: Record<string, string>;
    };

    return [
      ...Object.keys(raw.dependencies ?? {}),
      ...Object.keys(raw.devDependencies ?? {}),
    ];
  } catch {
    return [];
  }
}

function buildProjectPrompt(scan: ProjectScan): string {
  const features: string[] = [];
  const items = [...scan.files, ...scan.directories];

  if (items.some((item) => matchesAny(item, BACKEND_FILE_PATTERNS))) {
    features.push("backend api routes");
  }
  if (items.some((item) => matchesAny(item, FRONTEND_FILE_PATTERNS))) {
    features.push("frontend dashboard components");
  }
  if (items.some((item) => matchesAny(item, DATA_FILE_PATTERNS))) {
    features.push("database schema migrations");
  }
  if (scan.files.some((file) => /readme|docs?\//i.test(file))) {
    features.push("documentation guides");
  }

  if (features.length === 0) {
    features.push("project setup");
  }

  return `build ${features.join(" with ")}`;
}

function detectProjectType(
  scan: ProjectScan,
  intent: IntentAnalysis,
): ProjectType {
  const items = [...scan.files, ...scan.directories];
  const hasFrontend = items.some((item) =>
    matchesAny(item, FRONTEND_FILE_PATTERNS),
  );
  const hasBackend = items.some((item) =>
    matchesAny(item, BACKEND_FILE_PATTERNS),
  );

  if (hasFrontend && hasBackend) {
    return "fullstack";
  }

  return intent.domain;
}

function computeHealthScore(gaps: readonly Gap[]): number {
  const penalty = gaps.reduce((total, gap) => {
    switch (gap.severity) {
      case "critical":
        return total + 20;
      case "high":
        return total + 10;
      case "medium":
        return total + 5;
      default:
        return total;
    }
  }, 0);

  return Math.max(0, 100 - penalty);
}

function buildSuggestedNextSteps(
  packageManager: PackageManager,
  gaps: readonly Gap[],
  intentContext: IntentContext,
): string[] {
  const commands = getCommands(packageManager);
  const steps: string[] = [];

  for (const gap of gaps) {
    steps.push(gap.suggestion);
    if (steps.length === 3) {
      return steps;
    }
  }

  if (intentContext.proactiveDecision.mode === "plan") {
    steps.push(
      `Review the recommended execution plan for this ${intentContext.analysis.domain} project before broader changes.`,
    );
  } else if (intentContext.proactiveDecision.mode === "clarify") {
    steps.push(
      `Clarify the project outcome: ${intentContext.proactiveDecision.clarifyingQuestion?.question ?? "define the exact target behavior."}`,
    );
  }

  steps.push(
    `Run ${commands.test} to verify the current baseline before the next change.`,
  );
  steps.push(
    `Run ${commands.build} to confirm the project still builds cleanly.`,
  );
  steps.push(
    `Use the package manager workflow (${commands.install}) to keep dependencies aligned with the detected setup.`,
  );

  return [...new Set(steps)].slice(0, 3);
}

export class FullSpectrumPartner {
  private readonly gapDetector: GapDetector;
  private readonly proactiveExecutor: ProactiveExecutor;

  constructor(options?: {
    gapDetector?: GapDetector;
    proactiveExecutor?: ProactiveExecutor;
  }) {
    this.gapDetector = options?.gapDetector ?? new GapDetector();
    this.proactiveExecutor =
      options?.proactiveExecutor ?? new ProactiveExecutor();
  }

  analyzeProject(root: string): ProjectAnalysis {
    const scan = collectProjectScan(root);
    const packageManager = detectPackageManager(root);
    const gaps = this.gapDetector.detect(scan);
    const prompt = buildProjectPrompt(scan);
    const analysis = understandIntent(prompt);
    const proactiveDecision = this.proactiveExecutor.execute(analysis, {
      prompt,
    });
    const intentContext: IntentContext = {
      prompt,
      analysis,
      proactiveDecision,
    };

    return {
      packageManager,
      gaps,
      suggestedNextSteps: buildSuggestedNextSteps(
        packageManager,
        gaps,
        intentContext,
      ),
      projectType: detectProjectType(scan, analysis),
      healthScore: computeHealthScore(gaps),
      intentContext,
    };
  }
}
