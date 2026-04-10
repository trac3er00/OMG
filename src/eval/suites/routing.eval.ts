import type { EvalSuiteDefinition } from "../runner.js";
import { TeamRouter } from "../../orchestration/router.js";
import type { TeamDispatchRequest } from "../../interfaces/orchestration.js";

function makeRequest(target: string, problem: string): TeamDispatchRequest {
  return { target, problem, context: "" };
}

const suite: EvalSuiteDefinition = {
  module: "routing",
  description:
    "Evaluates routing decision accuracy: target selection, signal detection, cost optimization",
  cases: [
    {
      name: "explicit-target-routing",
      weight: 2,
      run: async () => {
        const router = TeamRouter.create();
        let correct = 0;
        let total = 0;

        const explicitCases: Array<[string, string, string]> = [
          ["codex", "Build the API", "codex"],
          ["gemini", "Research best practices", "gemini"],
          ["ccg", "Full stack implementation", "ccg"],
        ];

        for (const [target, problem, expected] of explicitCases) {
          total++;
          const result = await router.route(makeRequest(target, problem));
          if (result.evidence.selected_target === expected) correct++;
        }

        const score = Math.round((correct / total) * 100);
        return {
          passed: score >= 90,
          score,
          details: `${correct}/${total} explicit routes correct`,
        };
      },
    },
    {
      name: "auto-routing-code-signals",
      weight: 2,
      run: async () => {
        const router = TeamRouter.create();
        let correct = 0;
        let total = 0;

        const codeProblems = [
          "Build a React component for user authentication",
          "Fix the TypeScript compilation bug in the API backend",
          "Create a new JavaScript module for data processing",
        ];

        for (const problem of codeProblems) {
          total++;
          const result = await router.route(makeRequest("auto", problem));
          if (result.evidence.selected_target === "codex") correct++;
        }

        const score = Math.round((correct / total) * 100);
        return {
          passed: score >= 66,
          score,
          details: `${correct}/${total} code-signal routes to codex`,
        };
      },
    },
    {
      name: "auto-routing-research-signals",
      weight: 2,
      run: async () => {
        const router = TeamRouter.create();
        let correct = 0;
        let total = 0;

        const researchProblems = [
          "Research the latest trends in AI safety",
          "Investigate performance analysis methods",
          "Compare different database architectures in a survey",
        ];

        for (const problem of researchProblems) {
          total++;
          const result = await router.route(makeRequest("auto", problem));
          if (result.evidence.selected_target === "gemini") correct++;
        }

        const score = Math.round((correct / total) * 100);
        return {
          passed: score >= 66,
          score,
          details: `${correct}/${total} research-signal routes to gemini`,
        };
      },
    },
    {
      name: "multi-provider-ccg-detection",
      weight: 1,
      run: async () => {
        const router = TeamRouter.create();
        let correct = 0;
        let total = 0;

        const ccgProblems = [
          "Use codex and gemini to build and test the feature",
          "Run tri-track analysis on the codebase",
        ];

        for (const problem of ccgProblems) {
          total++;
          const result = await router.route(makeRequest("auto", problem));
          if (result.evidence.selected_target === "ccg") correct++;
          if (result.evidence.parallel_execution === true) correct++;
          total++;
        }

        const score = Math.round((correct / total) * 100);
        return {
          passed: score >= 75,
          score,
          details: `${correct}/${total} ccg detection checks`,
        };
      },
    },
    {
      name: "cost-tier-fallback",
      weight: 1,
      run: async () => {
        const router = TeamRouter.create();

        const result = await router.route(
          makeRequest("auto", "do something generic with no signal words"),
        );

        const costRanking = result.evidence.cost_ranking as string[];
        const isGeminiFirst = costRanking[0] === "gemini";
        const selectedTarget = result.evidence.selected_target;
        const fallsToLowestCost = selectedTarget === "gemini";

        let score = 0;
        if (isGeminiFirst) score += 50;
        if (fallsToLowestCost) score += 50;

        return {
          passed: score >= 50,
          score,
          details: `lowest_cost_first=${isGeminiFirst}, fallback_correct=${fallsToLowestCost}`,
        };
      },
    },
    {
      name: "route-result-structure",
      weight: 1,
      run: async () => {
        const router = TeamRouter.create();
        const result = await router.route(
          makeRequest("auto", "build a component"),
        );

        let checks = 0;
        let passed = 0;

        checks++;
        if (result.status === "ok") passed++;
        checks++;
        if (Array.isArray(result.findings) && result.findings.length > 0)
          passed++;
        checks++;
        if (Array.isArray(result.actions) && result.actions.length > 0)
          passed++;
        checks++;
        if (result.evidence.selected_target) passed++;
        checks++;
        if (result.evidence.selection_reason) passed++;
        checks++;
        if (result.evidence.cost_ranking) passed++;

        const score = Math.round((passed / checks) * 100);
        return {
          passed: score >= 80,
          score,
          details: `${passed}/${checks} structural checks`,
        };
      },
    },
  ],
};

export default suite;
