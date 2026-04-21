export interface MultiAIEscalationResult {
  routingAccuracy: boolean;
  fallbackChainValid: boolean;
  costTierCompliant: boolean;
  providersFound: string[];
}

export async function runMultiAIEscalationSuite(): Promise<MultiAIEscalationResult> {
  const { readFileSync } = await import("node:fs");
  const { join } = await import("node:path");

  const root = process.cwd();
  const multiForce = readFileSync(join(root, "src/cx/multi-force.ts"), "utf-8");
  const equalizer = readFileSync(join(root, "runtime/equalizer.py"), "utf-8");
  const registry = readFileSync(
    join(root, "runtime/providers/provider_registry.py"),
    "utf-8",
  );

  const providers = ["claude", "codex", "gemini", "kimi", "ollama-cloud"];
  const providersFound = providers.filter(
    (provider) =>
      multiForce.includes(provider) &&
      equalizer.includes(provider) &&
      registry.includes(provider),
  );

  return {
    routingAccuracy:
      multiForce.includes("PROVIDER_STRENGTHS") &&
      multiForce.includes("routeToStrongest") &&
      multiForce.includes("ollama-cloud"),
    fallbackChainValid:
      multiForce.includes("CATEGORY_FALLBACKS") &&
      multiForce.includes("ollama-cloud"),
    costTierCompliant:
      equalizer.includes("_COST_TIERS") &&
      equalizer.includes('"claude": "high"') &&
      equalizer.includes('"codex": "medium"') &&
      equalizer.includes('"ollama-cloud": "low"'),
    providersFound,
  };
}
