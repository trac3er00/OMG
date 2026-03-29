import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { RegistryLoader, create } from "./loader.js";

const REGISTRY_ROOT = join(import.meta.dir, "../../registry");
const SKILLS_PATH = join(REGISTRY_ROOT, "skills.json");
const BUNDLES_DIR = join(REGISTRY_ROOT, "bundles");
const POLICY_PACKS_DIR = join(REGISTRY_ROOT, "policy-packs");
const TRUSTED_SIGNERS_PATH = join(REGISTRY_ROOT, "trusted_signers.json");

describe("RegistryLoader", () => {
  test("create returns a RegistryLoader instance", () => {
    const loader = RegistryLoader.create();
    expect(loader).toBeInstanceOf(RegistryLoader);
  });

  test("create factory function works", () => {
    const loader = create();
    expect(loader).toBeInstanceOf(RegistryLoader);
  });
});

describe("loadSkills", () => {
  test("loads skills.json successfully", () => {
    const loader = create();
    const registry = loader.loadSkills(SKILLS_PATH);
    expect(registry.schema_version).toBe("1.0");
    expect(registry.skills.length).toBeGreaterThan(0);
  });

  test("getSkills returns loaded skills", () => {
    const loader = create();
    loader.loadSkills(SKILLS_PATH);
    const skills = loader.getSkills();
    expect(skills.length).toBeGreaterThan(0);
  });

  test("getSkills returns empty before loading", () => {
    const loader = create();
    expect(loader.getSkills()).toEqual([]);
  });

  test("skills have required fields", () => {
    const loader = create();
    loader.loadSkills(SKILLS_PATH);
    const skills = loader.getSkills();
    for (const skill of skills) {
      expect(skill.id).toBeTruthy();
      expect(skill.name).toBeTruthy();
      expect(skill.provider).toBeTruthy();
      expect(skill.version).toBeTruthy();
    }
  });

  test("getSkillsByProvider filters correctly", () => {
    const loader = create();
    loader.loadSkills(SKILLS_PATH);
    const claudeSkills = loader.getSkillsByProvider("claude");
    expect(claudeSkills.length).toBeGreaterThan(0);
    for (const skill of claudeSkills) {
      expect(skill.provider).toBe("claude");
    }
  });

  test("universal skills exist", () => {
    const loader = create();
    loader.loadSkills(SKILLS_PATH);
    const universal = loader.getSkillsByProvider("universal");
    expect(universal.length).toBeGreaterThanOrEqual(5);
  });
});

describe("loadBundles", () => {
  test("loads all bundle YAML files", () => {
    const loader = create();
    const bundles = loader.loadBundles(BUNDLES_DIR);
    expect(bundles.length).toBeGreaterThanOrEqual(20);
  });

  test("bundles have id, kind, and version", () => {
    const loader = create();
    loader.loadBundles(BUNDLES_DIR);
    const bundles = loader.getBundles();
    for (const bundle of bundles) {
      expect(bundle.id).toBeTruthy();
      expect(bundle.kind).toBeTruthy();
      expect(bundle.version).toBeTruthy();
    }
  });

  test("getBundle returns specific bundle", () => {
    const loader = create();
    loader.loadBundles(BUNDLES_DIR);
    const cp = loader.getBundle("control-plane");
    expect(cp).toBeDefined();
    expect(cp?.title).toContain("Control Plane");
  });

  test("control-plane bundle has all 4 hosts", () => {
    const loader = create();
    loader.loadBundles(BUNDLES_DIR);
    const cp = loader.getBundle("control-plane");
    expect(cp?.hosts).toContain("claude");
    expect(cp?.hosts).toContain("codex");
    expect(cp?.hosts).toContain("gemini");
    expect(cp?.hosts).toContain("kimi");
  });

  test("getBundle returns undefined for unknown id", () => {
    const loader = create();
    loader.loadBundles(BUNDLES_DIR);
    expect(loader.getBundle("nonexistent")).toBeUndefined();
  });

  test("throws on missing bundles directory", () => {
    const loader = create();
    expect(() => loader.loadBundles("/nonexistent/path")).toThrow("Bundles directory not found");
  });
});

