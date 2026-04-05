import { afterEach, describe, expect, test } from "bun:test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { MiddlewareStack } from "./middleware.js";
import { createServer } from "./server.js";

interface ConnectedRuntime {
  readonly client: Client;
  readonly close: () => Promise<void>;
}

const disposers: Array<() => Promise<void>> = [];

afterEach(async () => {
  while (disposers.length > 0) {
    const dispose = disposers.pop();
    if (dispose) {
      await dispose();
    }
  }
});

async function connectServer(stack?: MiddlewareStack): Promise<ConnectedRuntime> {
  const runtime = createServer({
    ...(stack ? { middlewareStack: stack } : {}),
    projectDir: "/tmp/omg-mcp",
  });
  const client = new Client({ name: "test-client", version: "0.1.0" });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();

  await runtime.server.connect(serverTransport);
  await client.connect(clientTransport);

  const close = async (): Promise<void> => {
    await Promise.all([client.close(), runtime.server.close()]);
  };

  disposers.push(close);
  return { client, close };
}

describe("MCP server", () => {
  test("initializes with OMG server info", async () => {
    const { client } = await connectServer();
    const serverInfo = client.getServerVersion();

    expect(serverInfo?.name).toBe("OMG Control MCP");
    expect(serverInfo?.version).toBe("2.3.0");
  });

  test("registers omg_ping and returns ok payload", async () => {
    const { client } = await connectServer();

    const tools = await client.listTools();
    expect(tools.tools.some((tool) => tool.name === "omg_ping")).toBe(true);

    const response = await client.callTool({
      name: "omg_ping",
      arguments: {},
    });

    expect(response.isError).toBeUndefined();
    expect(response.structuredContent).toBeDefined();
    expect(isRecord(response.structuredContent)).toBe(true);
    if (isRecord(response.structuredContent)) {
      expect(response.structuredContent.status).toBe("ok");
      expect(typeof response.structuredContent.timestamp).toBe("number");
    }
  });

  test("middleware pre and post hooks fire around ping execution", async () => {
    const events: string[] = [];
    const stack = new MiddlewareStack();

    stack.before(async (ctx) => {
      events.push(`before:${ctx.toolName}`);
    });

    stack.after(async (ctx, result) => {
      const payload = result as { status?: string };
      events.push(`after:${ctx.toolName}:${payload.status ?? "unknown"}`);
      return result;
    });

    const { client } = await connectServer(stack);
    await client.callTool({ name: "omg_ping", arguments: {} });

    expect(events).toEqual(["before:omg_ping", "after:omg_ping:ok"]);
  });
});

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
