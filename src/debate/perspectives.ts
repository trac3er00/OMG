import { z } from "zod";

export const DEBATE_VERSION = "1.0.0";
export const MAX_DEBATE_ROUNDS = 3;
export const SOT_COMPLEXITY_THRESHOLD = 3;

export type PerspectiveRole =
  | "proposer"
  | "critic"
  | "red-team"
  | "domain-expert"
  | "reconciler";
export type DisagreementSeverity = "minor" | "major" | "blocking";
export type TaskComplexityLevel = 1 | 2 | 3 | 4 | 5;

export const DisagreementSchema = z.object({
  role: z.enum([
    "proposer",
    "critic",
    "red-team",
    "domain-expert",
    "reconciler",
  ]),
  claim: z.string(),
  rationale: z.string(),
  severity: z.enum(["minor", "major", "blocking"]),
  evidence: z.array(z.string()),
});
export type Disagreement = z.infer<typeof DisagreementSchema>;

export const PerspectiveOutputSchema = z.object({
  role: z.enum([
    "proposer",
    "critic",
    "red-team",
    "domain-expert",
    "reconciler",
  ]),
  position: z.string(),
  rationale: z.string(),
  confidence: z.number().min(0).max(1),
  disagreements: z.array(DisagreementSchema),
  round: z.number().int().min(1).max(3),
});
export type PerspectiveOutput = z.infer<typeof PerspectiveOutputSchema>;

export const PERSPECTIVE_PROMPTS: Record<PerspectiveRole, string> = {
  proposer:
    "Generate an initial solution or approach with clear rationale and implementation steps.",
  critic:
    "Systematically challenge assumptions. Identify risks, edge cases, and potential failures.",
  "red-team":
    "Act as an adversary. Find security vulnerabilities, attack vectors, and ways this could fail catastrophically.",
  "domain-expert":
    "Apply domain-specific knowledge. Identify technical constraints, industry standards, and best practices.",
  reconciler:
    "Synthesize all perspectives. Identify areas of consensus, classify disagreements by severity, and propose a balanced resolution.",
};

const SOT_ACTIVATION_DOMAINS = new Set([
  "security",
  "authentication",
  "authorization",
  "payment",
  "architecture",
  "deployment",
  "database-migration",
  "breaking-change",
]);

export interface ActivationDecision {
  readonly should_activate: boolean;
  readonly reason: string;
  readonly complexity_level: TaskComplexityLevel;
}

export function shouldActivateSoT(opts: {
  complexity_level: TaskComplexityLevel;
  domain?: string;
  is_high_stakes?: boolean;
}): ActivationDecision {
  const { complexity_level, domain, is_high_stakes = false } = opts;

  if (complexity_level < SOT_COMPLEXITY_THRESHOLD && !is_high_stakes) {
    const isDomainCritical =
      domain != null && SOT_ACTIVATION_DOMAINS.has(domain.toLowerCase());
    if (!isDomainCritical) {
      return {
        should_activate: false,
        reason: "Task complexity below threshold",
        complexity_level,
      };
    }
  }

  const reason =
    complexity_level >= 5
      ? "Extreme complexity task"
      : is_high_stakes
        ? "High-stakes operation"
        : domain != null && SOT_ACTIVATION_DOMAINS.has(domain.toLowerCase())
          ? `Critical domain: ${domain}`
          : `Complexity level ${complexity_level} meets threshold`;

  return {
    should_activate: true,
    reason,
    complexity_level,
  };
}

export function createPerspectiveOutput(
  role: PerspectiveRole,
  position: string,
  opts: Partial<Omit<PerspectiveOutput, "role" | "position" | "round">> & {
    round?: number;
  } = {},
): PerspectiveOutput {
  return PerspectiveOutputSchema.parse({
    role,
    position,
    rationale: opts.rationale ?? `${PERSPECTIVE_PROMPTS[role]}`,
    confidence: opts.confidence ?? 0.7,
    disagreements: opts.disagreements ?? [],
    round: opts.round ?? 1,
  });
}

export function hasBlockingDisagreement(
  outputs: readonly PerspectiveOutput[],
): boolean {
  return outputs.some((o) =>
    o.disagreements.some((d) => d.severity === "blocking"),
  );
}
