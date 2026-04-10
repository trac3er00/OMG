interface ImssEntry<T> {
  readonly value: T;
  readonly expiresAt?: number;
}

export class IMSS<T> {
  private readonly entries = new Map<string, ImssEntry<T>>();

  private isExpired(entry: ImssEntry<T>, now = Date.now()): boolean {
    return entry.expiresAt !== undefined && entry.expiresAt <= now;
  }

  private pruneKey(key: string, now = Date.now()): ImssEntry<T> | undefined {
    const entry = this.entries.get(key);
    if (entry === undefined) {
      return undefined;
    }

    if (this.isExpired(entry, now)) {
      this.entries.delete(key);
      return undefined;
    }

    return entry;
  }

  private pruneExpired(now = Date.now()): void {
    for (const [key, entry] of this.entries) {
      if (this.isExpired(entry, now)) {
        this.entries.delete(key);
      }
    }
  }

  get(key: string): T | undefined {
    return this.pruneKey(key)?.value;
  }

  set(key: string, value: T, ttl?: number): void {
    const expiresAt = ttl === undefined ? undefined : Date.now() + ttl;
    this.entries.set(
      key,
      expiresAt === undefined ? { value } : { value, expiresAt },
    );
  }

  delete(key: string): boolean {
    this.pruneKey(key);
    return this.entries.delete(key);
  }

  list(prefix = ""): string[] {
    this.pruneExpired();
    const keys = [...this.entries.keys()].filter((key) =>
      key.startsWith(prefix),
    );
    return keys.sort((left, right) => left.localeCompare(right));
  }

  clear(): void {
    this.entries.clear();
  }
}
