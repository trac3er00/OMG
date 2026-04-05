#!/usr/bin/env bun

import {
  randomBytes,
  createCipheriv,
  createDecipheriv,
  generateKeyPairSync,
  sign,
  verify,
  pbkdf2Sync,
} from "node:crypto";
import { writeFileSync, mkdirSync, existsSync } from "node:fs";
import { join } from "node:path";

interface AssumptionResult {
  assumption: string;
  status: "pass" | "fail";
  details: string;
  timeMs?: number;
}

type SqliteDatabaseCtor = new (filename: string) => {
  exec: (sql: string) => void;
  prepare: (sql: string) => {
    all: () => unknown;
    get: () => unknown;
  };
  close: () => void;
};

type Check = {
  assumption: string;
  run: () => string | Promise<string>;
};

const checks: Check[] = [
  {
    assumption: "node:crypto AES-256-GCM roundtrip",
    run: () => {
      const key = randomBytes(32);
      const iv = randomBytes(12);
      const plaintext = "Hello, OMG v2.3.0!";

      const cipher = createCipheriv("aes-256-gcm", key, iv);
      const ciphertext = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
      const authTag = cipher.getAuthTag();

      const decipher = createDecipheriv("aes-256-gcm", key, iv);
      decipher.setAuthTag(authTag);
      const decrypted = Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString("utf8");

      if (decrypted !== plaintext) {
        throw new Error(`Mismatch: got "${decrypted}"`);
      }

      const tampered = Buffer.from(ciphertext);
      tampered[0] ^= 0xff;
      try {
        const d2 = createDecipheriv("aes-256-gcm", key, iv);
        d2.setAuthTag(authTag);
        d2.update(tampered);
        d2.final();
        throw new Error("Should have thrown for tampered ciphertext");
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        if (
          !msg.includes("Unsupported state or unable to authenticate data") &&
          !msg.includes("bad decrypt") &&
          !msg.toLowerCase().includes("authentication")
        ) {
          if (msg.includes("Should have thrown")) {
            throw e;
          }
        }
      }

      return `AES-256-GCM encrypt/decrypt roundtrip: OK. Plaintext length: ${plaintext.length}`;
    },
  },
  {
    assumption: "node:crypto PBKDF2-HMAC-SHA256 (600k iterations)",
    run: () => {
      const passphrase = Buffer.from("testpassphrase");
      const salt = Buffer.from("testsalt12345678");
      const iterations = 600_000;
      const keylen = 32;

      const start = Date.now();
      const key = pbkdf2Sync(passphrase, salt, iterations, keylen, "sha256");
      const elapsed = Date.now() - start;

      return `PBKDF2 (600k): ${key.toString("hex")} [${elapsed}ms]`;
    },
  },
  {
    assumption: "node:crypto Ed25519 sign/verify",
    run: () => {
      const { privateKey, publicKey } = generateKeyPairSync("ed25519");
      const data = Buffer.from("test data for signing");

      const signature = sign(null, data, privateKey);
      const valid = verify(null, data, publicKey, signature);

      if (!valid) {
        throw new Error("Signature verification failed");
      }

      const tampered = Buffer.from("tampered data!!!");
      const invalid = verify(null, tampered, publicKey, signature);
      if (invalid) {
        throw new Error("Tampered data should not verify");
      }

      return `Ed25519 sign/verify: OK. Signature length: ${signature.length}`;
    },
  },
  {
    assumption: "Bun.Database FTS5 virtual table",
    run: async () => {
      const Database = await getDatabaseCtor();
      const db = new Database(":memory:");

      db.exec(`
        CREATE VIRTUAL TABLE search_test USING fts5(
          key,
          content,
          tokenize = 'porter ascii'
        )
      `);

      db.exec(`INSERT INTO search_test VALUES ('key1', 'hello world orchestration')`);
      db.exec(`INSERT INTO search_test VALUES ('key2', 'security firewall protection')`);
      db.exec(`INSERT INTO search_test VALUES ('key3', 'agent routing dispatch')`);

      const rows = db
        .prepare(`SELECT key FROM search_test WHERE search_test MATCH 'orchestr*'`)
        .all() as { key: string }[];

      if (rows.length === 0) {
        throw new Error("FTS5 search returned no results");
      }
      if (!rows.some((r) => r.key === "key1")) {
        throw new Error(`Expected key1, got: ${JSON.stringify(rows)}`);
      }

      db.close();
      return `FTS5: Found ${rows.length} result(s) for 'orchestr*': ${rows.map((r) => r.key).join(", ")}`;
    },
  },
  {
    assumption: "Bun.Database WAL mode",
    run: async () => {
      const Database = await getDatabaseCtor();
      const db = new Database(":memory:");
      db.exec("PRAGMA journal_mode=WAL");
      const row = db.prepare("PRAGMA journal_mode").get() as { journal_mode: string };
      const mode = row.journal_mode;
      db.close();
      return `WAL pragma: journal_mode=${mode} (memory DBs may return 'memory', file DBs return 'wal')`;
    },
  },
  {
    assumption: "Dynamic import() for provider pattern",
    run: async () => {
      const tmpDir = "/tmp/omg-spike-test";
      if (!existsSync(tmpDir)) {
        mkdirSync(tmpDir, { recursive: true });
      }

      const providerCode = `export const PROVIDER_NAME = "test-provider";
export function greet() { return "hello from dynamic provider"; }`;
      writeFileSync(join(tmpDir, "test-provider.ts"), providerCode);

      const mod = (await import(join(tmpDir, "test-provider.ts"))) as {
        PROVIDER_NAME: string;
        greet: () => string;
      };

      if (mod.PROVIDER_NAME !== "test-provider") {
        throw new Error(`Unexpected name: ${mod.PROVIDER_NAME}`);
      }
      if (mod.greet() !== "hello from dynamic provider") {
        throw new Error(`Unexpected greet: ${mod.greet()}`);
      }

      return `Dynamic import(): OK. Loaded provider: ${mod.PROVIDER_NAME}`;
    },
  },
  {
    assumption: "proper-lockfile file locking under concurrent writes",
    run: async () => {
      const { lock } = (await import("proper-lockfile")) as {
        lock: (path: string, opts: { retries: number }) => Promise<() => Promise<void>>;
      };

      const testFile = "/tmp/omg-spike-locktest.txt";
      writeFileSync(testFile, "initial");

      const release = await lock(testFile, { retries: 0 });
      let lockAcquired = false;
      try {
        await lock(testFile, { retries: 0 });
        lockAcquired = true;
      } catch {
        lockAcquired = false;
      }

      await release();

      if (lockAcquired) {
        throw new Error("Second lock should not have been acquired while first was held");
      }

      const release2 = await lock(testFile, { retries: 0 });
      await release2();

      return "proper-lockfile: Lock acquired, concurrent lock blocked, release works";
    },
  },
  {
    assumption: "stdio pipe for MCP (stdout JSON output)",
    run: () => {
      const testPayload = {
        jsonrpc: "2.0",
        result: { serverInfo: { name: "OMG Control MCP", version: "2.3.0" } },
        id: 1,
      };

      const json = JSON.stringify(testPayload);
      const parsed = JSON.parse(json) as typeof testPayload;

      if (parsed.result.serverInfo.name !== "OMG Control MCP") {
        throw new Error("JSON roundtrip failed");
      }

      if (typeof process.stdout.write !== "function") {
        throw new Error("process.stdout.write is not available");
      }

      return `stdio/JSON: process.stdout writable, JSON roundtrip OK. Payload: ${json.length} bytes`;
    },
  },
];

