import { afterEach, describe, expect, test } from "bun:test";
import { generateKeyPairSync } from "node:crypto";
import {
  clearRevocations,
  generateToken,
  hasRequiredRole,
  refreshToken,
  revokeToken,
  validateToken,
} from "./jwt-auth.js";

describe("JWT auth (Ed25519)", () => {
  afterEach(() => {
    clearRevocations();
  });

  test("generate and validate token", () => {
    const { privateKey, publicKey } = generateKeyPairSync("ed25519");
    const token = generateToken({ sub: "agent-1", role: "agent" }, privateKey);

    const validation = validateToken(token, publicKey);
    expect(validation.valid).toBe(true);
    expect(validation.payload?.sub).toBe("agent-1");
    expect(validation.payload?.role).toBe("agent");
  });

  test("tampered token is invalid", () => {
    const { privateKey, publicKey } = generateKeyPairSync("ed25519");
    const token = generateToken({ sub: "admin-1", role: "admin" }, privateKey);
    const tokenParts = token.split(".");
    const header = tokenParts[0] ?? "";
    const signature = tokenParts[2] ?? "";
    const tamperedPayload = Buffer.from(
      JSON.stringify({ sub: "hijacked", role: "admin" }),
      "utf8",
    ).toString("base64url");
    const tamperedToken = `${header}.${tamperedPayload}.${signature}`;

    const validation = validateToken(tamperedToken, publicKey);
    expect(validation.valid).toBe(false);
  });

  test("role hierarchy enforced", () => {
    expect(hasRequiredRole({ role: "admin" }, "readonly")).toBe(true);
    expect(hasRequiredRole({ role: "agent" }, "readonly")).toBe(true);
    expect(hasRequiredRole({ role: "readonly" }, "agent")).toBe(false);
  });

  test("revoked token cannot be used", () => {
    const { privateKey, publicKey } = generateKeyPairSync("ed25519");
    const token = generateToken({ sub: "agent-2", role: "agent" }, privateKey);
    const revoked = revokeToken(token, publicKey);
    expect(revoked).toBe(true);

    const validation = validateToken(token, publicKey);
    expect(validation.valid).toBe(false);
    expect(validation.error).toBe("Token revoked");
  });

  test("rejects revocation of tampered token payload", () => {
    const { privateKey, publicKey } = generateKeyPairSync("ed25519");
    const token = generateToken({ sub: "agent-4", role: "agent" }, privateKey);
    const tokenParts = token.split(".");
    const header = tokenParts[0] ?? "";
    const signature = tokenParts[2] ?? "";
    const tamperedPayload = Buffer.from(
      JSON.stringify({
        sub: "agent-4",
        role: "agent",
        jti: "fake-jti",
        exp: 9999999999,
      }),
      "utf8",
    ).toString("base64url");
    const tamperedToken = `${header}.${tamperedPayload}.${signature}`;

    expect(revokeToken(tamperedToken, publicKey)).toBe(false);
    // Validate the tampered token (not original) to verify cache isn't poisoned by forged jti
    expect(validateToken(tamperedToken, publicKey).valid).toBe(false);
  });

  test("refresh rotates token and revokes old one", () => {
    const { privateKey, publicKey } = generateKeyPairSync("ed25519");
    const token = generateToken({ sub: "agent-3", role: "agent" }, privateKey);

    const refreshed = refreshToken(token, privateKey, publicKey);
    expect(refreshed.ok).toBe(true);
    expect(typeof refreshed.token).toBe("string");

    const oldValidation = validateToken(token, publicKey);
    expect(oldValidation.valid).toBe(false);

    const newValidation = validateToken(refreshed.token ?? "", publicKey);
    expect(newValidation.valid).toBe(true);
    expect(newValidation.payload?.tokenType).toBe("refresh");
  });
});
