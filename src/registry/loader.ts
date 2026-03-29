import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { createHash } from "node:crypto";
import { z } from "zod";

// ---------------------------------------------------------------------------
// Skill schemas
// ---------------------------------------------------------------------------

const SkillEntrySchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  category: z.string(),
  provider: z.string(),
  path: z.string(),
  keywords: z.array(z.string()),
  version: z.string(),
  enabled: z.boolean(),
});

const SkillsRegistrySchema = z.object({
  schema_version: z.string(),
  registry_version: z.string(),
  skills: z.array(SkillEntrySchema),
});

export type SkillEntry = z.infer<typeof SkillEntrySchema>;
export type SkillsRegistry = z.infer<typeof SkillsRegistrySchema>;

// ---------------------------------------------------------------------------
// Bundle schema (YAML subset parsed as key-value — no yaml dep)
// ---------------------------------------------------------------------------

export interface BundleManifest {
  readonly id: string;
  readonly kind: string;
  readonly version: string;
  readonly title: string;
  readonly description: string;
  readonly hosts: readonly string[];
  readonly raw: string;
}

// ---------------------------------------------------------------------------
// Policy pack schemas
// ---------------------------------------------------------------------------

const PolicyPackSignatureSchema = z.object({
  artifact_digest: z.string(),
  action: z.string(),
  scope: z.string(),
  reason: z.string(),
  signer_key_id: z.string(),
  issued_at: z.string(),
  signature: z.string(),
  run_id: z.string(),
});

export type PolicyPackSignature = z.infer<typeof PolicyPackSignatureSchema>;

export interface PolicyPack {
  readonly id: string;
  readonly content: string;
  readonly digest: string;
  readonly signature: PolicyPackSignature | undefined;
  readonly verified: boolean;
}

// ---------------------------------------------------------------------------
// Trusted signers
// ---------------------------------------------------------------------------

const TrustedSignerSchema = z.object({
  key_id: z.string(),
  algorithm: z.string(),
  public_key: z.string(),
  status: z.string(),
  usage: z.array(z.string()),
  owner: z.string(),
  notes: z.string(),
});

const TrustedSignersSchema = z.object({
  version: z.number(),
  signers: z.array(TrustedSignerSchema),
});

export type TrustedSigner = z.infer<typeof TrustedSignerSchema>;

// ---------------------------------------------------------------------------
// Minimal YAML parser (key: value and - list items only, no external deps)
// ---------------------------------------------------------------------------

