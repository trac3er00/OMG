import { z } from "zod";
import { atomicWriteJson, readJsonFile } from "../state/atomic-io.js";
import { join } from "node:path";
import { mkdirSync } from "node:fs";

export const GOVERNANCE_VERSION = "1.0.0";
export const GOVERNANCE_GRAPH_FILE = "governance-graph.json";

export type GovernanceState =
  | "planning"
  | "implementing"
  | "reviewing"
  | "deploying"
  | "complete"
  | "blocked";

export const ALLOWED_TRANSITIONS: Record<
  GovernanceState,
  readonly GovernanceState[]
> = {
  planning: ["implementing", "blocked"],
  implementing: ["reviewing", "planning", "blocked"],
  reviewing: ["deploying", "implementing", "blocked"],
  deploying: ["complete", "reviewing", "blocked"],
  complete: [],
  blocked: ["planning"],
};

export const GovernanceNodeSchema = z.object({
  node_id: z.string(),
  state: z.enum([
    "planning",
    "implementing",
    "reviewing",
    "deploying",
    "complete",
    "blocked",
  ]),
  requires_approval_from: z.array(z.string()),
  sanctions: z.array(z.string()),
  remediation_paths: z.array(z.string()),
  created_at: z.string(),
  updated_at: z.string(),
});
export type GovernanceNode = z.infer<typeof GovernanceNodeSchema>;

export const GovernanceGraphSchema = z.object({
  schema_version: z.literal(GOVERNANCE_VERSION),
  graph_id: z.string(),
  nodes: z.record(z.string(), GovernanceNodeSchema),
  adjacency: z.record(z.string(), z.array(z.string())),
  created_at: z.string(),
  updated_at: z.string(),
});
export type GovernanceGraph = z.infer<typeof GovernanceGraphSchema>;

export interface TransitionResult {
  readonly success: boolean;
  readonly from: GovernanceState;
  readonly to: GovernanceState;
  readonly node_id: string;
  readonly error?: string;
}

export type EnforcementMode = "advisory" | "soft-block" | "hard-block";

export interface ValidationResult {
  readonly allowed: boolean;
  readonly mode: EnforcementMode;
  readonly agents: readonly string[];
  readonly warnings: readonly string[];
  readonly violations: readonly string[];
}

export class GovernanceGraphRuntime {
  private graph: GovernanceGraph;
  private readonly projectDir: string;
  private readonly enforcementMode: EnforcementMode;