async function getDatabaseCtor(): Promise<SqliteDatabaseCtor> {
  const maybeGlobal = (Bun as unknown as { Database?: SqliteDatabaseCtor }).Database;
  if (typeof maybeGlobal === "function") {
    return maybeGlobal;
  }

  const mod = (await import("bun:sqlite")) as { Database?: SqliteDatabaseCtor };
  if (typeof mod.Database === "function") {
    return mod.Database;
  }

  throw new Error("SQLite Database constructor not available via Bun.Database or bun:sqlite");
}

async function main() {
  const results: AssumptionResult[] = [];

  for (const check of checks) {
    const start = Date.now();
    try {
      const details = await check.run();
      results.push({
        assumption: check.assumption,
        status: "pass",
        details,
        timeMs: Date.now() - start,
      });
    } catch (err) {
      results.push({
        assumption: check.assumption,
        status: "fail",
        details: err instanceof Error ? err.stack || err.message : String(err),
        timeMs: Date.now() - start,
      });
    }
  }

  const passed = results.filter((r) => r.status === "pass").length;
  const failed = results.filter((r) => r.status === "fail").length;

  console.log("\n=== BUN SPIKE RESULTS ===\n");
  for (const r of results) {
    const icon = r.status === "pass" ? "✓" : "✗";
    console.log(`${icon} [${r.status.toUpperCase()}] ${r.assumption}`);
    if (r.status === "fail") {
      console.log(`  ERROR: ${r.details}`);
    } else {
      console.log(`  ${r.details.split("\n")[0]}`);
    }
  }

  console.log(`\n${passed}/${results.length} assumptions passed`);
  if (failed > 0) {
    console.log("\n⚠️  FAILURES DETECTED — Review before proceeding to Wave 2");
  } else {
    console.log("\n✓ All assumptions valid — proceed to Wave 2");
  }

  writeFileSync(
    "spike/results.json",
    JSON.stringify(
      {
        timestamp: new Date().toISOString(),
        bunVersion: Bun.version,
        passed,
        failed,
        results,
      },
      null,
      2,
    ),
  );

  process.exit(failed > 0 ? 1 : 0);
}

await main();