function parseSimpleYaml(content: string): Record<string, string | string[]> {
  const result: Record<string, string | string[]> = {};
  let currentKey = "";

  for (const line of content.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    const kvMatch = trimmed.match(/^([a-z_]+)\s*:\s*(.*)$/);
    if (kvMatch) {
      const key = kvMatch[1] as string;
      const value = (kvMatch[2] as string).trim();
      if (!value) {
        currentKey = key;
        result[key] = [];
      } else {
        result[key] = value;
        currentKey = "";
      }
      continue;
    }

    const listMatch = trimmed.match(/^-\s+(.+)$/);
    if (listMatch && currentKey) {
      const arr = result[currentKey];
      if (Array.isArray(arr)) {
        arr.push((listMatch[1] as string).trim());
      }
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// RegistryLoader
// ---------------------------------------------------------------------------

export class RegistryLoader {
  private skills: SkillsRegistry | undefined;
  private readonly bundles: Map<string, BundleManifest> = new Map();
  private readonly policyPacks: Map<string, PolicyPack> = new Map();
  private trustedSigners: readonly TrustedSigner[] = [];

  private constructor() {}

  static create(): RegistryLoader {
    return new RegistryLoader();
  }

  loadTrustedSigners(filePath: string): readonly TrustedSigner[] {
    const raw = readFileSync(filePath, "utf8");
    const parsed = TrustedSignersSchema.parse(JSON.parse(raw));
    this.trustedSigners = parsed.signers;
    return this.trustedSigners;
  }

  loadSkills(filePath: string): SkillsRegistry {
    const raw = readFileSync(filePath, "utf8");
    const parsed: unknown = JSON.parse(raw);
    this.skills = SkillsRegistrySchema.parse(parsed);
    return this.skills;
  }

  getSkills(): readonly SkillEntry[] {
    return this.skills?.skills ?? [];
  }

  getSkillsByProvider(provider: string): readonly SkillEntry[] {
    return this.getSkills().filter((s) => s.provider === provider);
  }

  loadBundles(dir: string): readonly BundleManifest[] {
    const resolvedDir = resolve(dir);
    if (!existsSync(resolvedDir)) {
      throw new Error(`Bundles directory not found: ${resolvedDir}`);
    }

    const files = readdirSync(resolvedDir).filter((f) => f.endsWith(".yaml"));
    const loaded: BundleManifest[] = [];

    for (const file of files) {
      const filePath = join(resolvedDir, file);
      const raw = readFileSync(filePath, "utf8");
      const parsed = parseSimpleYaml(raw);

      const bundle: BundleManifest = {
        id: (parsed["id"] as string) ?? file.replace(".yaml", ""),
        kind: (parsed["kind"] as string) ?? "skill",
        version: (parsed["version"] as string) ?? "0.0.0",
        title: (parsed["title"] as string) ?? "",
        description: (parsed["description"] as string) ?? "",
        hosts: Array.isArray(parsed["hosts"]) ? parsed["hosts"] : [],
        raw,
      };

      this.bundles.set(bundle.id, bundle);
      loaded.push(bundle);
    }

    return loaded;
  }

  getBundles(): readonly BundleManifest[] {
    return Array.from(this.bundles.values());
  }

  getBundle(id: string): BundleManifest | undefined {
    return this.bundles.get(id);
  }

  loadPolicyPacks(dir: string): readonly PolicyPack[] {
    const resolvedDir = resolve(dir);
    if (!existsSync(resolvedDir)) {
      throw new Error(`Policy packs directory not found: ${resolvedDir}`);
    }

    const yamlFiles = readdirSync(resolvedDir).filter((f) => f.endsWith(".yaml"));
    const loaded: PolicyPack[] = [];

    for (const file of yamlFiles) {
      const packId = file.replace(".yaml", "");
      const filePath = join(resolvedDir, file);
      const content = readFileSync(filePath, "utf8");
      const digest = createHash("sha256").update(content).digest("hex");

      const sigPath = join(resolvedDir, `${packId}.signature.json`);
      let signature: PolicyPackSignature | undefined;
      let verified = false;

      if (existsSync(sigPath)) {
        const sigRaw = readFileSync(sigPath, "utf8");
        const sigParsed = PolicyPackSignatureSchema.safeParse(JSON.parse(sigRaw));
        if (sigParsed.success) {
          signature = sigParsed.data;
          verified = this.verifySignature(digest, signature);
        }
      }

      const pack: PolicyPack = { id: packId, content, digest, signature, verified };
      this.policyPacks.set(packId, pack);
      loaded.push(pack);
    }

    return loaded;
  }

  /**
   * Verify a policy pack signature against trusted signers.
   * Checks: digest match + signer key_id is in trusted_signers with active status.
   */
  verifySignature(digest: string, signature: PolicyPackSignature): boolean {
    if (signature.artifact_digest !== digest) {
      return false;
    }

    const signer = this.trustedSigners.find(
      (s) => s.key_id === signature.signer_key_id && s.status === "active",
    );

    return signer !== undefined;
  }

  getPolicyPacks(): readonly PolicyPack[] {
    return Array.from(this.policyPacks.values());
  }

  getPolicyPack(id: string): PolicyPack | undefined {
    return this.policyPacks.get(id);
  }
}

export function create(): RegistryLoader {
  return RegistryLoader.create();
}
