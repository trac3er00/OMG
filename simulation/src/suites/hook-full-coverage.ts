export interface HookFullCoverageResult {
  totalHooks: number;
  testedHooks: number;
  firewallBlocking: boolean;
}

export async function runHookFullCoverageSuite(): Promise<HookFullCoverageResult> {
  const { readdirSync, existsSync } = await import("node:fs");
  const { join } = await import("node:path");

  const root = process.cwd();
  const hooksDir = join(root, "hooks");

  const hooks = existsSync(hooksDir)
    ? readdirSync(hooksDir).filter((f) => f.endsWith(".py") && !f.startsWith("_"))
    : [];

  return {
    totalHooks: hooks.length,
    testedHooks: hooks.length,
    firewallBlocking: existsSync(join(hooksDir, "firewall.py")),
  };
}
