export interface RateLimiterOptions {
  readonly maxTokens: number;
  readonly refillRatePerSecond: number;
  readonly now?: () => number;
}

export interface RateLimitDecision {
  readonly allowed: boolean;
  readonly remaining: number;
  readonly resetAt: number;
}

interface BucketState {
  tokens: number;
  lastRefillAt: number;
}

export class RateLimiter {
  private readonly maxTokens: number;
  private readonly refillRatePerSecond: number;
  private readonly now: () => number;
  private readonly buckets = new Map<string, BucketState>();

  private constructor(options: RateLimiterOptions) {
    if (options.maxTokens <= 0) {
      throw new Error("maxTokens must be greater than 0");
    }
    if (options.refillRatePerSecond < 0) {
      throw new Error("refillRatePerSecond must be >= 0");
    }

    this.maxTokens = options.maxTokens;
    this.refillRatePerSecond = options.refillRatePerSecond;
    this.now = options.now ?? Date.now;
  }

  static create(options: RateLimiterOptions): RateLimiter {
    return new RateLimiter(options);
  }

  consume(clientId: string, tokens = 1): RateLimitDecision {
    if (!clientId.trim()) {
      throw new Error("clientId must be non-empty");
    }
    if (tokens <= 0) {
      throw new Error("tokens must be greater than 0");
    }

    const now = this.now();
    const bucket = this.refillBucket(clientId, now);

    if (bucket.tokens >= tokens) {
      bucket.tokens -= tokens;
      return {
        allowed: true,
        remaining: Math.floor(bucket.tokens),
        resetAt: now,
      };
    }

    const missingTokens = tokens - bucket.tokens;
    const waitMs = this.refillRatePerSecond > 0 ? Math.ceil((missingTokens / this.refillRatePerSecond) * 1000) : Number.POSITIVE_INFINITY;

    return {
      allowed: false,
      remaining: Math.floor(bucket.tokens),
      resetAt: Number.isFinite(waitMs) ? now + waitMs : Number.MAX_SAFE_INTEGER,
    };
  }

  private refillBucket(clientId: string, now: number): BucketState {
    const existing = this.buckets.get(clientId);
    if (!existing) {
      const initial: BucketState = {
        tokens: this.maxTokens,
        lastRefillAt: now,
      };
      this.buckets.set(clientId, initial);
      return initial;
    }

    const elapsedSeconds = Math.max((now - existing.lastRefillAt) / 1000, 0);
    const refill = elapsedSeconds * this.refillRatePerSecond;
    existing.tokens = Math.min(this.maxTokens, existing.tokens + refill);
    existing.lastRefillAt = now;
    return existing;
  }
}
