import { describe, test, expect } from "bun:test";
import {
  scoreTrustChange,
  getTrustDecision,
  TrustReviewManager,
} from "./trust-review.js";
import { generateKeyPairSync } from "node:crypto";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { rmSync } from "node:fs";

describe("scoreTrustChange", () => {
  test("adding new MCP server scores high", () => {
    const score = scoreTrustChange({ type: "mcp_server_added", count: 1 });
    expect(score).toBeGreaterThanOrEqual(45);
  });

  test("adding hook scores medium-high", () => {
    const score = scoreTrustChange({ type: "hook_added", count: 1 });
    expect(score).toBeGreaterThanOrEqual(20);
  });

  test("permission scope expansion scores very high", () => {
    const score = scoreTrustChange({ type: "permission_scope_expanded", count: 1 });
    expect(score).toBeGreaterThanOrEqual(60);
  });

  test("env permission added scores high", () => {
    const score = scoreTrustChange({ type: "env_permission_added", count: 1 });
    expect(score).toBeGreaterThanOrEqual(50);
  });

  test("trivial change scores low", () => {
    const score = scoreTrustChange({ type: "description_changed", count: 1 });
    expect(score).toBeLessThan(20);
  });

  test("unknown type gets default score", () => {
    const score = scoreTrustChange({ type: "something_new", count: 1 });
    expect(score).toBeGreaterThanOrEqual(20);
  });

  test("count multiplier caps at 3", () => {
    const single = scoreTrustChange({ type: "mcp_server_added", count: 1 });
    const five = scoreTrustChange({ type: "mcp_server_added", count: 5 });
    expect(five).toBe(single * 3);
  });
});

describe("getTrustDecision", () => {
  test("score >= 80 → deny", () => {
    expect(getTrustDecision(80)).toBe("deny");
    expect(getTrustDecision(85)).toBe("deny");
    expect(getTrustDecision(100)).toBe("deny");
  });

  test("score >= 45 → ask", () => {
    expect(getTrustDecision(45)).toBe("ask");
    expect(getTrustDecision(60)).toBe("ask");
    expect(getTrustDecision(79)).toBe("ask");
  });

  test("score < 45 → allow", () => {
    expect(getTrustDecision(0)).toBe("allow");
    expect(getTrustDecision(20)).toBe("allow");
    expect(getTrustDecision(44)).toBe("allow");
  });
});

describe("TrustReviewManager", () => {
  function makeTempDir(): string {
    return join(tmpdir(), `trust-test-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  }

  test("generate + sign + verify manifest", async () => {
    const dir = makeTempDir();
    const { privateKey, publicKey } = generateKeyPairSync("ed25519");
    const mgr = new TrustReviewManager({ projectDir: dir, privateKey, publicKey });

    const manifest = await mgr.generateManifest({ "test.json": JSON.stringify({ x: 1 }) });
    expect(manifest.signature).toBeTruthy();
    expect(manifest.version).toBe(1);
    expect(manifest.files).toHaveLength(1);
    expect(manifest.files[0]!.path).toBe("test.json");
    expect(manifest.digest).toBeTruthy();
    expect(manifest.createdAt).toBeTruthy();

    const valid = await mgr.verifyManifest(manifest);
    expect(valid).toBe(true);

    rmSync(dir, { recursive: true, force: true });
  });

  test("tampered manifest fails verify", async () => {
    const dir = makeTempDir();
    const { privateKey, publicKey } = generateKeyPairSync("ed25519");
    const mgr = new TrustReviewManager({ projectDir: dir, privateKey, publicKey });

    const manifest = await mgr.generateManifest({ "test.json": "{}" });
    const tampered = { ...manifest, digest: "tampered-digest" };

    const valid = await mgr.verifyManifest(tampered);
    expect(valid).toBe(false);

    rmSync(dir, { recursive: true, force: true });
  });

  test("wrong key pair fails verify", async () => {
    const dir = makeTempDir();
    const { privateKey } = generateKeyPairSync("ed25519");
    const { publicKey: wrongPublic } = generateKeyPairSync("ed25519");
    const mgr = new TrustReviewManager({ projectDir: dir, privateKey, publicKey: wrongPublic });

    const manifest = await mgr.generateManifest({ "a.json": "{}" });
    const valid = await mgr.verifyManifest(manifest);
    expect(valid).toBe(false);

    rmSync(dir, { recursive: true, force: true });
  });

  test("manifest without signature fails verify", async () => {
    const dir = makeTempDir();
    const { publicKey } = generateKeyPairSync("ed25519");
    const mgr = new TrustReviewManager({ projectDir: dir, publicKey });

    const manifest = await mgr.generateManifest({ "test.json": "{}" });
    expect(manifest.signature).toBe("");

    const valid = await mgr.verifyManifest(manifest);
    expect(valid).toBe(false);

    rmSync(dir, { recursive: true, force: true });
  });

  test("multiple files in manifest", async () => {
    const dir = makeTempDir();
    const { privateKey, publicKey } = generateKeyPairSync("ed25519");
    const mgr = new TrustReviewManager({ projectDir: dir, privateKey, publicKey });

    const manifest = await mgr.generateManifest({
      "a.json": '{"a":1}',
      "b.json": '{"b":2}',
      "c.json": '{"c":3}',
    });
    expect(manifest.files).toHaveLength(3);

    const valid = await mgr.verifyManifest(manifest);
    expect(valid).toBe(true);

    rmSync(dir, { recursive: true, force: true });
  });

  test("loadManifest returns undefined when no file", () => {
    const dir = makeTempDir();
    const mgr = new TrustReviewManager({ projectDir: dir });
    expect(mgr.loadManifest()).toBeUndefined();
    rmSync(dir, { recursive: true, force: true });
  });

  test("loadManifest reads persisted manifest", async () => {
    const dir = makeTempDir();
    const { privateKey, publicKey } = generateKeyPairSync("ed25519");
    const mgr = new TrustReviewManager({ projectDir: dir, privateKey, publicKey });

    const original = await mgr.generateManifest({ "x.json": "42" });
    const loaded = mgr.loadManifest();
    expect(loaded).toBeTruthy();
    expect(loaded!.digest).toBe(original.digest);
    expect(loaded!.signature).toBe(original.signature);

    rmSync(dir, { recursive: true, force: true });
  });
});
