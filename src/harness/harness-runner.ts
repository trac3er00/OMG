import { randomUUID } from "node:crypto";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { z } from "zod";

import {
  formatDebateSummary,
  isBlockingIssue,
  runPlanningDebate,
} from "../debate/integration.js";
import { GovernanceBlockError } from "../governance/enforcement.js";
import {
  ToolFabric,
  type ToolFabricResult,
} from "../governance/tool-fabric.js";
import type { WorkerTask } from "../interfaces/orchestration.js";
import {
  ExecKernel,
  type ExecKernelExecutor,
  type ExecKernelRunContext,
} from "../orchestration/exec-kernel.js";
import {
  evaluateGate,
  DEFAULT_RELIABILITY_THRESHOLD,
} from "../reliability/gate-integration.js";
import {
  aggregateSnapshot,
  measureCrossRunConsistency,
  measureSameInputConsistency,
  measureSafeFailureModes,
  type ReliabilitySnapshot,
} from "../reliability/metrics.js";

export const HARNESS_VERSION = "1.0.0";

export type HarnessLayer = 1 | 2 | 3 | 4 | 5;
export type HarnessTarget =
  | "typescript"
  | "python"
  | "e2e-browser"
  | "e2e-cli"
  | "e2e-api";
export type TestStatus = "pass" | "fail" | "skip" | "error";

export const LayerResultSchema = z.object({
  layer: z.number().int().min(1).max(5),
  target: z.string(),
  status: z.enum(["pass", "fail", "skip", "error"]),
  total: z.number().int().min(0),
  passed: z.number().int().min(0),
  failed: z.number().int().min(0),
  duration_ms: z.number(),
  evidence_path: z.string().optional(),
  error_message: z.string().optional(),
});
export type LayerResult = z.infer<typeof LayerResultSchema>;

export const HarnessReportSchema = z.object({
  schema_version: z.literal(HARNESS_VERSION),
  run_id: z.string(),
  module: z.string(),
  layers_executed: z.array(z.number().int()),
  layer_results: z.array(LayerResultSchema),
  overall_status: z.enum(["pass", "fail", "partial"]),
  total_tests: z.number().int(),
  passed_tests: z.number().int(),
  failed_tests: z.number().int(),
  generated_at: z.string(),
  orchestration: z
    .object({
      phases: z
        .object({
          started_at: z.string(),
          executed_at: z.string().optional(),
          verified_at: z.string().optional(),
          reported_at: z.string(),
        })
        .strict(),
      debate: z
        .object({
          invoked: z.boolean(),
          skipped: z.boolean(),
          summary: z.string().optional(),
          blocking: z.boolean(),
          error: z.string().optional(),
        })
        .strict(),
      governance: z
        .object({
          allowed: z.boolean(),
          lane: z.string(),
          action: z.enum(["allow", "deny", "warn"]),
          reason: z.string(),
          forced: z.boolean(),
        })
        .strict(),
      reliability: z
        .object({
          gate: z.object({
            passed: z.boolean(),
            warning: z.string().optional(),
            score: z.number(),
            threshold: z.number(),
          }),
          snapshot: z.object({
            schema_version: z.string(),
            snapshot_id: z.string(),
            agent_id: z.string(),
            task_type: z.string(),
            metrics: z.array(
              z.object({
                metric_id: z.string(),
                dimension: z.string(),
                name: z.string(),
                score: z.number(),
                threshold: z.number(),
                status: z.string(),
                sample_count: z.number().int(),
                details: z.record(z.string(), z.unknown()).optional(),
              }),
            ),
            overall_score: z.number(),
            overall_status: z.string(),
            recorded_at: z.string(),
          }),
        })
        .strict(),
    })
    .strict(),
});
export type HarnessReport = z.infer<typeof HarnessReportSchema>;

export interface HarnessRunOptions {
  readonly layers?: readonly HarnessLayer[];
  readonly module: string;
  readonly runId?: string;
  readonly complexity?: number;
  readonly context?: string;
  readonly domain?: string;
  readonly isHighStakes?: boolean;
  readonly alternatives?: readonly string[];
  readonly governance?: {
    readonly lane?: string;
    readonly signedApproval?: boolean;
    readonly attested?: boolean;
    readonly enforcement?: "advisory" | "enforced";
    readonly force?: boolean;
  };
  readonly reliabilityThreshold?: number;
}

export interface LayerRunner {
  readonly layer: HarnessLayer;
  readonly name: string;
  run(module: string): Promise<LayerResult>;
}

export interface HarnessRunnerDeps {
  readonly now?: () => Date;
  readonly toolFabric?: ToolFabric;
}

const GovernanceOutcomeSchema = z.object({
  allowed: z.boolean(),
  lane: z.string(),
  action: z.enum(["allow", "deny", "warn"]),
  reason: z.string(),
  forced: z.boolean(),
});

