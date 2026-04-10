import { IMSS } from "../state/imss.js";
import { understandIntent } from "../intent/index.js";
import { TeamRouter } from "../orchestration/router.js";
import { checkMutationAllowed } from "../security/mutation-gate.js";
import type { TeamDispatchRequest } from "../interfaces/orchestration.js";

interface BenchmarkResult {
  readonly operation: string;
  readonly iterations: number;
  readonly totalMs: number;
  readonly avgMs: number;
  readonly p95Ms: number;
  readonly p99Ms: number;
  readonly opsPerSec: number;
}

function percentile(sorted: readonly number[], p: number): number {
  const idx = Math.ceil((p / 100) * sorted.length) - 1;
  return sorted[Math.max(0, idx)]!;
}

async function bench(
  name: string,
  iterations: number,
  fn: () => void | Promise<void>,
): Promise<BenchmarkResult> {
  const timings: number[] = [];

  for (let i = 0; i < 50; i++) {
    await fn();
  }

  for (let i = 0; i < iterations; i++) {
    const start = performance.now();
    await fn();
    timings.push(performance.now() - start);
  }

  timings.sort((a, b) => a - b);
  const totalMs = timings.reduce((s, t) => s + t, 0);

  return {
    operation: name,
    iterations,
    totalMs: Math.round(totalMs * 1000) / 1000,
    avgMs: Math.round((totalMs / iterations) * 1000) / 1000,
    p95Ms: Math.round(percentile(timings, 95) * 1000) / 1000,
    p99Ms: Math.round(percentile(timings, 99) * 1000) / 1000,
    opsPerSec: Math.round(iterations / (totalMs / 1000)),
  };
}

const ITERATIONS = 1000;

async function benchIntentClassification(): Promise<BenchmarkResult> {
  return bench("classifyIntent", ITERATIONS, () => {
    understandIntent("fix typo in readme");
  });
}

async function benchImssSet(): Promise<BenchmarkResult> {
  const store = new IMSS<string>();
  return bench("imss.set", ITERATIONS, () => {
    store.set("bench-key", "bench-value");
  });
}

async function benchImssGet(): Promise<BenchmarkResult> {
  const store = new IMSS<string>();
  store.set("bench-key", "bench-value");
  return bench("imss.get", ITERATIONS, () => {
    store.get("bench-key");
  });
}

async function benchRouteTask(): Promise<BenchmarkResult> {
  const router = TeamRouter.create();
  const request: TeamDispatchRequest = {
    target: "auto",
    problem: "build a login page with authentication",
    context: "",
    files: ["src/auth.ts"],
    routingSignals: { files: 2, loc: 150, deps: 3, errors: 0 },
  };
  return bench("routeTask", ITERATIONS, async () => {
    await router.route(request);
  });
}

async function benchMutationGate(): Promise<BenchmarkResult> {
  const projectDir = process.cwd();
  return bench("checkMutationAllowed", ITERATIONS, async () => {
    await checkMutationAllowed(
      "Write",
      "src/example.ts",
      projectDir,
      null,
      null,
      null,
      "bench-run-001",
    );
  });
}

async function main(): Promise<void> {
  const results = await Promise.all([
    benchIntentClassification(),
    benchImssSet(),
    benchImssGet(),
    benchRouteTask(),
    benchMutationGate(),
  ]);

  const report = {
    timestamp: new Date().toISOString(),
    runtime: "bun",
    iterations: ITERATIONS,
    results,
    summary: {
      allUnder100ms: results.every((r) => r.avgMs < 100),
      maxAvgMs: Math.max(...results.map((r) => r.avgMs)),
      minOpsPerSec: Math.min(...results.map((r) => r.opsPerSec)),
    },
  };

  console.log(JSON.stringify(report, null, 2));
}

await main();
