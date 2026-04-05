import { describe, expect, test } from "bun:test";
import { RateLimiter } from "./rate-limiter.js";

describe("RateLimiter", () => {
  test("allows first 50 requests and throttles 51st", () => {
    let nowMs = 1_700_000_000_000;
    const limiter = RateLimiter.create({
      maxTokens: 50,
      refillRatePerSecond: 0,
      now: () => nowMs,
    });

    for (let i = 0; i < 50; i += 1) {
      const decision = limiter.consume("client-A");
      expect(decision.allowed).toBe(true);
    }

    const blocked = limiter.consume("client-A");
    expect(blocked.allowed).toBe(false);
    expect(blocked.remaining).toBe(0);

    nowMs += 1000;
    const stillBlocked = limiter.consume("client-A");
    expect(stillBlocked.allowed).toBe(false);
  });

  test("refills over time", () => {
    let nowMs = 1_700_000_000_000;
    const limiter = RateLimiter.create({
      maxTokens: 5,
      refillRatePerSecond: 2,
      now: () => nowMs,
    });

    for (let i = 0; i < 5; i += 1) {
      expect(limiter.consume("client-B").allowed).toBe(true);
    }
    expect(limiter.consume("client-B").allowed).toBe(false);

    nowMs += 500;
    expect(limiter.consume("client-B").allowed).toBe(true);
  });
});
