export interface RoutingCandidate {
  readonly agent: string;
  readonly order: number;
  readonly successes: number;
  readonly failures: number;
}

export interface AgentPerformance {
  readonly agent: string;
  readonly successes: number;
  readonly failures: number;
  readonly total: number;
  readonly successRate: number;
  readonly weight: number;
}

export interface RoutingOptimization {
  readonly taskType: string;
  readonly optimizedAt: string;
  readonly recommendedAgent: string;
  readonly weights: Readonly<Record<string, number>>;
  readonly rankings: readonly AgentPerformance[];
}

export interface RoutingMetaAgentOptions {
  readonly now?: () => Date;
}

export interface SelfImprovingRouterOptions {
  readonly agents?: readonly string[];
  readonly fallbackAgent?: string;
  readonly now?: () => Date;
  readonly metaAgent?: RoutingMetaAgent;
}

interface AgentStats {
  successes: number;
  failures: number;
}

function round(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}

export class RoutingMetaAgent {
  static create(options: RoutingMetaAgentOptions = {}): RoutingMetaAgent {
    return new RoutingMetaAgent(options.now ?? (() => new Date()));
  }

  private readonly now: () => Date;

  constructor(now: () => Date) {
    this.now = now;
  }

  optimize(taskType: string, candidates: readonly RoutingCandidate[]): RoutingOptimization {
    const scored = candidates.map((candidate) => {
      const total = candidate.successes + candidate.failures;
      const successRate = total === 0 ? 0.5 : candidate.successes / total;
      const confidenceBonus = total === 0 ? 0 : Math.min(total, 10) / 100;
      const rawWeight = Math.max(0.05, successRate + confidenceBonus);

      return {
        agent: candidate.agent,
        order: candidate.order,
        successes: candidate.successes,
        failures: candidate.failures,
        total,
        successRate: round(successRate),
        rawWeight,
      };
    });

    const totalRawWeight = scored.reduce((sum, candidate) => sum + candidate.rawWeight, 0);
    const rankings = scored
      .map<AgentPerformance>((candidate) => ({
        agent: candidate.agent,
        successes: candidate.successes,
        failures: candidate.failures,
        total: candidate.total,
        successRate: candidate.successRate,
        weight: round(candidate.rawWeight / totalRawWeight),
      }))
      .sort((left, right) => {
        if (right.weight !== left.weight) {
          return right.weight - left.weight;
        }
        if (right.successRate !== left.successRate) {
          return right.successRate - left.successRate;
        }
        if (right.total !== left.total) {
          return right.total - left.total;
        }

        const leftOrder = scored.find((candidate) => candidate.agent === left.agent)?.order ?? Number.MAX_SAFE_INTEGER;
        const rightOrder = scored.find((candidate) => candidate.agent === right.agent)?.order ?? Number.MAX_SAFE_INTEGER;
        if (leftOrder !== rightOrder) {
          return leftOrder - rightOrder;
        }
        return left.agent.localeCompare(right.agent);
      });

    const weights: Record<string, number> = {};
    for (const ranking of rankings) {
      weights[ranking.agent] = ranking.weight;
    }

    return {
      taskType,
      optimizedAt: this.now().toISOString(),
      recommendedAgent: rankings[0]?.agent ?? "",
      weights,
      rankings,
    };
  }
}

export class SelfImprovingRouter {
  static create(options: SelfImprovingRouterOptions = {}): SelfImprovingRouter {
    return new SelfImprovingRouter(options);
  }

  private readonly fallbackAgent: string;

  private readonly metaAgent: RoutingMetaAgent;

  private readonly registeredAgents: string[];

  private readonly agentOrder = new Map<string, number>();

  private readonly taskPerformance = new Map<string, Map<string, AgentStats>>();

  constructor(options: SelfImprovingRouterOptions = {}) {
    this.fallbackAgent = options.fallbackAgent ?? "codex";
    if (options.metaAgent !== undefined) {
      this.metaAgent = options.metaAgent;
    } else if (options.now !== undefined) {
      this.metaAgent = RoutingMetaAgent.create({ now: options.now });
    } else {
      this.metaAgent = RoutingMetaAgent.create();
    }
    const seededAgents = options.agents ?? [this.fallbackAgent];
    this.registeredAgents = [];

    for (const agent of seededAgents) {
      this.registerAgent(agent);
    }
  }

  recordOutcome(agent: string, taskType: string, success: boolean): void {
    this.registerAgent(agent);
    const stats = this.getOrCreateStats(taskType, agent);
    if (success) {
      stats.successes += 1;
      return;
    }
    stats.failures += 1;
  }

  route(taskType: string): string {
    return this.optimize(taskType).recommendedAgent;
  }

  optimize(taskType: string): RoutingOptimization {
    const candidates = this.buildCandidates(taskType);
    return this.metaAgent.optimize(taskType, candidates);
  }

  private registerAgent(agent: string): void {
    if (this.agentOrder.has(agent)) {
      return;
    }

    this.agentOrder.set(agent, this.registeredAgents.length);
    this.registeredAgents.push(agent);
  }

  private getOrCreateStats(taskType: string, agent: string): AgentStats {
    let taskStats = this.taskPerformance.get(taskType);
    if (taskStats === undefined) {
      taskStats = new Map<string, AgentStats>();
      this.taskPerformance.set(taskType, taskStats);
    }

    let stats = taskStats.get(agent);
    if (stats === undefined) {
      stats = { successes: 0, failures: 0 };
      taskStats.set(agent, stats);
    }

    return stats;
  }

  private buildCandidates(taskType: string): RoutingCandidate[] {
    const taskStats = this.taskPerformance.get(taskType);
    const agentNames = this.registeredAgents.length > 0 ? this.registeredAgents : [this.fallbackAgent];

    return agentNames.map((agent) => {
      const stats = taskStats?.get(agent);
      return {
        agent,
        order: this.agentOrder.get(agent) ?? Number.MAX_SAFE_INTEGER,
        successes: stats?.successes ?? 0,
        failures: stats?.failures ?? 0,
      };
    });
  }
}
