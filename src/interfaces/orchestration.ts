export type AgentState = "pending" | "running" | "completed" | "failed" | "cancelled" | "orphaned";
export type IsolationMode = "worktree" | "container" | "none";
export type TaskComplexity = "trivial" | "simple" | "moderate" | "complex" | "extreme";

export interface AgentConfig {
  readonly name: string;
  readonly category: string;
  readonly prompt: string;
  readonly skills: readonly string[];
  readonly timeout: number;
  readonly maxRetries: number;
  readonly subagentType?: string;
}

export interface WorkerTask {
  readonly agentName: string;
  readonly prompt: string;
  readonly order?: number;
  readonly timeout?: number;
}

export interface BudgetEnvelope {
  readonly runId: string;
  readonly cpuSecondsLimit: number;
  readonly memoryMbLimit: number;
  readonly wallTimeSecondsLimit: number;
  readonly tokenLimit: number;
  readonly networkBytesLimit: number;
  readonly cpuSecondsUsed: number;
  readonly memoryMbPeak: number;
  readonly wallTimeSecondsUsed: number;
  readonly tokensUsed: number;
  readonly networkBytesUsed: number;
  readonly exceeded: boolean;
  readonly exceededDimensions: readonly string[];
}

export interface AgentRecommendation {
  readonly agentName: string;
  readonly category: string;
  readonly provider: string;
  readonly confidence: number;
  readonly fallback: readonly string[];
  readonly reasoning: string;
  readonly complexity: TaskComplexity;
}

export interface TeamDispatchRequest {
  readonly target: string;
  readonly problem: string;
  readonly context: string;
  readonly files?: readonly string[];
  readonly expectedOutcome?: string;
}

export interface TeamDispatchResult {
  readonly status: "ok" | "clarification_required" | "error";
  readonly findings: readonly string[];
  readonly actions: readonly string[];
  readonly evidence: Readonly<Record<string, unknown>>;
}
