import { existsSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { nowIso, readJsonFile } from "./common.ts";
import { collectProviderStatusWithOptions } from "./provider_bootstrap.ts";

const STABLE_METADATA_FILES = [
  "package.json",
  "README.md",
  "settings.json",
  ".claude-plugin/plugin.json",
  ".claude-plugin/marketplace.json",
  "plugins/core/plugin.json",
  "plugins/advanced/plugin.json",
  "runtime/compat.ts"
];

const DEPRECATED_PROVIDER_FILES = [
  "README.md",
  "plugins/README.md",
  "hud/omg-hud.mjs",
  "runtime/provider_bootstrap.ts"
];

const REQUIRED_INSTALL_SCRIPTS = [
  "OMG-setup.sh",
  ".claude-plugin/scripts/install.sh",
  ".claude-plugin/scripts/update.sh",
  ".claude-plugin/scripts/uninstall.sh"
];

function git(projectDir: string, args: string[]): string {
  const proc = Bun.spawnSync({
    cmd: ["git", ...args],
    cwd: projectDir,
    stdout: "pipe",
    stderr: "pipe"
  });
  return proc.exitCode === 0 ? proc.stdout.toString().trim() : "";
}

function readTextIfPresent(projectDir: string, relativePath: string): string {
  const path = join(projectDir, relativePath);
  return existsSync(path) ? readFileSync(path, "utf8") : "";
}

function isExecutable(projectDir: string, relativePath: string): boolean {
  const path = join(projectDir, relativePath);
  if (!existsSync(path)) {
    return false;
  }
  return (statSync(path).mode & 0o111) !== 0;
}

function collectStableMetadataBlockers(projectDir: string): string[] {
  const blockers: string[] = [];
  const betaPattern = /\b2\.0\.0-beta\.\d+\b|\bv2\.0\.0-beta\.\d+\b/;

  for (const relativePath of STABLE_METADATA_FILES) {
    const content = readTextIfPresent(projectDir, relativePath);
    if (content && betaPattern.test(content)) {
      blockers.push(`beta marker in ${relativePath}`);
    }
  }

  const pkg = readJsonFile<Record<string, unknown>>(join(projectDir, "package.json"), {});
  if (String(pkg.version || "").includes("-beta.")) {
    blockers.push("beta marker in package.json");
  }

  return [...new Set(blockers)];
}

function collectDeprecatedProviderBlockers(projectDir: string): string[] {
  const blockers: string[] = [];

  for (const relativePath of DEPRECATED_PROVIDER_FILES) {
    const content = readTextIfPresent(projectDir, relativePath);
    if (content && /\bopencode\b/i.test(content)) {
      blockers.push(`deprecated provider token in ${relativePath}`);
    }
  }

  return blockers;
}

function collectPackagingBlockers(projectDir: string): string[] {
  const blockers: string[] = [];
  const pkg = readJsonFile<Record<string, any>>(join(projectDir, "package.json"), {});
  const scripts = pkg.scripts && typeof pkg.scripts === "object" ? (pkg.scripts as Record<string, string>) : {};

  if (scripts.postinstall !== "bash ./OMG-setup.sh install --non-interactive") {
    blockers.push("packaged install smoke missing: package.json postinstall must use bash ./OMG-setup.sh");
  }
  if (scripts.update !== "bash ./OMG-setup.sh update") {
    blockers.push("packaged install smoke missing: package.json update must use bash ./OMG-setup.sh");
  }
  if (scripts.uninstall !== "bash ./OMG-setup.sh uninstall") {
    blockers.push("packaged install smoke missing: package.json uninstall must use bash ./OMG-setup.sh");
  }

  const npmignore = readTextIfPresent(projectDir, ".npmignore");
  if (npmignore) {
    const ignoresInstallScript = npmignore.split(/\r?\n/).some((line) => line.trim() === "install.sh");
    const restoresPluginInstallScript = npmignore
      .split(/\r?\n/)
      .some((line) => line.trim() === "!.claude-plugin/scripts/install.sh");
    if (ignoresInstallScript && !restoresPluginInstallScript) {
      blockers.push("packaged install smoke missing: .npmignore excludes .claude-plugin/scripts/install.sh");
    }
  }

  for (const relativePath of REQUIRED_INSTALL_SCRIPTS) {
    const path = join(projectDir, relativePath);
    if (!existsSync(path)) {
      blockers.push(`packaged install smoke missing: ${relativePath}`);
      continue;
    }
    if (!isExecutable(projectDir, relativePath)) {
      blockers.push(`packaged install smoke missing: ${relativePath} is not executable`);
    }
  }

  return blockers;
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

  const staticBlockers = {
    stable_metadata: collectStableMetadataBlockers(projectDir),
    deprecated_provider_tokens: collectDeprecatedProviderBlockers(projectDir),
    packaged_install_smoke: collectPackagingBlockers(projectDir)
  };

  const statusLines = git(projectDir, ["status", "--short"])
    .split(/\r?\n/)
    .filter(Boolean);
  const blockers = [
    ...staticBlockers.stable_metadata,
    ...staticBlockers.deprecated_provider_tokens,
    ...staticBlockers.packaged_install_smoke,
    ...(statusLines.length > 0 ? ["git working tree is dirty"] : [])
  ];

  return {
    schema: "OmgReleaseReadiness",
    status: "ok",
    generated_at: nowIso(),
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
    static_checks: {
      stable_metadata: {
        status: staticBlockers.stable_metadata.length === 0 ? "ok" : "blocked",
        blockers: staticBlockers.stable_metadata
      },
      deprecated_provider_tokens: {
        status: staticBlockers.deprecated_provider_tokens.length === 0 ? "ok" : "blocked",
        blockers: staticBlockers.deprecated_provider_tokens
      },
      packaged_install_smoke: {
        status: staticBlockers.packaged_install_smoke.length === 0 ? "ok" : "blocked",
        blockers: staticBlockers.packaged_install_smoke
      }
    },
    blockers,
    ready_for_release: blockers.length === 0
  };
}
