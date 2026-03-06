import { collectProviderStatusWithOptions } from "./provider_bootstrap.ts";
import { nowIso } from "./common.ts";

export function runProviderSmokeMatrix(input: {
  project_dir: string;
  provider?: string;
  host_mode?: string;
}) {
  const status = collectProviderStatusWithOptions(input.project_dir, {
    includeSmoke: true,
    smokeHostMode: input.host_mode || "claude_dispatch"
  });
  const selected = String(input.provider || "all");
  const providers = status.providers.filter((entry: any) => selected === "all" || entry.provider === selected);
  const results = providers.map((entry: any) => {
    if (!entry.installed) {
      return { provider: entry.provider, status: "skipped", reason: "provider_cli_missing" };
    }
    const proc = Bun.spawnSync({ cmd: [entry.command, "--version"], stdout: "pipe", stderr: "pipe" });
    return {
      provider: entry.provider,
      status: proc.exitCode === 0 ? "passed" : "failed",
      exit_code: proc.exitCode,
      stdout: proc.stdout.toString().trim(),
      stderr: proc.stderr.toString().trim()
    };
  });
  return {
    schema: "OmgProviderSmokeMatrix",
    status: "ok",
    generated_at: nowIso(),
    results
  };
}
