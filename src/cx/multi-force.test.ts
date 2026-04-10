import { describe, expect, test } from "bun:test";

import {
  parallelDispatch,
  routeToStrongest,
  type ParallelDispatchProvider,
} from "./multi-force.js";

describe("routeToStrongest", () => {
  const providers = ["claude", "gemini", "ollama"] as const;

  test("coding task selects Claude", () => {
    expect(
      routeToStrongest("implement a TypeScript API refactor", providers),
    ).toBe("claude");
  });

  test("research task selects Gemini", () => {
    expect(
      routeToStrongest(
        "research tradeoffs between vector databases",
        providers,
      ),
    ).toBe("gemini");
  });

  test("trivial task selects Ollama", () => {
    expect(routeToStrongest("quick typo fix", providers)).toBe("ollama");
  });

  test("single provider falls back gracefully", () => {
    expect(routeToStrongest("implement a new endpoint", ["gemini"])).toBe(
      "gemini",
    );
  });
});

describe("parallelDispatch", () => {
  test("queries multiple providers and selects the best result", async () => {
    const calls: string[] = [];
    const providers: ParallelDispatchProvider<{
      text: string;
      score: number;
    }>[] = [
      {
        name: "claude",
        dispatch: async () => {
          calls.push("claude");
          await Bun.sleep(25);
          return { text: "solid answer", score: 0.82 };
        },
        evaluate: (result) => result.score,
      },
      {
        name: "gemini",
        dispatch: async () => {
          calls.push("gemini");
          await Bun.sleep(25);
          return { text: "best answer", score: 0.97 };
        },
        evaluate: (result) => result.score,
      },
    ];

    const startedAt = Date.now();
    const result = await parallelDispatch(
      "research the best caching strategy",
      providers,
    );
    const elapsedMs = Date.now() - startedAt;

    expect(calls.sort()).toEqual(["claude", "gemini"]);
    expect(result.provider).toBe("gemini");
    expect(result.result).toEqual({ text: "best answer", score: 0.97 });
    expect(result.candidates).toHaveLength(2);
    expect(elapsedMs).toBeLessThan(45);
  });

  test("ties prefer the strongest routed provider", async () => {
    const result = await parallelDispatch("implement auth middleware", [
      {
        name: "claude",
        dispatch: async () => ({ text: "claude", score: 0.9 }),
        evaluate: (candidate) => candidate.score,
      },
      {
        name: "gemini",
        dispatch: async () => ({ text: "gemini", score: 0.9 }),
        evaluate: (candidate) => candidate.score,
      },
    ]);

    expect(result.provider).toBe("claude");
  });
});
