import { describe, expect, test } from "bun:test";
import type { LspDeps, LspServerInfo } from "./lsp.js";
import {
  aggregateWorkspaceDiagnostics,
  getLSPServerStatus,
  LspClient,
} from "./lsp.js";

const stubServers: LspServerInfo[] = [
  {
    name: "ts-server",
    command: "typescript-language-server",
    languages: ["typescript"],
  },
  { name: "pyright", command: "pyright-langserver", languages: ["python"] },
];

function makeDeps(whichSucceeds = true): LspDeps {
  return {
    exec: (async (_cmd: string, _args?: readonly string[]) => {
      if (!whichSucceeds) throw new Error("not found");
      return { stdout: "/usr/bin/ts-server\n", stderr: "" };
    }) as LspDeps["exec"],
    discoverPaths: async () => stubServers,
  };
}

describe("LspClient", () => {
  test("create returns LspClient instance", () => {
    const client = LspClient.create(makeDeps());
    expect(client).toBeInstanceOf(LspClient);
  });

  test("starts disconnected", () => {
    const client = LspClient.create(makeDeps());
    expect(client.isConnected()).toBe(false);
    expect(client.getServerPath()).toBe("");
  });

  test("connect succeeds when server binary exists", async () => {
    const client = LspClient.create(makeDeps(true));
    const ok = await client.connect("typescript-language-server");
    expect(ok).toBe(true);
    expect(client.isConnected()).toBe(true);
    expect(client.getServerPath()).toBe("typescript-language-server");
  });

  test("connect fails when server binary missing", async () => {
    const client = LspClient.create(makeDeps(false));
    const ok = await client.connect("nonexistent-server");
    expect(ok).toBe(false);
    expect(client.isConnected()).toBe(false);
  });

  test("connect with empty path returns false", async () => {
    const client = LspClient.create(makeDeps());
    const ok = await client.connect("");
    expect(ok).toBe(false);
  });

  test("disconnect clears state", async () => {
    const client = LspClient.create(makeDeps());
    await client.connect("typescript-language-server");
    client.disconnect();
    expect(client.isConnected()).toBe(false);
    expect(client.getServerPath()).toBe("");
  });

  test("getDefinition returns null when disconnected", async () => {
    const client = LspClient.create(makeDeps());
    const loc = await client.getDefinition("src/foo.ts", 10, 5);
    expect(loc).toBeNull();
  });

  test("getDefinition returns location when connected", async () => {
    const client = LspClient.create(makeDeps());
    await client.connect("typescript-language-server");
    const loc = await client.getDefinition("src/foo.ts", 10, 5);
    expect(loc).not.toBeNull();
    expect(loc?.file).toBe("src/foo.ts");
    expect(loc?.line).toBe(10);
    expect(loc?.column).toBe(5);
  });

  test("getReferences returns empty when disconnected", async () => {
    const client = LspClient.create(makeDeps());
    const refs = await client.getReferences("src/foo.ts", 10, 5);
    expect(refs).toEqual([]);
  });

  test("getReferences returns locations when connected", async () => {
    const client = LspClient.create(makeDeps());
    await client.connect("typescript-language-server");
    const refs = await client.getReferences("src/foo.ts", 10, 5);
    expect(refs.length).toBeGreaterThan(0);
    expect(refs[0]?.file).toBe("src/foo.ts");
  });

  test("getDiagnostics returns empty when disconnected", async () => {
    const client = LspClient.create(makeDeps());
    const diags = await client.getDiagnostics("src/foo.ts");
    expect(diags).toEqual([]);
  });

  test("discoverServers returns known servers", async () => {
    const client = LspClient.create(makeDeps());
    const servers = await client.discoverServers();
    expect(servers).toHaveLength(2);
    expect(servers[0]?.name).toBe("ts-server");
    expect(servers[1]?.languages).toContain("python");
  });

  test("getDefinition with invalid args returns null", async () => {
    const client = LspClient.create(makeDeps());
    await client.connect("typescript-language-server");
    expect(await client.getDefinition("", 10, 5)).toBeNull();
    expect(await client.getDefinition("file.ts", -1, 5)).toBeNull();
    expect(await client.getDefinition("file.ts", 10, -1)).toBeNull();
  });

  test("getReferences with invalid args returns empty", async () => {
    const client = LspClient.create(makeDeps());
    await client.connect("typescript-language-server");
    expect(await client.getReferences("", 10, 5)).toEqual([]);
  });
});

describe("workspace LSP helpers", () => {
  test("getLSPServerStatus returns array", () => {
    const servers = getLSPServerStatus();
    expect(Array.isArray(servers)).toBe(true);
    expect(servers.length).toBeGreaterThan(0);
  });

  test("aggregateWorkspaceDiagnostics handles empty list", async () => {
    const result = await aggregateWorkspaceDiagnostics([]);
    expect(result.totalFiles).toBe(0);
    expect(result.filesWithErrors).toBe(0);
    expect(result.errorCount).toBe(0);
    expect(result.warningCount).toBe(0);
    expect(result.byFile).toEqual({});
  });
});
