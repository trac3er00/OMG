import { afterEach, describe, expect, test } from "bun:test";
import { generateKeyPairSync } from "node:crypto";
import { HttpControlPlaneServer } from "./http-server.js";
import { generateToken } from "../security/jwt-auth.js";

const activeServers: HttpControlPlaneServer[] = [];

async function withServer(
  port: number,
  fn: (context: { baseUrl: string; token: string }) => Promise<void>,
): Promise<void> {
  const { privateKey, publicKey } = generateKeyPairSync("ed25519");
  const token = generateToken({ role: "agent", sub: "tester" }, privateKey);
  const server = HttpControlPlaneServer.create({
    host: "127.0.0.1",
    port,
    jwtPublicKey: publicKey.export({ type: "spki", format: "pem" }).toString(),
    handler: async ({ payload, body }) => ({ ok: true, role: payload.role, body }),
  });
  activeServers.push(server);
  await server.start();
  try {
    await fn({ baseUrl: `http://127.0.0.1:${port}`, token });
  } finally {
    await server.stop();
    activeServers.splice(activeServers.indexOf(server), 1);
  }
}

afterEach(async () => {
  while (activeServers.length > 0) {
    await activeServers.pop()?.stop();
  }
});

describe("HttpControlPlaneServer", () => {
  test("health endpoint omits service fingerprint and applies security headers", async () => {
    const { privateKey, publicKey } = generateKeyPairSync("ed25519");
    const server = HttpControlPlaneServer.create({
      host: "127.0.0.1",
      port: 9988,
      jwtPublicKey: publicKey.export({ type: "spki", format: "pem" }).toString(),
    });
    activeServers.push(server);
    await server.start();

    const response = await fetch("http://127.0.0.1:9988/health");
    const payload = (await response.json()) as Record<string, unknown>;

    expect(response.status).toBe(200);
    expect(payload).toEqual({ ok: true });
    expect(response.headers.get("x-frame-options")).toBe("DENY");
    expect(response.headers.get("x-content-type-options")).toBe("nosniff");
    expect(response.headers.get("content-security-policy")).toContain("default-src 'none'");

    await server.stop();
    activeServers.splice(activeServers.indexOf(server), 1);
    void privateKey;
  });

  test("malformed JSON request returns 400", async () => {
    await withServer(9989, async ({ baseUrl, token }) => {
      const response = await fetch(`${baseUrl}/execute`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${token}`,
          "content-type": "application/json",
        },
        body: '{"broken":',
      });

      const payload = (await response.json()) as Record<string, unknown>;
      expect(response.status).toBe(400);
      expect(payload).toEqual({ error: "Malformed JSON body" });
    });
  });
});
