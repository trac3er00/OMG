import { describe, test, expect, beforeEach, afterEach } from "bun:test";
import { mkdirSync, rmSync, existsSync } from "node:fs";
import { join } from "node:path";
import {
  GOVERNANCE_VERSION,
  ALLOWED_TRANSITIONS,
  GovernanceGraphRuntime,
} from "./graph.js";

const TEST_DIR = "/tmp/omg-governance-test";

beforeEach(() => {
  rmSync(TEST_DIR, { recursive: true, force: true });
  mkdirSync(join(TEST_DIR, ".omg", "state"), { recursive: true });
});
afterEach(() => rmSync(TEST_DIR, { recursive: true, force: true }));

describe("governance/graph", () => {
  test("GOVERNANCE_VERSION is 1.0.0", () => {
    expect(GOVERNANCE_VERSION).toBe("1.0.0");
  });

  describe("ALLOWED_TRANSITIONS", () => {
    test("planning → implementing is allowed", () => {
      expect(ALLOWED_TRANSITIONS["planning"]).toContain("implementing");
    });

    test("complete → anything is not allowed (empty array)", () => {
      expect(ALLOWED_TRANSITIONS["complete"].length).toBe(0);
    });

    test("planning → deploying is NOT allowed (skip)", () => {
      expect(ALLOWED_TRANSITIONS["planning"]).not.toContain("deploying");
    });
  });

  describe("GovernanceGraphRuntime", () => {
    describe("addNode", () => {
      test("adds node with default planning state", () => {
        const runtime = new GovernanceGraphRuntime(TEST_DIR);
        const node = runtime.addNode("task-1");
        expect(node.node_id).toBe("task-1");
        expect(node.state).toBe("planning");
      });

      test("adds node with custom initial state", () => {
        const runtime = new GovernanceGraphRuntime(TEST_DIR);
        const node = runtime.addNode("task-1", "implementing");
        expect(node.state).toBe("implementing");
      });
    });

    describe("transition", () => {
      test("allowed transition succeeds", () => {
        const runtime = new GovernanceGraphRuntime(TEST_DIR);
        runtime.addNode("task-1");
        const result = runtime.transition("task-1", "implementing");
        expect(result.success).toBe(true);
        expect(result.from).toBe("planning");
        expect(result.to).toBe("implementing");
      });

      test("unauthorized transition fails", () => {
        const runtime = new GovernanceGraphRuntime(TEST_DIR);
        runtime.addNode("task-1");
        const result = runtime.transition("task-1", "deploying");
        expect(result.success).toBe(false);
        expect(result.error).toContain("unauthorized_transition");
      });

      test("state persists after transition", () => {
        const runtime = new GovernanceGraphRuntime(TEST_DIR);
        runtime.addNode("task-1");
        runtime.transition("task-1", "implementing");
        expect(runtime.getNode("task-1")?.state).toBe("implementing");
      });

      test("unknown node transition fails", () => {
        const runtime = new GovernanceGraphRuntime(TEST_DIR);
        const result = runtime.transition("nonexistent", "implementing");
        expect(result.success).toBe(false);
        expect(result.error).toContain("Unknown node");
      });

      test("full state machine walkthrough", () => {
        const runtime = new GovernanceGraphRuntime(TEST_DIR);
        runtime.addNode("task-1");
        expect(runtime.transition("task-1", "implementing").success).toBe(true);
        expect(runtime.transition("task-1", "reviewing").success).toBe(true);
        expect(runtime.transition("task-1", "deploying").success).toBe(true);
        expect(runtime.transition("task-1", "complete").success).toBe(true);
      });
    });

    describe("cycle detection", () => {
      test("rejects circular approval chains", () => {
        const runtime = new GovernanceGraphRuntime(TEST_DIR);
        runtime.addNode("A");
        runtime.addNode("B");
        runtime.addEdge("A", "B");
        expect(() => runtime.addEdge("B", "A")).toThrow("cycle_detected");
      });

      test("allows acyclic chains", () => {
        const runtime = new GovernanceGraphRuntime(TEST_DIR);
        runtime.addNode("A");
        runtime.addNode("B");
        runtime.addNode("C");
        expect(() => {
          runtime.addEdge("A", "B");
          runtime.addEdge("B", "C");
        }).not.toThrow();
      });
    });

    describe("compliance enforcement", () => {
      test("dot-export", () => {
        const runtime = new GovernanceGraphRuntime(TEST_DIR);
        runtime.addNode("agent-A");
        runtime.addNode("agent-B", "implementing");
        runtime.addEdge("agent-A", "agent-B");

        const dot = runtime.exportToDOT();
        expect(dot.startsWith("digraph")).toBe(true);
        expect(dot).toContain('"agent-A"');
        expect(dot).toContain('"agent-A" -> "agent-B" [label="dependency"]');
      });

      test("validate-combination", () => {
        const runtime = new GovernanceGraphRuntime(TEST_DIR);
        runtime.addNode("agent-a");
        runtime.addNode("agent-b", "implementing", {
          requires_approval_from: ["agent-a"],
        });

        const result = runtime.validateAgentCombination(["agent-a", "agent-b"]);
        expect(result.allowed).toBe(true);
        expect(result.violations).toHaveLength(0);
      });

      test("advisory-mode", () => {
        const runtime = new GovernanceGraphRuntime(TEST_DIR);
        expect(runtime.getEnforcementMode()).toBe("advisory");
      });
    });

    describe("persist and restore", () => {
      test("persist creates governance-graph.json", () => {
        const runtime = new GovernanceGraphRuntime(TEST_DIR);
        runtime.addNode("task-1");
        runtime.persist();
        const graphPath = join(
          TEST_DIR,
          ".omg",
          "state",
          "governance-graph.json",
        );
        expect(existsSync(graphPath)).toBe(true);
      });

      test("restore recovers graph state within 5s", () => {
        const runtime = new GovernanceGraphRuntime(TEST_DIR);
        runtime.addNode("task-1");
        runtime.transition("task-1", "implementing");
        runtime.persist();

        const start = Date.now();
        const restored = new GovernanceGraphRuntime(TEST_DIR);
        restored.restore();
        const elapsed = Date.now() - start;

        expect(elapsed).toBeLessThan(5000);
        expect(restored.getNode("task-1")?.state).toBe("implementing");
      });
    });
  });
});
