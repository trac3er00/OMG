export interface SubagentOrchestrationResult {
  agentTypesFound: string[];
  routingLogicPresent: boolean;
  parallelDispatchSupported: boolean;
}

export async function runSubagentOrchestrationSuite(): Promise<SubagentOrchestrationResult> {
  const { readFileSync, existsSync } = await import("node:fs");
  const { join } = await import("node:path");

  const root = process.cwd();
  const registryPath = join(root, "hooks", "_agent_registry.py");
  const routerPath = join(root, "src", "orchestration", "router.js");

  const registryContent = existsSync(registryPath) ? readFileSync(registryPath, "utf-8") : "";
  const agentTypes = ["explore", "librarian", "oracle"].filter((agentType) =>
    registryContent.includes(agentType),
  );

  return {
    agentTypesFound: agentTypes,
    routingLogicPresent: existsSync(routerPath),
    parallelDispatchSupported:
      registryContent.includes("background") || registryContent.includes("parallel"),
  };
}
