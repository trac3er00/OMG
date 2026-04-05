import { z } from "zod";

export type HostName = "claude" | "codex" | "gemini" | "kimi";
export type FrontierName =
  | "context-durability"
  | "multi-agent"
  | "society-of-thought"
  | "governance-graph"
  | "reliability-science";
export type ParityStatus = "PASS" | "PARTIAL" | "FAIL";

export const ParityEntrySchema = z.object({
  frontier: z.enum([
    "context-durability",
    "multi-agent",
    "society-of-thought",
    "governance-graph",
    "reliability-science",
  ]),
  host: z.enum(["claude", "codex", "gemini", "kimi"]),
  status: z.enum(["PASS", "PARTIAL", "FAIL"]),
  degradation_mode: z.string().optional(),
  notes: z.string().optional(),
});
export type ParityEntry = z.infer<typeof ParityEntrySchema>;

export const FRONTIER_PARITY_MATRIX: ParityEntry[] = [
  { frontier: "context-durability", host: "claude", status: "PASS" },
  { frontier: "context-durability", host: "codex", status: "PASS" },
  {
    frontier: "context-durability",
    host: "gemini",
    status: "PARTIAL",
    degradation_mode:
      "Checkpoint interval increased to 100 calls; reconstruction protocol works but slower",
    notes: "Gemini context window slightly different semantics",
  },
  {
    frontier: "context-durability",
    host: "kimi",
    status: "PARTIAL",
    degradation_mode:
      "Summarize strategy preferred; DiscardAll may lose domain-specific context",
    notes: "Kimi K2.5 has good summarization capability",
  },

  { frontier: "multi-agent", host: "claude", status: "PASS" },
  { frontier: "multi-agent", host: "codex", status: "PASS" },
  {
    frontier: "multi-agent",
    host: "gemini",
    status: "PARTIAL",
    degradation_mode:
      "A2A handoff works; timeout enforced at 45s instead of 30s for Gemini's longer latency",
  },
  {
    frontier: "multi-agent",
    host: "kimi",
    status: "PARTIAL",
    degradation_mode:
      "A2A handoff works; circuit breaker threshold adjusted to 3 (more conservative for Kimi)",
  },

  { frontier: "society-of-thought", host: "claude", status: "PASS" },
  { frontier: "society-of-thought", host: "codex", status: "PASS" },
  {
    frontier: "society-of-thought",
    host: "gemini",
    status: "PARTIAL",
    degradation_mode:
      "3-perspective voting works; max 2 perspectives for cost efficiency on Gemini",
  },
  {
    frontier: "society-of-thought",
    host: "kimi",
    status: "PARTIAL",
    degradation_mode:
      "Proposer+Critic only (2 perspectives); Red-Team requires explicit invocation",
  },

  { frontier: "governance-graph", host: "claude", status: "PASS" },
  { frontier: "governance-graph", host: "codex", status: "PASS" },
  { frontier: "governance-graph", host: "gemini", status: "PASS" },
  { frontier: "governance-graph", host: "kimi", status: "PASS" },

  { frontier: "reliability-science", host: "claude", status: "PASS" },
  { frontier: "reliability-science", host: "codex", status: "PASS" },
  { frontier: "reliability-science", host: "gemini", status: "PASS" },
  { frontier: "reliability-science", host: "kimi", status: "PASS" },
];

export function getParityStatus(
  frontier: FrontierName,
  host: HostName,
): ParityEntry | null {
  return (
    FRONTIER_PARITY_MATRIX.find(
      (e) => e.frontier === frontier && e.host === host,
    ) ?? null
  );
}

export function getFrontierHosts(
  frontier: FrontierName,
): readonly ParityEntry[] {
  return FRONTIER_PARITY_MATRIX.filter((e) => e.frontier === frontier);
}

export function isFrontierDeployable(
  frontier: FrontierName,
  minHosts = 2,
): boolean {
  const hosts = getFrontierHosts(frontier);
  const supported = hosts.filter(
    (h) => h.status === "PASS" || h.status === "PARTIAL",
  );
  return supported.length >= minHosts;
}
