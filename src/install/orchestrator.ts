import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import type { CanonicalInstallHost, InstallPlan } from "./planner.js";
import { InstallPlanner } from "./planner.js";

interface OrchestratorDeps {
  readonly readFile: (path: string, encoding: "utf-8") => Promise<string>;
  readonly writeFile: (path: string, content: string, encoding: "utf-8") => Promise<void>;
  readonly mkdir: (path: string, options: { readonly recursive: boolean }) => Promise<string | undefined | void>;
}

export interface ApplyResult {
  readonly preview: string[];
  readonly files: string[];
}

function ensureObject(value: unknown): Record<string, unknown> {
  if (typeof value === "object" && value !== null) {
    return value as Record<string, unknown>;
  }
  return {};
}

function parseJsonOrEmpty(raw: string): Record<string, unknown> {
  try {
    return ensureObject(JSON.parse(raw));
  } catch {
    return {};
  }
}

function upsertCodexControlBlock(existing: string): string {
  const block = [
    "[mcp_servers.omg-control]",
    'command = "bunx"',
    'args = ["omg-control"]',
    "",
  ].join("\n");

  const lines = existing.split(/\r?\n/);
  const startIndex = lines.findIndex((line) => line.trim() === "[mcp_servers.omg-control]");
  if (startIndex === -1) {
    const prefix = existing.length > 0 && !existing.endsWith("\n") ? `${existing}\n` : existing;
    return `${prefix}${block}`;
  }

  let endIndex = lines.length;
  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const trimmed = lines[index]?.trim() ?? "";
    if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
      endIndex = index;
      break;
    }
  }

  const updated = [...lines.slice(0, startIndex), ...block.split("\n"), ...lines.slice(endIndex)];
  return updated.join("\n");
}

export class SetupOrchestrator {
  private constructor(
    private readonly planner: InstallPlanner,
    private readonly deps: OrchestratorDeps,
  ) {}

  static create(planner: InstallPlanner, overrides: Partial<OrchestratorDeps> = {}): SetupOrchestrator {
    return new SetupOrchestrator(planner, {
      readFile: overrides.readFile ?? ((path, encoding) => readFile(path, { encoding })),
      writeFile: overrides.writeFile ?? ((path, content, encoding) => writeFile(path, content, { encoding })),
      mkdir: overrides.mkdir ?? (async (path, options) => {
        await mkdir(path, options);
      }),
    });
  }

  async plan(): Promise<InstallPlan> {
    const hosts = await this.planner.detectHosts();
    return this.planner.planInstall(hosts);
  }

  async apply(): Promise<ApplyResult> {
    const plan = await this.plan();
    const files: string[] = [];

    for (const step of plan.steps) {
      const content = await this.renderHostConfig(step.host, step.targetPath);
      await this.deps.mkdir(dirname(step.targetPath), { recursive: true });
      await this.deps.writeFile(step.targetPath, content, "utf-8");
      files.push(step.targetPath);
    }

    return {
      preview: plan.preview,
      files,
    };
  }

  private async renderHostConfig(host: CanonicalInstallHost, targetPath: string): Promise<string> {
    const existing = await this.safeRead(targetPath);

    if (host === "codex") {
      return upsertCodexControlBlock(existing);
    }

    const parsed = parseJsonOrEmpty(existing);
    const servers = ensureObject(parsed.mcpServers);
    servers["omg-control"] = {
      command: "bunx",
      args: ["omg-control"],
    };
    parsed.mcpServers = servers;

    return `${JSON.stringify(parsed, null, 2)}\n`;
  }

  private async safeRead(path: string): Promise<string> {
    try {
      return await this.deps.readFile(path, "utf-8");
    } catch {
      return "";
    }
  }
}
