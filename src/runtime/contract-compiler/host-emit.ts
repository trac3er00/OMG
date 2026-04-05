import type { ContractHost, ContractSchema } from "./schema.js";

export interface HostArtifact {
  readonly host: ContractHost;
  readonly targetPath: string;
  readonly payload: Readonly<Record<string, unknown>>;
}

function emitClaudeArtifact(): HostArtifact {
  return {
    host: "claude",
    targetPath: ".claude-plugin/mcp.json",
    payload: {
      mcpServers: {
        "omg-control": {
          command: "bun",
          args: ["run", "src/mcp/server.ts"],
        },
      },
    },
  };
}

function emitCodexArtifact(schema: ContractSchema): HostArtifact {
  const skillNames = Object.keys(schema.tools).sort();
  const skillFiles: Record<string, string> = {};
  for (const skillName of skillNames) {
    skillFiles[`${skillName}/SKILL.md`] = `# ${skillName}\n\nGenerated from OMG contract compiler.\n`;
    skillFiles[`${skillName}/openai.yaml`] = `name: omg-${skillName}\ndescription: ${schema.tools[skillName]?.description ?? ""}\n`;
  }

  return {
    host: "codex",
    targetPath: ".agents/skills/omg/",
    payload: {
      files: {
        "AGENTS.fragment.md": "# OMG Codex Governance\n",
        "codex-rules.md": "# OMG Codex Rules\n",
        ...skillFiles,
      },
    },
  };
}

function emitGeminiArtifact(): HostArtifact {
  return {
    host: "gemini",
    targetPath: "settings.json",
    payload: {
      mcpServers: {
        "omg-control": {
          command: "bun",
          args: ["run", "src/mcp/server.ts"],
          enabled: true,
        },
      },
    },
  };
}

function emitKimiArtifact(): HostArtifact {
  return {
    host: "kimi",
    targetPath: "mcp.json",
    payload: {
      mcpServers: {
        "omg-control": {
          command: "bun",
          args: ["run", "src/mcp/server.ts"],
        },
      },
    },
  };
}

export function emitForHost(schema: ContractSchema, host: ContractHost): HostArtifact {
  switch (host) {
    case "claude":
      return emitClaudeArtifact();
    case "codex":
      return emitCodexArtifact(schema);
    case "gemini":
      return emitGeminiArtifact();
    case "kimi":
      return emitKimiArtifact();
    default: {
      const unreachableHost: never = host;
      throw new Error(`Unsupported host: ${String(unreachableHost)}`);
    }
  }
}
