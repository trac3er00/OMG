import { describe, test, expect } from "bun:test";
import {
  encrypt,
  decrypt,
  deriveKey,
  sign,
  verify as verifySignature,
  hmacSign,
  hash,
  randomBytes,
  type EncryptedPayload,
} from "./crypto.js";
import { generateKeyPairSync } from "node:crypto";

describe("AES-256-GCM", () => {
  test("encrypt/decrypt roundtrip", async () => {
    const key = await deriveKey("passphrase", "salt12345678901234567890");
    const plaintext = "Hello, OMG v3!";
    const payload = encrypt(plaintext, key);
    expect(payload.ciphertext).not.toBe(plaintext);
    expect(payload.iv).toHaveLength(24);
    expect(payload.authTag).toBeTruthy();
    const decrypted = decrypt(payload, key);
    expect(decrypted).toBe(plaintext);
  });

  test("different plaintexts produce different ciphertexts", async () => {
    const key = await deriveKey("passphrase", "salt12345678901234567890");
    const p1 = encrypt("hello", key);
    const p2 = encrypt("hello", key);
    expect(p1.iv).not.toBe(p2.iv);
  });

  test("tampered ciphertext throws on decrypt", async () => {
    const key = await deriveKey("passphrase", "salt12345678901234567890");
    const payload = encrypt("secret", key);
    const tampered: EncryptedPayload = {
      ...payload,
      ciphertext: "dGFtcGVyZWQ=",
    };
    expect(() => decrypt(tampered, key)).toThrow();
  });

  test("wrong key throws on decrypt", async () => {
    const key1 = await deriveKey("passphrase1", "salt12345678901234567890");
    const key2 = await deriveKey("passphrase2", "salt12345678901234567890");
    const payload = encrypt("secret", key1);
    expect(() => decrypt(payload, key2)).toThrow();
  });

  test("empty plaintext roundtrip", async () => {
    const key = await deriveKey("passphrase", "salt12345678901234567890");
    const payload = encrypt("", key);
    expect(decrypt(payload, key)).toBe("");
  });
});

describe("PBKDF2 key derivation", () => {
  test("produces 32-byte key", async () => {
    const key = await deriveKey("passphrase", "salt");
    expect(key).toHaveLength(32);
  });

  test("same inputs produce same key (deterministic)", async () => {
    const k1 = await deriveKey("test", "salt");
    const k2 = await deriveKey("test", "salt");
    expect(Buffer.from(k1).toString("hex")).toBe(Buffer.from(k2).toString("hex"));
  });

  test("different passphrases produce different keys", async () => {
    const k1 = await deriveKey("pass1", "salt");
    const k2 = await deriveKey("pass2", "salt");
    expect(Buffer.from(k1).toString("hex")).not.toBe(Buffer.from(k2).toString("hex"));
  });

  test("Python PBKDF2 parity: known hex output", async () => {
    const expected = "aef7d31b8440f1227cf763f710086f7acfd656450e828b8a190f79b71d840b2c";
    const key = await deriveKey("testpassphrase", "testsalt12345678", 600_000);
    expect(Buffer.from(key).toString("hex")).toBe(expected);
  });
});

describe("Ed25519 signing", () => {
  test("sign and verify roundtrip", () => {
    const { privateKey, publicKey } = generateKeyPairSync("ed25519");
    const data = Buffer.from("important data");
    const sig = sign(data, privateKey);
    expect(verifySignature(data, sig, publicKey)).toBe(true);
  });

  test("tampered data fails verify", () => {
    const { privateKey, publicKey } = generateKeyPairSync("ed25519");
    const data = Buffer.from("important data");
    const sig = sign(data, privateKey);
    const tampered = Buffer.from("tampered data!!");
    expect(verifySignature(tampered, sig, publicKey)).toBe(false);
  });

  test("wrong public key fails verify", () => {
    const { privateKey } = generateKeyPairSync("ed25519");
    const { publicKey: wrongPub } = generateKeyPairSync("ed25519");
    const data = Buffer.from("data");
    const sig = sign(data, privateKey);
    expect(verifySignature(data, sig, wrongPub)).toBe(false);
  });
});

describe("HMAC-SHA256", () => {
  test("same inputs produce same signature", () => {
    const s1 = hmacSign("data", "secret");
    const s2 = hmacSign("data", "secret");
    expect(s1).toBe(s2);
  });

  test("different secrets produce different signatures", () => {
    const s1 = hmacSign("data", "secret1");
    const s2 = hmacSign("data", "secret2");
    expect(s1).not.toBe(s2);
  });

  test("produces 64-char hex string", () => {
    const s = hmacSign("data", "secret");
    expect(s).toHaveLength(64);
    expect(/^[0-9a-f]+$/.test(s)).toBe(true);
  });
});

describe("SHA-256 hash", () => {
  test("known hash", () => {
    expect(hash("hello")).toBe("2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824");
  });

  test("different inputs differ", () => {
    expect(hash("a")).not.toBe(hash("b"));
  });
});

describe("randomBytes", () => {
  test("produces requested length", () => {
    const bytes = randomBytes(16);
    expect(bytes).toHaveLength(16);
  });

  test("two calls produce different values", () => {
    const b1 = randomBytes(16).toString("hex");
    const b2 = randomBytes(16).toString("hex");
    expect(b1).not.toBe(b2);
  });
});
