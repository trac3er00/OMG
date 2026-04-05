import { StateResolver } from "../state/state-resolver.js";
import { atomicWriteJson, readJsonFile } from "../state/atomic-io.js";

const PACKET_VERSION = "v2";
const MAX_SUMMARY_CHARS = 1000;

type JsonScalar = string | number | boolean | null;
type JsonLike = JsonScalar | JsonLike[] | { readonly [key: string]: JsonLike };

export interface ProfileDigest {
  readonly architecture_requests: readonly string[];
  readonly constraints: Readonly<Record<string, string | number | boolean | null>>;
  readonly tags: readonly string[];
  readonly summary: string;
  readonly confidence: number;
  readonly profile_version: string;
}

export interface ContextPacket {
  readonly packet_version: string;
  readonly summary: string;
  readonly artifact_pointers: readonly string[];
  readonly provenance_pointers: readonly string[];
  readonly artifact_handles: readonly Readonly<Record<string, JsonLike>>[];
  readonly clarification_status: {
    readonly requires_clarification: boolean;
    readonly intent_class: string;
    readonly clarification_prompt: string;
    readonly confidence: number;
  };
  readonly ambiguity_state: {
    readonly status: "resolved" | "unresolved";
    readonly unresolved: boolean;
    readonly requires_clarification: boolean;
    readonly missing_slots: readonly string[];
    readonly updated_at: string;
  };
  readonly provenance_only: boolean;
  readonly governance: Readonly<Record<string, JsonLike>>;
  readonly release_metadata: Readonly<Record<string, JsonLike>>;
  readonly coordinator_run_id: string;
  readonly profile_digest: ProfileDigest;
  readonly budget: {
    readonly max_chars: number;
    readonly used_chars: number;
  };
  readonly delta_only: boolean;
  readonly run_id: string;
  readonly deterministic_contract: Readonly<Record<string, JsonLike>>;
  readonly derived_action_summary?: string;
}

function emptyProfileDigest(): ProfileDigest {
  return {
    architecture_requests: [],
    constraints: {},
    tags: [],
    summary: "",
    confidence: 0,
    profile_version: "",
  };
}

function normalizeStringArray(value: unknown, maxItems: number): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const out: string[] = [];
  for (const item of value) {
    const token = String(item).trim();
    if (!token) {
      continue;
    }
    out.push(token);
    if (out.length >= maxItems) {
      break;
    }
  }
  return out;
}

function normalizeConstraints(value: unknown, maxItems: number): Record<string, string | number | boolean | null> {
  if (!value || typeof value !== "object") {
    return {};
  }

  const out: Record<string, string | number | boolean | null> = {};
  for (const [key, raw] of Object.entries(value)) {
    const normalizedKey = key.trim().toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "").slice(0, 40);
    if (!normalizedKey) {
      continue;
    }

    let normalized: string | number | boolean | null;
    if (typeof raw === "boolean" || typeof raw === "number" || raw === null) {
      normalized = raw;
    } else {
      const text = String(raw).trim().toLowerCase();
      normalized = text ? text.slice(0, 80) : null;
    }
    if (normalized === null) {
      continue;
    }
    out[normalizedKey] = normalized;
    if (Object.keys(out).length >= maxItems) {
      break;
    }
  }

  return out;
}

export class ContextEngine {
  private readonly resolver: StateResolver;
  private lastSnapshot: string | null = null;

  constructor(projectDir: string) {
    this.resolver = new StateResolver(projectDir);
  }

  buildPacket(runId: string, deltaOnly = false): ContextPacket {
    const profileDigest = this.loadProfileDigest() ?? emptyProfileDigest();
    const summary = this.buildSummary(profileDigest);
    const snapshot = JSON.stringify(profileDigest);

    let finalSummary = summary;
    let artifactPointers: string[] = [];
    let provenancePointers: string[] = [];

    if (deltaOnly && this.lastSnapshot !== null && this.lastSnapshot === snapshot) {
      finalSummary = "no changes since last packet";
    }

    this.lastSnapshot = snapshot;

    const packet: ContextPacket = {
      packet_version: PACKET_VERSION,
      summary: finalSummary,
      artifact_pointers: artifactPointers,
      provenance_pointers: provenancePointers,
      artifact_handles: [],
      clarification_status: {
        requires_clarification: false,
        intent_class: "",
        clarification_prompt: "",
        confidence: 0,
      },
      ambiguity_state: {
        status: "resolved",
        unresolved: false,
        requires_clarification: false,
        missing_slots: [],
        updated_at: "",
      },
      provenance_only: false,
      governance: {},
      release_metadata: {},
      coordinator_run_id: runId,
      profile_digest: profileDigest,
      budget: {
        max_chars: MAX_SUMMARY_CHARS,
        used_chars: finalSummary.length,
      },
      delta_only: deltaOnly,
      run_id: runId,
      deterministic_contract: {
        run_id: runId,
        deterministic: true,
      },
      derived_action_summary: finalSummary,
    };

    this.persistPacket(packet);
    return packet;
  }

  loadProfileDigest(): ProfileDigest | null {
    const digestPath = this.resolver.resolve("profile_digest.json");
    const directDigest = readJsonFile<ProfileDigest>(digestPath);
    if (directDigest) {
      return {
        architecture_requests: normalizeStringArray(directDigest.architecture_requests, 3),
        constraints: normalizeConstraints(directDigest.constraints, 5),
        tags: normalizeStringArray(directDigest.tags, 5),
        summary: String(directDigest.summary ?? "").trim().slice(0, 120),
        confidence: Math.max(0, Math.min(1, Number(directDigest.confidence ?? 0))),
        profile_version: String(directDigest.profile_version ?? "").trim().slice(0, 64),
      };
    }

    return null;
  }

  renderProfileDigestText(digest: ProfileDigest | null, maxChars = 240): string {
    const source = digest ?? emptyProfileDigest();
    const arch = source.architecture_requests.map((item) => item.slice(0, 18)).join(",");
    const constraints = Object.entries(source.constraints)
      .slice(0, 5)
      .map(([key, value]) => `${key.slice(0, 14)}=${String(value).slice(0, 14)}`)
      .join(",");
    const tags = source.tags.map((tag) => tag.slice(0, 14)).join(",");
    const confidence = Number.isFinite(source.confidence) ? source.confidence.toFixed(2) : "0.00";
    const version = source.profile_version.slice(0, 24);
    const prefix = `arch[${arch}]|cons[${constraints}]|tags[${tags}]|conf=${confidence}|ver=${version}|sum=`;
    if (prefix.length >= maxChars) {
      return prefix.slice(0, maxChars);
    }

    const remaining = maxChars - prefix.length;
    const summary = source.summary.slice(0, remaining);
    return `${prefix}${summary}`;
  }

  private buildSummary(digest: ProfileDigest): string {
    const summary = digest.summary.trim();
    if (summary) {
      return summary.slice(0, MAX_SUMMARY_CHARS);
    }

    if (digest.architecture_requests.length > 0) {
      return `profile has ${digest.architecture_requests.length} architecture requests`;
    }

    return "no context signals available";
  }

  private persistPacket(packet: ContextPacket): void {
    const packetPath = this.resolver.resolve("context_engine_packet.json");
    atomicWriteJson(packetPath, packet);
  }
}
