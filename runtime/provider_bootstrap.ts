import { copyFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { nowIso } from "./common.ts";

type ProviderMeta = {
  provider: string;
  command: string;
};

const PROVIDERS: ProviderMeta[] = [
  { provider: "codex", command: "codex" },
  { provider: "gemini", command: "gemini" },
  { provider: "opencode", command: "opencode" },
  { provider: "kimi", command: "kimi" }
];

function commandExists(command: string): boolean {
  const proc = Bun.spawnSync({
    cmd: ["bash", "-lc", `command -v ${command}`],
    stdout: "ignore",
    stderr: "ignore"
  });
  return proc.exitCode === 0;
}

export function collectProviderStatusWithOptions(
  projectDir: string,
  options: { includeSmoke?: boolean; smokeHostMode?: string } = {}
) {
  const providers = PROVIDERS.map((provider) => {
    const installed = commandExists(provider.command);
    return {
      provider: provider.provider,
      command: provider.command,
      installed,
      smoke_host_mode: options.smokeHostMode || "claude_dispatch",
      parity_state: installed ? "ready" : "blocked",
      native_ready: installed,
      dispatch_ready: installed,
      local_steps: installed ? [] : [`install_${provider.command}_cli`],
      provider_steps: installed ? [] : ["login_to_provider"],
      native_ready_reasons: installed ? [] : ["provider_cli_missing"],
      dispatch_ready_reasons: installed ? [] : ["provider_cli_missing"],
      smoke_status: options.includeSmoke ? (installed ? "ready" : "blocked") : "not-requested"
    };
  });
  return {
    schema: "OmgProviderStatus",
    status: "ok",
    generated_at: nowIso(),
    project_dir: projectDir,
    providers
  };
}

export function collectProviderStatus(projectDir: string) {
  return collectProviderStatusWithOptions(projectDir);
}

export function bootstrapProviderHosts(projectDir: string) {
  return {
    status: "ok",
    schema: "OmgProviderBootstrap",
    generated_at: nowIso(),
    project_dir: projectDir,
    actions: PROVIDERS.map((provider) => ({
      provider: provider.provider,
      action: "noop"
    }))
  };
}

export function repairProviderHosts(projectDir: string, provider: string) {
  const configPath =
    provider === "codex"
      ? join(process.env.HOME || "", ".codex", "config.toml")
      : provider === "gemini"
        ? join(process.env.HOME || "", ".gemini", "config.toml")
        : "";
  let backup = "";
  let changed = false;
  if (configPath && existsSync(configPath)) {
    backup = `${configPath}.bak.${Date.now()}`;
    copyFileSync(configPath, backup);
    const cleaned = readFileSync(configPath, "utf8").replace(/^.*rmcp_client.*$\n?/gm, "");
    if (cleaned !== readFileSync(configPath, "utf8")) {
      writeFileSync(configPath, cleaned, "utf8");
      changed = true;
    }
  }
  return {
    status: "ok",
    schema: "OmgProviderRepair",
    generated_at: nowIso(),
    project_dir: projectDir,
    provider,
    changed,
    backup
  };
}