type GovernanceOutcome = z.infer<typeof GovernanceOutcomeSchema>;

class HarnessExecutor implements ExecKernelExecutor {
  constructor(private readonly runners: Map<HarnessLayer, LayerRunner>) {}

  async execute(
    task: WorkerTask,
    context: ExecKernelRunContext,
  ): Promise<LayerResult> {
    const layer = Number(task.order) as HarnessLayer;
    const runner = this.runners.get(layer);

    if (runner == null) {
      throw new Error(`No runner registered for layer ${String(task.order)}`);
    }

    context.setState("phase", "execute");
    context.setState("layer", layer);
    context.setState("target", task.prompt);

    const result = await runner.run(task.prompt);
    context.setState("status", result.status);
    return result;
  }
}

export class HarnessRunner {
  private readonly runners = new Map<HarnessLayer, LayerRunner>();
  private readonly now: () => Date;
  private readonly toolFabric: ToolFabric;

  constructor(deps: HarnessRunnerDeps = {}) {
    this.now = deps.now ?? (() => new Date());
    this.toolFabric =
      deps.toolFabric ??
      new ToolFabric(join(tmpdir(), `omg-harness-${randomUUID()}`), {
        appendLedgerLine: () => {},
      });
    this.toolFabric.registerLane("harness-execution", {
      allowedTools: ["execute"],
      requiresSignedApproval: true,
      requiresAttestation: true,
      evidenceRequired: ["debate", "module"],
    });
  }

  register(runner: LayerRunner): void {
    this.runners.set(runner.layer, runner);
  }

  async run(opts: HarnessRunOptions): Promise<HarnessReport> {
    const layers = opts.layers ?? [1, 2, 3];
    const runId = opts.runId ?? `run-${Date.now()}`;
    const startedAt = this.now().toISOString();
    const debateDecision: {
      topic: string;
      complexity: number;
      context: string;
      domain?: string;
      is_high_stakes?: boolean;
      alternatives?: readonly string[];
    } = {
      topic: `Harness validation for ${opts.module}`,
      complexity: opts.complexity ?? Math.max(layers.length * 2, 1),
      context:
        opts.context ??
        `Run layered harness validation for ${opts.module} across ${layers.length} layer(s).`,
    };
    if (opts.domain != null) {
      debateDecision.domain = opts.domain;
    }
    if (opts.isHighStakes != null) {
      debateDecision.is_high_stakes = opts.isHighStakes;
    }
    if (opts.alternatives != null) {
      debateDecision.alternatives = opts.alternatives;
    }
    const debateOutcome = await runPlanningDebate(debateDecision);
    const debateSummary =
      formatDebateSummary([debateOutcome]) || debateOutcome.skipReason;
    const blocking = isBlockingIssue(debateOutcome);

    const governance = await this.executeWithGovernance(opts, {
      blocking,
      layers,
      ...(debateSummary == null ? {} : { debateSummary }),
    });
    const executedAt = this.now().toISOString();
    const layerResults = governance.layerResults;

    const reliabilitySnapshot = this.buildReliabilitySnapshot(layerResults);
    const reliabilityGate = evaluateGate(
      Math.round(reliabilitySnapshot.overall_score * 100),
      opts.reliabilityThreshold ?? DEFAULT_RELIABILITY_THRESHOLD,
    );
    const verifiedAt = this.now().toISOString();

    const totalTests = layerResults.reduce((sum, r) => sum + r.total, 0);
    const passedTests = layerResults.reduce((sum, r) => sum + r.passed, 0);
    const failedTests = layerResults.reduce((sum, r) => sum + r.failed, 0);
    const hasFailure = layerResults.some(
      (r) => r.status === "fail" || r.status === "error",
    );
    const allPass = layerResults.every(
      (r) => r.status === "pass" || r.status === "skip",
    );

    return HarnessReportSchema.parse({
      schema_version: HARNESS_VERSION,
      run_id: runId,
      module: opts.module,
      layers_executed: layers,
      layer_results: layerResults,
      overall_status: allPass ? "pass" : hasFailure ? "fail" : "partial",
      total_tests: totalTests,
      passed_tests: passedTests,
      failed_tests: failedTests,
      generated_at: this.now().toISOString(),
      orchestration: {
        phases: {
          started_at: startedAt,
          executed_at: executedAt,
          verified_at: verifiedAt,
          reported_at: this.now().toISOString(),
        },
        debate: {
          invoked: debateOutcome.invoked,
          skipped: debateOutcome.skipped,
          summary: debateSummary,
          blocking,
          error: debateOutcome.error,
        },
        governance: governance.outcome,
        reliability: {
          gate: reliabilityGate,
          snapshot: reliabilitySnapshot,
        },
      },
    });
  }

