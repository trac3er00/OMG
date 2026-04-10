import type { EvalSuiteDefinition } from "../runner.js";
import {
  GovernanceGraphRuntime,
  ALLOWED_TRANSITIONS,
  type GovernanceState,
} from "../../governance/graph.js";
import { GovernanceLedger } from "../../governance/ledger.js";
import { ToolFabric } from "../../governance/tool-fabric.js";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

function withTempDir<T>(fn: (dir: string) => T): T {
  const dir = mkdtempSync(join(tmpdir(), "omg-eval-gov-"));
  try {
    return fn(dir);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const suite: EvalSuiteDefinition = {
  module: "governance",
  description:
    "Evaluates governance decision quality: state transitions, ledger integrity, tool fabric enforcement",
  cases: [
    {
      name: "state-transition-correctness",
      weight: 2,
      run: () =>
        withTempDir((dir) => {
          const graph = new GovernanceGraphRuntime(dir);
          graph.addNode("task-1", "planning");

          let correctTransitions = 0;
          let totalTransitions = 0;

          const validPaths: Array<[GovernanceState, GovernanceState]> = [
            ["planning", "implementing"],
            ["implementing", "reviewing"],
            ["reviewing", "deploying"],
            ["deploying", "complete"],
          ];

          for (const [from, to] of validPaths) {
            totalTransitions++;
            graph.addNode(`valid-${from}-${to}`, from);
            const result = graph.transition(`valid-${from}-${to}`, to);
            if (result.success) correctTransitions++;
          }

          const invalidPaths: Array<[GovernanceState, GovernanceState]> = [
            ["planning", "complete"],
            ["complete", "implementing"],
            ["reviewing", "planning"],
          ];

          for (const [from, to] of invalidPaths) {
            totalTransitions++;
            graph.addNode(`invalid-${from}-${to}`, from);
            const result = graph.transition(`invalid-${from}-${to}`, to);
            if (!result.success) correctTransitions++;
          }

          const score = Math.round(
            (correctTransitions / totalTransitions) * 100,
          );
          return {
            passed: score >= 90,
            score,
            details: `${correctTransitions}/${totalTransitions} transitions correct`,
          };
        }),
    },
    {
      name: "allowed-transitions-completeness",
      weight: 1,
      run: () => {
        const states = Object.keys(ALLOWED_TRANSITIONS) as GovernanceState[];
        const hasAllStates = states.length >= 6;
        const completeHasNoTransitions =
          (ALLOWED_TRANSITIONS.complete ?? []).length === 0;
        const blockedCanReturnToPlanning = (
          ALLOWED_TRANSITIONS.blocked ?? []
        ).includes("planning");

        let checks = 0;
        let passed = 0;

        checks++;
        if (hasAllStates) passed++;
        checks++;
        if (completeHasNoTransitions) passed++;
        checks++;
        if (blockedCanReturnToPlanning) passed++;

        const score = Math.round((passed / checks) * 100);
        return {
          passed: score === 100,
          score,
          details: `${passed}/${checks} completeness checks`,
        };
      },
    },
    {
      name: "ledger-integrity-chain",
      weight: 2,
      run: () =>
        withTempDir((dir) => {
          const ledger = new GovernanceLedger(dir);

          ledger.append({
            agent_id: "agent-1",
            node_id: "task-1",
            from_state: "planning",
            to_state: "implementing",
          });
          ledger.append({
            agent_id: "agent-2",
            node_id: "task-1",
            from_state: "implementing",
            to_state: "reviewing",
          });
          ledger.append({
            agent_id: "agent-1",
            node_id: "task-2",
            from_state: "planning",
            to_state: "implementing",
          });

          const integrity = ledger.verifyIntegrity();
          const entries = ledger.readAll();
          const hasCorrectChaining = entries.length === 3;
          const hashesUnique =
            new Set(entries.map((e) => e.hash)).size === entries.length;

          let score = 0;
          if (integrity.valid) score += 50;
          if (hasCorrectChaining) score += 25;
          if (hashesUnique) score += 25;

          return {
            passed: score >= 90,
            score,
            details: `integrity=${integrity.valid}, entries=${entries.length}, unique_hashes=${hashesUnique}`,
          };
        }),
    },
    {
      name: "tool-fabric-lane-enforcement",
      weight: 2,
      run: () =>
        withTempDir(async (dir) => {
          const fabric = new ToolFabric(dir);

          fabric.registerLane("strict", {
            allowedTools: ["read", "search"],
            requiresSignedApproval: false,
          });
          fabric.registerLane("locked", {
            allowedTools: ["read"],
            requiresSignedApproval: true,
          });

          let correct = 0;
          let total = 0;

          total++;
          const allowed = await fabric.evaluateRequest("read", {}, "strict");
          if (allowed.action === "allow") correct++;

          total++;
          const denied = await fabric.evaluateRequest("write", {}, "strict");
          if (denied.action === "deny") correct++;

          total++;
          const noApproval = await fabric.evaluateRequest("read", {}, "locked");
          if (noApproval.action === "deny") correct++;

          total++;
          const withApproval = await fabric.evaluateRequest(
            "read",
            { signedApproval: true },
            "locked",
          );
          if (withApproval.action === "allow") correct++;

          total++;
          const defaultLane = await fabric.evaluateRequest(
            "anything",
            {},
            "default",
          );
          if (defaultLane.action === "allow") correct++;

          fabric.close();

          const score = Math.round((correct / total) * 100);
          return {
            passed: score >= 80,
            score,
            details: `${correct}/${total} enforcement decisions correct`,
          };
        }),
    },
    {
      name: "governance-graph-cycle-detection",
      weight: 1,
      run: () =>
        withTempDir((dir) => {
          const graph = new GovernanceGraphRuntime(dir);
          graph.addNode("a", "planning");
          graph.addNode("b", "planning");
          graph.addNode("c", "planning");

          graph.addEdge("a", "b");
          graph.addEdge("b", "c");

          let cycleDetected = false;
          try {
            graph.addEdge("c", "a");
          } catch (err) {
            if (
              err instanceof Error &&
              err.message.includes("cycle_detected")
            ) {
              cycleDetected = true;
            }
          }

          const score = cycleDetected ? 100 : 0;
          return {
            passed: cycleDetected,
            score,
            details: `cycle_detected=${cycleDetected}`,
          };
        }),
    },
  ],
};

export default suite;
