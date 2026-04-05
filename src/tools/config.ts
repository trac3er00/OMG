import { readdir, stat, access, constants } from "node:fs/promises";
import { join, extname } from "node:path";

export interface ConfigFile {
  readonly tool: string;
  readonly paths: readonly string[];
  readonly format: string;
  readonly sizeBytes: number;
  readonly readable: boolean;
}

export interface DiscoveryResult {
  readonly configs: readonly ConfigFile[];
  readonly scanDir: string;
  readonly timestamp: string;
  readonly error?: string;
}

export interface ConfigDeps {
  readonly stat: typeof stat;
  readonly readdir: typeof readdir;
  readonly access: typeof access;
}

const defaultDeps: ConfigDeps = { stat, readdir, access };

const TOOL_PATTERNS: Record<string, readonly string[]> = {
  claude_code: [".claude/", ".claude/CLAUDE.md", "CLAUDE.md"],
  cursor: [".cursorrules", ".cursor/rules/", ".cursor/"],
  windsurf: [".windsurf/", ".windsurfrules"],
  gemini: ["system.md", ".gemini/"],
  codex: ["AGENTS.md"],
  cline: [".clinerules"],
  github_copilot: [".github/copilot-instructions.md"],
  vscode: [".vscode/settings.json", ".vscode/"],
};

function getFormat(filePath: string, isDir: boolean): string {
  if (isDir) return "directory";
  const ext = extname(filePath).toLowerCase();
  switch (ext) {
    case ".md": return "markdown";
    case ".json": return "json";
    case ".yaml":
    case ".yml": return "yaml";
    case ".txt": return "text";
    default: return "unknown";
  }
}

export class ConfigDiscovery {
  private readonly deps: ConfigDeps;

  private constructor(deps: ConfigDeps) {
    this.deps = deps;
  }

  static create(deps?: Partial<ConfigDeps>): ConfigDiscovery {
    return new ConfigDiscovery({ ...defaultDeps, ...deps });
  }

  async discoverConfigs(dir: string): Promise<DiscoveryResult> {
    try {
      await this.deps.stat(dir);
    } catch {
      return {
        configs: [],
        scanDir: dir,
        timestamp: new Date().toISOString(),
        error: `Directory does not exist: ${dir}`,
      };
    }

    const configs: ConfigFile[] = [];

    for (const [tool, patterns] of Object.entries(TOOL_PATTERNS)) {
      const foundPaths: string[] = [];

      for (const pattern of patterns) {
        const isDir = pattern.endsWith("/");
        const cleanPattern = isDir ? pattern.slice(0, -1) : pattern;
        const fullPath = join(dir, cleanPattern);

        try {
          const s = await this.deps.stat(fullPath);
          if (isDir && s.isDirectory()) {
            foundPaths.push(cleanPattern);
          } else if (!isDir && s.isFile()) {
            foundPaths.push(cleanPattern);
          }
        } catch {
          continue;
        }
      }

      if (foundPaths.length > 0) {
        const firstPath = join(dir, foundPaths[0] ?? "");
        let sizeBytes = 0;
        let readable = false;
        let isDir = false;

        try {
          const s = await this.deps.stat(firstPath);
          sizeBytes = s.isFile() ? s.size : 0;
          isDir = s.isDirectory();
        } catch {
          sizeBytes = 0;
        }

        try {
          await this.deps.access(firstPath, constants.R_OK);
          readable = true;
        } catch {
          readable = false;
        }

        configs.push({
          tool,
          paths: foundPaths,
          format: getFormat(foundPaths[0] ?? "", isDir),
          sizeBytes,
          readable,
        });
      }
    }

    return {
      configs,
      scanDir: dir,
      timestamp: new Date().toISOString(),
    };
  }

  mergeConfigs(configs: readonly ConfigFile[]): Record<string, ConfigFile> {
    const merged: Record<string, ConfigFile> = {};
    for (const config of configs) {
      merged[config.tool] = config;
    }
    return merged;
  }
}
