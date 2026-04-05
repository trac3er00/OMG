import { encrypt, decrypt, deriveKey } from "./crypto.js";
import type { EncryptedPayload } from "./crypto.js";
import { atomicWriteJson, readJsonFile } from "../state/atomic-io.js";
import { StateResolver } from "../state/state-resolver.js";
import { join } from "node:path";

export interface CredentialStoreConfig {
  readonly projectDir: string;
  readonly passphrase: string;
}

interface StoredCredentials {
  readonly version: number;
  readonly entries: Record<string, string>;
}

export class CredentialStore {
  private readonly storePath: string;
  private encryptionKey: Buffer | null = null;
  private readonly passphrase: string;

  constructor(config: CredentialStoreConfig) {
    const resolver = new StateResolver(config.projectDir);
    this.storePath = resolver.resolve(join("ledger", "credentials.enc"));
    this.passphrase = config.passphrase;
  }

  getStorePath(): string {
    return this.storePath;
  }

  private async getKey(): Promise<Buffer> {
    if (!this.encryptionKey) {
      this.encryptionKey = await deriveKey(this.passphrase, "omg-credential-salt-v3", 600_000);
    }
    return this.encryptionKey;
  }

  private async loadStore(): Promise<Record<string, string>> {
    const data = readJsonFile<{ payload: string }>(this.storePath);
    if (!data?.payload) return {};

    try {
      const key = await this.getKey();
      const decrypted = decrypt(JSON.parse(data.payload) as EncryptedPayload, key);
      const parsed = JSON.parse(decrypted) as StoredCredentials;
      return { ...parsed.entries };
    } catch {
      return {};
    }
  }

  private async saveStore(entries: Record<string, string>): Promise<void> {
    const key = await this.getKey();
    const plaintext = JSON.stringify({ version: 1, entries } satisfies StoredCredentials);
    const payload = encrypt(plaintext, key);
    atomicWriteJson(this.storePath, { payload: JSON.stringify(payload) });
  }

  async set(name: string, value: string): Promise<void> {
    const entries = await this.loadStore();
    entries[name] = value;
    await this.saveStore(entries);
  }

  async get(name: string): Promise<string | null> {
    const entries = await this.loadStore();
    return entries[name] ?? null;
  }

  async delete(name: string): Promise<boolean> {
    const entries = await this.loadStore();
    if (!(name in entries)) return false;
    delete entries[name];
    await this.saveStore(entries);
    return true;
  }

  async list(): Promise<string[]> {
    const entries = await this.loadStore();
    return Object.keys(entries);
  }

  close(): void {
    this.encryptionKey = null;
  }
}
