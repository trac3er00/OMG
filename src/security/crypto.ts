import {
  createCipheriv,
  createDecipheriv,
  createHmac,
  createHash,
  pbkdf2Sync,
  randomBytes as nodeRandomBytes,
  sign as nodeSign,
  verify as nodeVerify,
} from "node:crypto";
import type { KeyObject } from "node:crypto";

export interface EncryptedPayload {
  readonly ciphertext: string;
  readonly iv: string;
  readonly authTag: string;
  readonly algorithm: "aes-256-gcm";
}

const ALGORITHM = "aes-256-gcm" as const;
const IV_LENGTH = 16;
const AUTH_TAG_LENGTH = 16;
const KEY_LENGTH = 32;
const DEFAULT_PBKDF2_ITERATIONS = 600_000;
const DEFAULT_PBKDF2_DIGEST = "sha256" as const;

export function encrypt(plaintext: string, key: Uint8Array | Buffer): EncryptedPayload {
  const iv = nodeRandomBytes(IV_LENGTH);
  const cipher = createCipheriv(ALGORITHM, key, iv, { authTagLength: AUTH_TAG_LENGTH });
  const ciphertext = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const authTag = cipher.getAuthTag();

  return {
    ciphertext: ciphertext.toString("base64"),
    iv: iv.toString("base64"),
    authTag: authTag.toString("base64"),
    algorithm: ALGORITHM,
  };
}

export function decrypt(payload: EncryptedPayload, key: Uint8Array | Buffer): string {
  const iv = Buffer.from(payload.iv, "base64");
  const ciphertext = Buffer.from(payload.ciphertext, "base64");
  const authTag = Buffer.from(payload.authTag, "base64");

  const decipher = createDecipheriv(ALGORITHM, key, iv, { authTagLength: AUTH_TAG_LENGTH });
  decipher.setAuthTag(authTag);
  const decrypted = Buffer.concat([decipher.update(ciphertext), decipher.final()]);

  return decrypted.toString("utf8");
}

export async function deriveKey(
  passphrase: string,
  salt: string,
  iterations: number = DEFAULT_PBKDF2_ITERATIONS,
): Promise<Buffer> {
  return new Promise((resolve) => {
    const key = pbkdf2Sync(
      Buffer.from(passphrase, "utf8"),
      Buffer.from(salt, "utf8"),
      iterations,
      KEY_LENGTH,
      DEFAULT_PBKDF2_DIGEST,
    );
    resolve(key);
  });
}

export function sign(data: Buffer, privateKey: KeyObject): Buffer {
  return nodeSign(null, data, privateKey) as Buffer;
}

export function verify(data: Buffer, signature: Buffer, publicKey: KeyObject): boolean {
  try {
    return nodeVerify(null, data, publicKey, signature);
  } catch {
    return false;
  }
}

export function hmacSign(data: string, secret: string): string {
  return createHmac("sha256", secret).update(data, "utf8").digest("hex");
}

export function hash(data: string): string {
  return createHash("sha256").update(data, "utf8").digest("hex");
}

export function randomBytes(length: number): Buffer {
  return nodeRandomBytes(length);
}
