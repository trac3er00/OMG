export type RuntimeIdea = Record<string, unknown>;

export function dispatchRuntime(runtime: string, idea: RuntimeIdea) {
  const goal = typeof idea.goal === "string" ? idea.goal : "unspecified";
  return {
    status: "ok",
    schema: "RuntimeDispatchResult",
    runtime,
    goal,
    acceptance: Array.isArray(idea.acceptance) ? idea.acceptance : [],
    verification: {
      checks: [
        {
          name: "runtime-contract",
          status: "unverified",
          command: `omg runtime dispatch --runtime ${runtime}`
        }
      ]
    },
    plan: {
      route: runtime,
      summary: `Dispatch ${runtime} runtime for "${goal}".`
    }
  };
}