  private async executeWithGovernance(
    opts: HarnessRunOptions,
    execution: {
      readonly debateSummary?: string;
      readonly blocking: boolean;
      readonly layers: readonly HarnessLayer[];
    },
  ): Promise<{
    outcome: GovernanceOutcome;
    layerResults: LayerResult[];
  }> {
    const lane = opts.governance?.lane ?? "harness-execution";
    const forced = opts.governance?.force ?? false;
    let forcedOverride = false;
    const signedApproval =
      opts.governance?.signedApproval ?? !execution.blocking;
    const attested = opts.governance?.attested ?? true;

    try {
      const result = await this.toolFabric.executeTool(
        "execute",
        {
          signedApproval,
          attested,
          evidence: {
            debate: execution.debateSummary ?? "debate skipped",
            module: opts.module,
          },
        },
        lane,
        async () => this.executeLayers(opts.module, execution.layers),
        {
          enforcement: opts.governance?.enforcement ?? "enforced",
          force: forced,
          onForceOverride: () => {
            forcedOverride = true;
          },
        },
      );

      const decision = result.decision;
      const layerResults = Array.isArray(result.output)
        ? (result.output as LayerResult[])
        : [];

      return {
        outcome: this.toGovernanceOutcome(decision, forcedOverride),
        layerResults,
      };
    } catch (error) {
      if (!(error instanceof GovernanceBlockError)) {
        throw error;
      }

      return {
        outcome: GovernanceOutcomeSchema.parse({
          allowed: false,
          lane,
          action: "deny",
          reason: error.blockReason,
          forced: forced,
        }),
        layerResults: execution.layers.map((layer) =>
          LayerResultSchema.parse({
            layer,
            target: opts.module,
            status: "error",
            total: 0,
            passed: 0,
            failed: 0,
            duration_ms: 0,
            error_message: error.message,
          }),
        ),
      };
    }
  }

  private async executeLayers(
    module: string,
    layers: readonly HarnessLayer[],
  ): Promise<LayerResult[]> {
    const kernel = ExecKernel.create({
      now: this.now,
      createRunId: () => randomUUID(),
      executor: new HarnessExecutor(this.runners),
    });
    const layerResults: LayerResult[] = [];

    for (const layer of layers) {
      const runner = this.runners.get(layer);
      if (runner == null) {
        layerResults.push(
          LayerResultSchema.parse({
            layer,
            target: module,
            status: "skip",
            total: 0,
            passed: 0,
            failed: 0,
            duration_ms: 0,
            error_message: `No runner registered for layer ${layer}`,
          }),
        );
        continue;
      }

      const state = await kernel.run({
        agentName: runner.name,
        prompt: module,
        order: layer,
      });
      layerResults.push(LayerResultSchema.parse(state.executionResult));
    }

    return layerResults;
  }

  private buildReliabilitySnapshot(
    layerResults: readonly LayerResult[],
  ): ReliabilitySnapshot {
    const statusOutputs = layerResults.map((result) => result.status);
    const passRates = layerResults.map((result) => {
      if (result.total === 0) {
        return result.status === "error" ? 0 : 1;
      }

      return result.passed / result.total;
    });
    const failureModes = layerResults.map((result) => {
      if (result.status === "error") {
        return "unsafe" as const;
      }

      return "safe" as const;
    });

    return aggregateSnapshot("harness-runner", "harness-validation", [
      measureSameInputConsistency(statusOutputs),
      measureCrossRunConsistency(passRates),
      measureSafeFailureModes(failureModes),
    ]);
  }

  private toGovernanceOutcome(
    decision: ToolFabricResult,
    forced: boolean,
  ): GovernanceOutcome {
    return GovernanceOutcomeSchema.parse({
      allowed: decision.action !== "deny" || forced,
      lane: decision.lane,
      action: decision.action,
      reason: decision.reason,
      forced,
    });
  }
}

export function createPassingRunner(
  layer: HarnessLayer,
  name: string,
  testCount = 10,
): LayerRunner {
  return {
    layer,
    name,
    async run(module: string): Promise<LayerResult> {
      return LayerResultSchema.parse({
        layer,
        target: module,
        status: "pass",
        total: testCount,
        passed: testCount,
        failed: 0,
        duration_ms: 50,
      });
    },
  };
}

export function createFailingRunner(
  layer: HarnessLayer,
  name: string,
  failCount = 2,
): LayerRunner {
  return {
    layer,
    name,
    async run(module: string): Promise<LayerResult> {
      return LayerResultSchema.parse({
        layer,
        target: module,
        status: "fail",
        total: 10,
        passed: 10 - failCount,
        failed: failCount,
        duration_ms: 75,
        error_message: `${failCount} test(s) failed`,
      });
    },
  };
}