  constructor(
    projectDir: string,
    graphId = "default",
    enforcementMode: EnforcementMode = "soft-block",
  ) {
    this.projectDir = projectDir;
    this.enforcementMode = enforcementMode;
    const loaded = this.load();
    if (loaded != null) {
      this.graph = loaded;
    } else {
      this.graph = GovernanceGraphSchema.parse({
        schema_version: GOVERNANCE_VERSION,
        graph_id: graphId,
        nodes: {},
        adjacency: {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    }
  }

  addNode(
    nodeId: string,
    initialState: GovernanceState = "planning",
    opts: Partial<
      Pick<
        GovernanceNode,
        "requires_approval_from" | "sanctions" | "remediation_paths"
      >
    > = {},
  ): GovernanceNode {
    const node = GovernanceNodeSchema.parse({
      node_id: nodeId,
      state: initialState,
      requires_approval_from: opts.requires_approval_from ?? [],
      sanctions: opts.sanctions ?? [],
      remediation_paths: opts.remediation_paths ?? [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    this.graph.nodes[nodeId] = node;
    return node;
  }

  addEdge(fromNodeId: string, toNodeId: string): void {
    if (!this.graph.adjacency[fromNodeId]) {
      this.graph.adjacency[fromNodeId] = [];
    }
    const adj = this.graph.adjacency[fromNodeId]!;
    if (!adj.includes(toNodeId)) {
      adj.push(toNodeId);
    }
    if (this.detectCycle()) {
      adj.splice(adj.indexOf(toNodeId), 1);
      throw new Error(
        `cycle_detected: adding edge ${fromNodeId} → ${toNodeId} would create a cycle`,
      );
    }
  }

  transition(nodeId: string, newState: GovernanceState): TransitionResult {
    const node = this.graph.nodes[nodeId];
    if (node == null) {
      return {
        success: false,
        from: "planning",
        to: newState,
        node_id: nodeId,
        error: `Unknown node: ${nodeId}`,
      };
    }

    const allowed = ALLOWED_TRANSITIONS[node.state];
    if (!allowed.includes(newState)) {
      return {
        success: false,
        from: node.state,
        to: newState,
        node_id: nodeId,
        error: `unauthorized_transition: ${node.state} → ${newState}`,
      };
    }

    this.graph.nodes[nodeId] = {
      ...node,
      state: newState,
      updated_at: new Date().toISOString(),
    };
    this.graph = { ...this.graph, updated_at: new Date().toISOString() };

    return { success: true, from: node.state, to: newState, node_id: nodeId };
  }

  getNode(nodeId: string): GovernanceNode | null {
    return this.graph.nodes[nodeId] ?? null;
  }

  getGraph(): Readonly<GovernanceGraph> {
    return this.graph;
  }

  getEnforcementMode(): EnforcementMode {
    return this.enforcementMode;
  }

  exportToDOT(): string {
    const lines = ["digraph governance {"];
    const nodeIds = Object.keys(this.graph.nodes).sort();
    const escapeDotLabel = (value: string) => value.replaceAll('"', '\\"');

    for (const nodeId of nodeIds) {
      const node = this.graph.nodes[nodeId]!;
      lines.push(
        `  "${escapeDotLabel(nodeId)}" [label="${escapeDotLabel(node.node_id)} (${node.state})"];`,
      );
    }

    for (const fromNodeId of Object.keys(this.graph.adjacency).sort()) {
      for (const toNodeId of [
        ...(this.graph.adjacency[fromNodeId] ?? []),
      ].sort()) {
        lines.push(
          `  "${escapeDotLabel(fromNodeId)}" -> "${escapeDotLabel(toNodeId)}" [label="dependency"];`,
        );
      }
    }

    lines.push("}");
    return lines.join("\n");
  }

  validateAgentCombination(agents: string[]): ValidationResult {
    const normalizedAgents = agents
      .map((agent) => agent.trim())
      .filter(Boolean);
    const uniqueAgents = [...new Set(normalizedAgents)];
    const warnings: string[] = [];
    const violations: string[] = [];

    if (normalizedAgents.length !== uniqueAgents.length) {
      warnings.push("duplicate agents normalized before validation");
    }

    if (uniqueAgents.length === 0) {
      violations.push("at least one agent is required");
    }

    for (const agentId of uniqueAgents) {
      const node = this.graph.nodes[agentId];
      if (node == null) {
        violations.push(`unknown governance node: ${agentId}`);
        continue;
      }
      if (node.state === "blocked") {
        violations.push(`agent is blocked by governance graph: ${agentId}`);
      }

      const missingApprovers = node.requires_approval_from.filter(
        (approver) => !uniqueAgents.includes(approver),
      );
      if (missingApprovers.length > 0) {
        violations.push(
          `agent ${agentId} missing required approvers: ${missingApprovers.join(", ")}`,
        );
      }
    }

    const selectedAgentSet = new Set(uniqueAgents);
    const visiting = new Set<string>();
    const visited = new Set<string>();
    const hasCycle = (agentId: string): boolean => {
      visiting.add(agentId);
      for (const neighbor of this.graph.adjacency[agentId] ?? []) {
        if (!selectedAgentSet.has(neighbor)) {
          continue;
        }
        if (visiting.has(neighbor)) {
          return true;
        }
        if (!visited.has(neighbor) && hasCycle(neighbor)) {
          return true;
        }
      }
      visiting.delete(agentId);
      visited.add(agentId);
      return false;
    };

    for (const agentId of uniqueAgents) {
      if (!visited.has(agentId) && hasCycle(agentId)) {
        violations.push(
          `selected agent combination contains a dependency cycle: ${agentId}`,
        );
        break;
      }
    }

    return {
      allowed: violations.length === 0,
      mode: this.enforcementMode,
      agents: uniqueAgents,
      warnings,
      violations,
    };
  }

  persist(): void {
    const stateDir = join(this.projectDir, ".omg", "state");
    mkdirSync(stateDir, { recursive: true });
    atomicWriteJson(join(stateDir, GOVERNANCE_GRAPH_FILE), this.graph);
  }

  restore(): boolean {
    const loaded = this.load();
    if (loaded == null) return false;
    this.graph = loaded;
    return true;
  }

  private load(): GovernanceGraph | null {
    const raw = readJsonFile<unknown>(
      join(this.projectDir, ".omg", "state", GOVERNANCE_GRAPH_FILE),
    );
    if (raw == null) return null;
    const result = GovernanceGraphSchema.safeParse(raw);
    return result.success ? result.data : null;
  }

  private detectCycle(): boolean {
    const visited = new Set<string>();
    const inStack = new Set<string>();

    const dfs = (nodeId: string): boolean => {
      visited.add(nodeId);
      inStack.add(nodeId);
      for (const neighbor of this.graph.adjacency[nodeId] ?? []) {
        if (!visited.has(neighbor)) {
          if (dfs(neighbor)) return true;
        } else if (inStack.has(neighbor)) {
          return true;
        }
      }
      inStack.delete(nodeId);
      return false;
    };

    for (const nodeId of Object.keys(this.graph.adjacency)) {
      if (!visited.has(nodeId) && dfs(nodeId)) return true;
    }
    return false;
  }
}
