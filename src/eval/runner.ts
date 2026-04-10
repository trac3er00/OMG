import { readdirSync } from "node:fs";
import { join } from "node:path";

export interface EvalCase {
  readonly name: string;
  readonly run: () => Promise<EvalCaseResult> | EvalCaseResult;
  readonly weight?: number;
}

export interface EvalCaseResult {
  readonly passed: boolean;
  readonly score: number;
  readonly details?: string | undefined;
}

export interface EvalSuiteDefinition {
  readonly module: string;
  readonly description: string;
  readonly cases: readonly EvalCase[];
}

export interface EvalSuiteResult {
  readonly module: string;
  readonly score: number;
  readonly details: readonly EvalCaseDetail[];
  readonly timestamp: string;
}

export interface EvalCaseDetail {
  readonly name: string;
  readonly passed: boolean;
  readonly score: number;
  readonly weight: number;
  readonly details?: string | undefined;
  readonly error?: string | undefined;
}

export interface EvalRunResult {
  readonly schema: "EvalRunResult";
  readonly eval_id: string;
  readonly timestamp: string;
  readonly suites: readonly EvalSuiteResult[];
  readonly aggregate_score: number;
  readonly summary: {
    readonly total_cases: number;
    readonly passed_cases: number;
    readonly failed_cases: number;
    readonly suite_count: number;
  };
}

function generateEvalId(): string {
  return `eval-ts-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

async function runSuite(suite: EvalSuiteDefinition): Promise<EvalSuiteResult> {
  const details: EvalCaseDetail[] = [];

  for (const evalCase of suite.cases) {
    const weight = evalCase.weight ?? 1;
    try {
      const result = await evalCase.run();
      details.push({
        name: evalCase.name,
        passed: result.passed,
        score: Math.max(0, Math.min(100, result.score)),
        weight,
        details: result.details,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      details.push({
        name: evalCase.name,
        passed: false,
        score: 0,
        weight,
        error: message,
      });
    }
  }

  const totalWeight = details.reduce((sum, d) => sum + d.weight, 0);
  const weightedScore =
    totalWeight > 0
      ? details.reduce((sum, d) => sum + d.score * d.weight, 0) / totalWeight
      : 0;

  return {
    module: suite.module,
    score: Math.round(weightedScore * 100) / 100,
    details,
    timestamp: new Date().toISOString(),
  };
}

async function discoverSuites(): Promise<EvalSuiteDefinition[]> {
  const suitesDir = join(import.meta.dir, "suites");
  const files = readdirSync(suitesDir).filter((f) => f.endsWith(".eval.ts"));
  const suites: EvalSuiteDefinition[] = [];

  for (const file of files.sort()) {
    const modulePath = join(suitesDir, file);
    const mod = (await import(modulePath)) as {
      default?: EvalSuiteDefinition;
      suite?: EvalSuiteDefinition;
    };
    const suite = mod.default ?? mod.suite;
    if (suite && suite.module && suite.cases) {
      suites.push(suite);
    } else {
      console.error(`[eval] Skipping ${file}: no valid suite export found`);
    }
  }

  return suites;
}

export async function runAllEvals(): Promise<EvalRunResult> {
  const suites = await discoverSuites();
  const results: EvalSuiteResult[] = [];

  for (const suite of suites) {
    const result = await runSuite(suite);
    results.push(result);
  }

  const totalCases = results.reduce((sum, r) => sum + r.details.length, 0);
  const passedCases = results.reduce(
    (sum, r) => sum + r.details.filter((d) => d.passed).length,
    0,
  );
  const aggregateScore =
    results.length > 0
      ? Math.round(
          (results.reduce((sum, r) => sum + r.score, 0) / results.length) * 100,
        ) / 100
      : 0;

  return {
    schema: "EvalRunResult",
    eval_id: generateEvalId(),
    timestamp: new Date().toISOString(),
    suites: results,
    aggregate_score: aggregateScore,
    summary: {
      total_cases: totalCases,
      passed_cases: passedCases,
      failed_cases: totalCases - passedCases,
      suite_count: results.length,
    },
  };
}

if (import.meta.main) {
  const result = await runAllEvals();

  for (const suite of result.suites) {
    const icon =
      suite.score >= 70
        ? "\u2705"
        : suite.score >= 40
          ? "\u26A0\uFE0F"
          : "\u274C";
    console.log(`${icon} ${suite.module}: ${suite.score}/100`);
    for (const detail of suite.details) {
      const caseIcon = detail.passed ? "  \u2713" : "  \u2717";
      const suffix = detail.error
        ? ` (error: ${detail.error})`
        : detail.details
          ? ` (${detail.details})`
          : "";
      console.log(`${caseIcon} ${detail.name}: ${detail.score}/100${suffix}`);
    }
  }

  console.log("");
  console.log("--- Eval Summary ---");
  console.log(`Suites: ${result.summary.suite_count}`);
  console.log(
    `Cases: ${result.summary.passed_cases}/${result.summary.total_cases} passed`,
  );
  console.log(`Aggregate Score: ${result.aggregate_score}/100`);
  console.log("");

  console.log("--- JSON Output ---");
  console.log(JSON.stringify(result, null, 2));
}
