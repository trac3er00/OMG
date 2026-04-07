import { existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { z } from "zod";
import { readJsonFile, atomicWriteJson } from "../state/atomic-io.js";
import { StateResolver } from "../state/state-resolver.js";

export const PLANNING_CONTEXT_VERSION = "1.0.0";
export const PLANNING_CONTEXT_MEMORY_TIER = "ship" as const;
export const PLANNING_CONTEXT_RELATIVE_DIR = "planning-context";

const PlanningContextSchema = z.object({
  planId: z.string().min(1),
  topic: z.string().min(1),
  interviewDecisions: z.record(z.string(), z.string()),
  researchFindings: z.array(z.string()),
  metisReview: z.string().optional(),
  createdAt: z.string(),
  version: z.string().min(1),
});

const PlanningContextEnvelopeSchema = z.object({
  kind: z.literal("planning-context"),
  tier: z.literal(PLANNING_CONTEXT_MEMORY_TIER),
  savedAt: z.string(),
  context: PlanningContextSchema,
});

function normalizePlanningContext(
  context: z.infer<typeof PlanningContextSchema>,
): PlanningContext {
  return {
    planId: context.planId,
    topic: context.topic,
    interviewDecisions: context.interviewDecisions,
    researchFindings: context.researchFindings,
    createdAt: context.createdAt,
    version: context.version,
    ...(context.metisReview !== undefined
      ? { metisReview: context.metisReview }
      : {}),
  };
}

export interface PlanningContext {
  planId: string;
  topic: string;
  interviewDecisions: Record<string, string>;
  researchFindings: string[];
  metisReview?: string;
  createdAt: string;
  version: string;
}

export interface PlanningContextStore {
  save(context: PlanningContext): Promise<void>;
  load(planId: string): Promise<PlanningContext | null>;
  exists(planId: string): Promise<boolean>;
}

export class FilePlanningContextStore implements PlanningContextStore {
  private readonly planningContextDir: string;

  constructor(projectDir = process.cwd()) {
    const resolver = new StateResolver(projectDir);
    this.planningContextDir = resolver.resolve(PLANNING_CONTEXT_RELATIVE_DIR);
  }

  async save(context: PlanningContext): Promise<void> {
    const parsed = normalizePlanningContext(
      PlanningContextSchema.parse(context),
    );
    this.ensureDirectory();
    atomicWriteJson(this.planPath(parsed.planId), {
      kind: "planning-context",
      tier: PLANNING_CONTEXT_MEMORY_TIER,
      savedAt: new Date().toISOString(),
      context: parsed,
    });
  }

  async load(planId: string): Promise<PlanningContext | null> {
    const raw = readJsonFile<unknown>(this.planPath(planId));
    if (raw === undefined) {
      return null;
    }

    const envelope = PlanningContextEnvelopeSchema.safeParse(raw);
    if (envelope.success) {
      return normalizePlanningContext(envelope.data.context);
    }

    return normalizePlanningContext(PlanningContextSchema.parse(raw));
  }

  async exists(planId: string): Promise<boolean> {
    return existsSync(this.planPath(planId));
  }

  private ensureDirectory(): void {
    if (!existsSync(this.planningContextDir)) {
      mkdirSync(this.planningContextDir, { recursive: true });
    }
  }

  private planPath(planId: string): string {
    return join(this.planningContextDir, `${encodeURIComponent(planId)}.json`);
  }
}

export const defaultPlanningContextStore = new FilePlanningContextStore();
