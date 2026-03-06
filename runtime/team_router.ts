import { normalizeWhitespace } from "./common.ts";

export type TeamDispatchRequest = {
  target: string;
  problem: string;
  context?: string;
  files?: string[];
  expected_outcome?: string;
};

type Phase = {
  agent: string;
  focus: string;
};

export type TeamDispatchResult = {
  status: "ok";
  schema: "TeamDispatchResult";
  target: string;
  evidence: Record<string, unknown>;
  worker_count: number;
  target_worker_count: number;
  parallel_execution: boolean;
  sequential_execution: boolean;
  phases: Phase[];
  actions: string[];
};

function inferAutoTarget(problem: string): { target: string; reason: string } {
  const normalized = normalizeWhitespace(problem).toLowerCase();
  if (/\bgemini\b/.test(normalized)) {
    return { target: "gemini", reason: "explicit-provider-mention" };
  }
  if (/\bcodex\b/.test(normalized)) {
    return { target: "codex", reason: "explicit-provider-mention" };
  }
  const ui = /\b(ui|ux|layout|component|design|css|visual|dashboard|frontend)\b/.test(normalized);
  const code = /\b(api|auth|backend|service|bug|debug|security|database|logic|review|full stack)\b/.test(normalized);
  const ccg = /\bccg\b/.test(normalized) || (ui && code);
  if (ccg) {
    return { target: "ccg", reason: "mixed-ui-and-code-signals" };
  }
  if (ui) {
    return { target: "gemini", reason: "frontend-signals" };
  }
  return { target: "codex", reason: "default-backend-path" };
}

function buildSingleTrack(target: string, problem: string, reason: string): TeamDispatchResult {
  const phase: Phase =
    target === "gemini"
      ? { agent: "frontend-designer", focus: `Design response for "${problem}"` }
      : { agent: "backend-engineer", focus: `Implement or debug "${problem}"` };
  return {
    status: "ok",
    schema: "TeamDispatchResult",
    target,
    evidence: { target, reason },
    worker_count: 1,
    target_worker_count: 1,
    parallel_execution: false,
    sequential_execution: true,
    phases: [phase],
    actions: [`route:${target}`, `problem:${problem}`]
  };
}

export function executeCcgMode(input: {
  problem: string;
  project_dir?: string;
  context?: string;
  files?: string[];
}): TeamDispatchResult {
  return {
    status: "ok",
    schema: "TeamDispatchResult",
    target: "ccg",
    evidence: {
      target: "ccg",
      reason: "dual-track-orchestrator",
      project_dir: input.project_dir || ""
    },
    worker_count: 2,
    target_worker_count: 2,
    parallel_execution: true,
    sequential_execution: false,
    phases: [
      { agent: "backend-engineer", focus: `Codex track for "${input.problem}"` },
      { agent: "frontend-designer", focus: `Gemini track for "${input.problem}"` }
    ],
    actions: ["route:codex", "route:gemini"]
  };
}

export function executeCrazyMode(input: {
  problem: string;
  project_dir?: string;
  context?: string;
  files?: string[];
}): TeamDispatchResult {
  return {
    status: "ok",
    schema: "TeamDispatchResult",
    target: "crazy",
    evidence: {
      target: "crazy",
      reason: "parallel-multi-agent-mode",
      project_dir: input.project_dir || ""
    },
    worker_count: 5,
    target_worker_count: 5,
    parallel_execution: true,
    sequential_execution: false,
    phases: [
      { agent: "architect-mode", focus: `Define execution lanes for "${input.problem}"` },
      { agent: "backend-engineer", focus: "Core backend and logic pass" },
      { agent: "frontend-designer", focus: "UI, UX, and interaction pass" },
      { agent: "security-auditor", focus: "Security risk scan" },
      { agent: "testing-engineer", focus: "Verification and regression coverage" }
    ],
    actions: ["plan", "backend", "frontend", "security", "test"]
  };
}

export function dispatchTeam(request: TeamDispatchRequest): TeamDispatchResult {
  const requested = request.target || "auto";
  const resolved = requested === "auto" ? inferAutoTarget(request.problem) : { target: requested, reason: "explicit-target" };
  if (resolved.target === "ccg") {
    const ccg = executeCcgMode({
      problem: request.problem,
      context: request.context || "",
      files: request.files || []
    });
    ccg.evidence = { ...ccg.evidence, requested_target: requested };
    return ccg;
  }
  const single = buildSingleTrack(resolved.target, request.problem, resolved.reason);
  single.evidence = {
    ...single.evidence,
    requested_target: requested,
    expected_outcome: request.expected_outcome || ""
  };
  return single;
}
