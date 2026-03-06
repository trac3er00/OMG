import { collectProviderStatusWithOptions } from "./provider_bootstrap.ts";

function git(projectDir: string, args: string[]): string {
  const proc = Bun.spawnSync({
    cmd: ["git", ...args],
    cwd: projectDir,
    stdout: "pipe",
    stderr: "pipe"
  });
  return proc.exitCode === 0 ? proc.stdout.toString().trim() : "";
}

export function collectReleaseReadiness(projectDir: string) {
  const providerStatus = collectProviderStatusWithOptions(projectDir, {
    includeSmoke: true,
    smokeHostMode: "claude_dispatch"
  });
  const providers = providerStatus.providers as Array<Record<string, unknown>>;
  const blocked = providers
    .filter((entry) => String(entry.parity_state) === "blocked")
    .map((entry) => String(entry.provider));
  const native_ready = providers
    .filter((entry) => Boolean(entry.native_ready))
    .map((entry) => String(entry.provider));
  const blockers = providers.flatMap((entry) => [
    ...(Array.isArray(entry.local_steps) ? (entry.local_steps as string[]).map((step) => `${entry.provider}: ${step}`) : []),
    ...(Array.isArray(entry.provider_steps) ? (entry.provider_steps as string[]).map((step) => `${entry.provider}: ${step}`) : [])
  ]);
  const statusLines = git(projectDir, ["status", "--short"])
    .split(/\r?\n/)
    .filter(Boolean);
  return {
    schema: "OmgReleaseReadiness",
    status: "ok",
    git: {
      branch: git(projectDir, ["branch", "--show-current"]),
      dirty: statusLines.length > 0,
      status_lines: statusLines
    },
    providers: {
      blocked,
      native_ready,
      matrix: providerStatus
    },
    blockers,
    ready_for_release: blocked.length === 0 && statusLines.length === 0
  };
}