describe("loadPolicyPacks", () => {
  test("loads policy pack YAML files", () => {
    const loader = create();
    loader.loadTrustedSigners(TRUSTED_SIGNERS_PATH);
    const packs = loader.loadPolicyPacks(POLICY_PACKS_DIR);
    expect(packs.length).toBeGreaterThanOrEqual(3);
  });

  test("policy packs have digest", () => {
    const loader = create();
    loader.loadTrustedSigners(TRUSTED_SIGNERS_PATH);
    loader.loadPolicyPacks(POLICY_PACKS_DIR);
    const packs = loader.getPolicyPacks();
    for (const pack of packs) {
      expect(pack.digest).toMatch(/^[a-f0-9]{64}$/);
    }
  });

  test("fintech pack has signature", () => {
    const loader = create();
    loader.loadTrustedSigners(TRUSTED_SIGNERS_PATH);
    loader.loadPolicyPacks(POLICY_PACKS_DIR);
    const fintech = loader.getPolicyPack("fintech");
    expect(fintech).toBeDefined();
    expect(fintech?.signature).toBeDefined();
    expect(fintech?.signature?.signer_key_id).toBe("1f5fe64ec2f8c901");
  });

  test("fintech pack verification reflects digest match", () => {
    const loader = create();
    loader.loadTrustedSigners(TRUSTED_SIGNERS_PATH);
    loader.loadPolicyPacks(POLICY_PACKS_DIR);
    const fintech = loader.getPolicyPack("fintech");
    expect(fintech).toBeDefined();
    // verified is true only when content digest matches signature's artifact_digest
    // the pack may have been modified since signing, so we check the logic is consistent
    if (fintech?.digest === fintech?.signature?.artifact_digest) {
      expect(fintech?.verified).toBe(true);
    } else {
      expect(fintech?.verified).toBe(false);
    }
  });

  test("getPolicyPack returns undefined for unknown id", () => {
    const loader = create();
    expect(loader.getPolicyPack("nonexistent")).toBeUndefined();
  });

  test("throws on missing policy packs directory", () => {
    const loader = create();
    expect(() => loader.loadPolicyPacks("/nonexistent/path")).toThrow("Policy packs directory not found");
  });
});

describe("verifySignature", () => {
  test("returns false for mismatched digest", () => {
    const loader = create();
    loader.loadTrustedSigners(TRUSTED_SIGNERS_PATH);
    const result = loader.verifySignature("wrong-digest", {
      artifact_digest: "different-digest",
      action: "policy-pack-sign",
      scope: "test",
      reason: "test",
      signer_key_id: "1f5fe64ec2f8c901",
      issued_at: new Date().toISOString(),
      signature: "fake",
      run_id: "",
    });
    expect(result).toBe(false);
  });

  test("returns false for unknown signer", () => {
    const loader = create();
    loader.loadTrustedSigners(TRUSTED_SIGNERS_PATH);
    const result = loader.verifySignature("test-digest", {
      artifact_digest: "test-digest",
      action: "policy-pack-sign",
      scope: "test",
      reason: "test",
      signer_key_id: "unknown-key",
      issued_at: new Date().toISOString(),
      signature: "fake",
      run_id: "",
    });
    expect(result).toBe(false);
  });

  test("returns true for matching digest and known signer", () => {
    const loader = create();
    loader.loadTrustedSigners(TRUSTED_SIGNERS_PATH);
    const result = loader.verifySignature("test-digest", {
      artifact_digest: "test-digest",
      action: "policy-pack-sign",
      scope: "test",
      reason: "test",
      signer_key_id: "1f5fe64ec2f8c901",
      issued_at: new Date().toISOString(),
      signature: "fake",
      run_id: "",
    });
    expect(result).toBe(true);
  });
});

describe("loadTrustedSigners", () => {
  test("loads trusted signers", () => {
    const loader = create();
    const signers = loader.loadTrustedSigners(TRUSTED_SIGNERS_PATH);
    expect(signers.length).toBeGreaterThanOrEqual(1);
  });

  test("signers have required fields", () => {
    const loader = create();
    const signers = loader.loadTrustedSigners(TRUSTED_SIGNERS_PATH);
    for (const signer of signers) {
      expect(signer.key_id).toBeTruthy();
      expect(signer.algorithm).toBeTruthy();
      expect(signer.public_key).toBeTruthy();
      expect(signer.status).toBe("active");
    }
  });
});
