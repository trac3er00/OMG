import { describe, test, expect } from "bun:test";
import { SecretGuard } from "./secret-guard.js";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { rmSync } from "node:fs";

describe("SecretGuard", () => {
  function mkDir(): string {
    return join(tmpdir(), `omg-sg-test-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  }

  test(".env access blocked", async () => {
    const dir = mkDir();
    try {
      const guard = new SecretGuard({ projectDir: dir });
      const result = await guard.evaluateFileAccess("Read", ".env");
      expect(result.allowed).toBe(false);
      expect(result.auditLogged).toBe(true);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test(".env.local access blocked", async () => {
    const dir = mkDir();
    try {
      const guard = new SecretGuard({ projectDir: dir });
      const result = await guard.evaluateFileAccess("Read", ".env.local");
      expect(result.allowed).toBe(false);
      expect(result.auditLogged).toBe(true);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test(".env.production access blocked", async () => {
    const dir = mkDir();
    try {
      const guard = new SecretGuard({ projectDir: dir });
      const result = await guard.evaluateFileAccess("Read", ".env.production");
      expect(result.allowed).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("normal TS file allowed", async () => {
    const dir = mkDir();
    try {
      const guard = new SecretGuard({ projectDir: dir });
      const result = await guard.evaluateFileAccess("Read", "src/index.ts");
      expect(result.allowed).toBe(true);
      expect(result.auditLogged).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("allowlisted file bypasses block", async () => {
    const dir = mkDir();
    try {
      const guard = new SecretGuard({ projectDir: dir, allowlist: [".env"] });
      const result = await guard.evaluateFileAccess("Read", ".env");
      expect(result.allowed).toBe(true);
      expect(result.allowlisted).toBe(true);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("SSH key access blocked", async () => {
    const dir = mkDir();
    try {
      const guard = new SecretGuard({ projectDir: dir });
      const result = await guard.evaluateFileAccess("Read", "id_rsa");
      expect(result.allowed).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("PEM file access blocked", async () => {
    const dir = mkDir();
    try {
      const guard = new SecretGuard({ projectDir: dir });
      const result = await guard.evaluateFileAccess("Read", "server.pem");
      expect(result.allowed).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("credentials.json access blocked", async () => {
    const dir = mkDir();
    try {
      const guard = new SecretGuard({ projectDir: dir });
      const result = await guard.evaluateFileAccess("Read", "credentials.json");
      expect(result.allowed).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test(".aws/ directory access blocked", async () => {
    const dir = mkDir();
    try {
      const guard = new SecretGuard({ projectDir: dir });
      const result = await guard.evaluateFileAccess("Read", ".aws/credentials");
      expect(result.allowed).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test(".netrc access blocked", async () => {
    const dir = mkDir();
    try {
      const guard = new SecretGuard({ projectDir: dir });
      const result = await guard.evaluateFileAccess("Read", ".netrc");
      expect(result.allowed).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("secrets.yml access blocked", async () => {
    const dir = mkDir();
    try {
      const guard = new SecretGuard({ projectDir: dir });
      const result = await guard.evaluateFileAccess("Read", "secrets.yml");
      expect(result.allowed).toBe(false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  test("result contains correct tool and filePath", async () => {
    const dir = mkDir();
    try {
      const guard = new SecretGuard({ projectDir: dir });
      const result = await guard.evaluateFileAccess("Write", "config.ts");
      expect(result.tool).toBe("Write");
      expect(result.filePath).toBe("config.ts");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});
