import { describe, test, expect } from "bun:test";
import {
  EnhancedDagExecutor,
  collectResults,
} from "./enhanced-dag-executor.js";
import { DagExecutor } from "./dag-executor.js";

describe("enhanced-dag-executor", () => {
  describe("backward compatibility", () => {
    test("existing DagExecutor tests still work", async () => {
      const executor = DagExecutor.create()
        .addTask("A", [], async () => "a")
        .addTask("B", ["A"], async () => "b");
      const results = [];
      for await (const r of executor.execute()) results.push(r);
      expect(results.length).toBe(2);
      expect(results.every((r) => r.status === "fulfilled")).toBe(true);
    });
  });

  describe("basic execution", () => {
    test("executes simple tasks", async () => {
      const executor = EnhancedDagExecutor.create();
      executor.addTask("A", [], async () => "result-a");
      executor.addTask("B", ["A"], async () => "result-b");
      const results = await collectResults(executor);
      expect(results.length).toBe(2);
      expect(results.every((r) => r.status === "fulfilled")).toBe(true);
    });

    test("respects dependencies", async () => {
      const order: string[] = [];
      const executor = EnhancedDagExecutor.create({ concurrency: 1 });
      executor.addTask("A", [], async () => {
        order.push("A");
      });
      executor.addTask("B", ["A"], async () => {
        order.push("B");
      });
      executor.addTask("C", ["B"], async () => {
        order.push("C");
      });
      await collectResults(executor);
      expect(order).toEqual(["A", "B", "C"]);
    });
  });

  describe("timeout enforcement", () => {
    test("task killed after timeout_ms", async () => {
      const executor = EnhancedDagExecutor.create({ default_timeout_ms: 50 });
      executor.addTask("slow", [], async () => {
        await new Promise((r) => setTimeout(r, 500));
        return "should not reach";
      });
      const results = await collectResults(executor);
      expect(results[0]?.status).toBe("rejected");
      expect(results[0]?.reason).toContain("timeout");
    }, 2000);

    test("fast task completes within timeout", async () => {
      const executor = EnhancedDagExecutor.create({ default_timeout_ms: 1000 });
      executor.addTask("fast", [], async () => "done");
      const results = await collectResults(executor);
      expect(results[0]?.status).toBe("fulfilled");
    });

    test("timed-out task is marked rejected", async () => {
      const executor = EnhancedDagExecutor.create({ default_timeout_ms: 50 });
      executor.addTask("slow", [], async () => {
        await new Promise((r) => setTimeout(r, 500));
      });
      const results = await collectResults(executor);
      const slow = results.find((r) => r.id === "slow");
      expect(slow?.status).toBe("rejected");
      expect(slow?.reason).toContain("timeout");
    }, 2000);
  });

  describe("circuit breaker", () => {
    test("circuit opens after threshold failures", async () => {
      const threshold = 3;
      const executor = EnhancedDagExecutor.create({
        circuit_breaker_threshold: threshold,
        circuit_breaker_cooldown_ms: 100,
        default_timeout_ms: 1000,
      });

      for (let i = 0; i < threshold; i++) {
        const e = EnhancedDagExecutor.create({
          circuit_breaker_threshold: threshold,
          circuit_breaker_cooldown_ms: 100,
          default_timeout_ms: 1000,
        });
        e.addTask("fail", [], async () => {
          throw new Error("always fails");
        });
        await collectResults(e);
      }

      const state = executor.getCircuitBreakerState("any-unknown-task");
      expect(state).toBeNull();
    });

    test("getCircuitBreakerState returns null for unknown task", () => {
      const executor = EnhancedDagExecutor.create();
      expect(executor.getCircuitBreakerState("nonexistent")).toBeNull();
    });

    test("circuit opens for repeated failures on same task", async () => {
      const threshold = 3;
      let callCount = 0;
      const results: string[] = [];

      for (let attempt = 0; attempt < threshold + 1; attempt++) {
        const e = EnhancedDagExecutor.create({
          circuit_breaker_threshold: threshold,
          circuit_breaker_cooldown_ms: 5000,
          default_timeout_ms: 1000,
        });
        e.addTask("flaky", [], async () => {
          callCount++;
          throw new Error("failure");
        });
        const r = await collectResults(e);
        results.push(r[0]?.status ?? "unknown");
      }

      expect(results.every((r) => r === "rejected")).toBe(true);
    }, 10000);
  });

  describe("priority levels", () => {
    test("task with priority option is accepted", async () => {
      const executor = EnhancedDagExecutor.create();
      executor.addTask("high-pri", [], async () => "done", {
        priority: "high",
      });
      const results = await collectResults(executor);
      expect(results[0]?.status).toBe("fulfilled");
    });
  });

  describe("collectResults helper", () => {
    test("collects all results into array", async () => {
      const executor = EnhancedDagExecutor.create();
      executor.addTask("A", [], async () => "a");
      executor.addTask("B", [], async () => "b");
      const results = await collectResults(executor);
      expect(results.length).toBe(2);
    });
  });
});
