import { cwd } from "node:process";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import type { ToolRegistration } from "../interfaces/mcp.js";
import { isMiddlewareResult, MiddlewareStack } from "./middleware.js";
import { newCapabilityTools } from "./tools/new-capabilities.js";
import { wrapTool } from "./tool-wrapper.js";

const SERVER_NAME = "OMG Control MCP";
const SERVER_VERSION = "2.3.0";

/**
 * Canonical MCP protocol version expected by OMG clients.
 */
export const OMG_PROTOCOL_VERSION = "2025-03-26";

/**
 * Response shape for the built-in health-check tool.
 */
export interface PingResponse {
  readonly status: "ok";
  readonly timestamp: number;
}

/**
 * Runtime options for MCP server construction.
 */
export interface CreateServerOptions {
  /**
   * Project directory used for middleware context payloads.
   * Defaults to CLAUDE_PROJECT_DIR or process.cwd().
   */
  readonly projectDir?: string;
  /**
   * Optional session id to thread through middleware context.
   */
  readonly sessionId?: string;
  /**
   * Existing middleware stack instance (DI-friendly).
   */
  readonly middlewareStack?: MiddlewareStack;
  /**
   * Optional tool registrations to add on top of built-ins.
   */
  readonly tools?: readonly ToolRegistration[];
}

/**
 * Factory output for the OMG MCP server runtime.
 */
export interface OmgMcpServer {
  readonly server: McpServer;
  readonly middlewareStack: MiddlewareStack;
  readonly toolNames: readonly string[];
}

function toCallToolResult(result: unknown): {
  content: Array<{ type: "text"; text: string }>;
  structuredContent?: Record<string, unknown>;
  isError?: boolean;
} {
  if (isMiddlewareResult(result) && result.decision === "deny") {
    const denialPayload: Record<string, unknown> = {
      status: "denied",
      reason: result.reason ?? "Denied by middleware",
      ...(isRecord(result.response) ? { response: result.response } : {}),
    };

    return {
      content: [{ type: "text", text: JSON.stringify(denialPayload) }],
      structuredContent: denialPayload,
      isError: true,
    };
  }

  if (isRecord(result)) {
    return {
      content: [{ type: "text", text: JSON.stringify(result) }],
      structuredContent: result,
    };
  }

  return {
    content: [{ type: "text", text: String(result) }],
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function createPingToolRegistration(): ToolRegistration {
  return {
    name: "omg_ping",
    description: "Health-check endpoint for OMG MCP connectivity",
    inputSchema: {},
    handler: async (): Promise<PingResponse> => ({
      status: "ok",
      timestamp: Date.now(),
    }),
  };
}

/**
 * Create an OMG MCP server instance with middleware-wrapped tools.
 */
export function createServer(options: CreateServerOptions = {}): OmgMcpServer {
  const server = new McpServer(
    {
      name: SERVER_NAME,
      version: SERVER_VERSION,
    },
    {
      capabilities: {
        tools: {
          listChanged: true,
        },
      },
    },
  );

  const projectDir =
    options.projectDir ?? process.env.CLAUDE_PROJECT_DIR ?? cwd();
  const middlewareStack = options.middlewareStack ?? new MiddlewareStack();
  const builtInTools = [createPingToolRegistration(), ...newCapabilityTools];
  const allTools = [...builtInTools, ...(options.tools ?? [])];

  for (const tool of allTools) {
    const wrapped = wrapTool<Record<string, unknown>>(
      tool.name,
      tool.handler,
      middlewareStack,
      projectDir,
      options.sessionId,
    );

    server.registerTool(
      tool.name,
      {
        description: tool.description,
        inputSchema: z.looseObject({}),
      },
      async (args) => {
        const result = await wrapped(args);
        return toCallToolResult(result);
      },
    );
  }

  return {
    server,
    middlewareStack,
    toolNames: allTools.map((tool) => tool.name),
  };
}

/**
 * Start the OMG MCP server over stdio transport.
 */
export async function startServer(
  options: CreateServerOptions = {},
): Promise<OmgMcpServer> {
  const runtime = createServer(options);
  const transport = new StdioServerTransport();
  await runtime.server.connect(transport);
  return runtime;
}

if (import.meta.main) {
  startServer().catch((error: unknown) => {
    console.error("Fatal error in OMG MCP server:", error);
    process.exit(1);
  });
}
