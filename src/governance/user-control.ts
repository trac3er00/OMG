import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { load as loadYaml } from "js-yaml";
import { AuditTrail } from "../security/audit-trail.js";
import { atomicWriteJson } from "../state/atomic-io.js";
import { StateResolver } from "../state/state-resolver.js";
import {
  DEFAULT_ENFORCEMENT,
  type GovernanceEnforcement,
} from "./enforcement.js";

export const GOVERNANCE_CONFIG_PATH = [".omg", "governance.yaml"] as const;
export const GOVERNANCE_GATES = ["MutationGate", "ToolFabric"] as const;

export type GovernanceGateName = (typeof GOVERNANCE_GATES)[number];

export interface GateOverrideInput {
  readonly enabled?: boolean;
  readonly enforcement?: GovernanceEnforcement;
}

export interface GateConfigInput extends GateOverrideInput {
  readonly providers?: Readonly<Record<string, GateOverrideInput>>;
}

export interface GovernanceConfig {
  readonly version: number;
  readonly defaultProvider: string;
  readonly gates: Readonly<Record<GovernanceGateName, GateConfigInput>>;
}

export interface ResolvedGateControl {
  readonly gate: GovernanceGateName;
  readonly provider: string;
  readonly enabled: boolean;
  readonly enforcement: GovernanceEnforcement;
  readonly source: "default" | "file";
}

export interface GovernanceStatus {
  readonly provider: string;
  readonly configPath: string;
  readonly source: "default" | "file";
  readonly gates: readonly ResolvedGateControl[];
}

interface GovernanceSnapshot {
  readonly digest: string;
  readonly configPath: string;
}

const DEFAULT_CONFIG: GovernanceConfig = {
  version: 1,
  defaultProvider: "claude",
  gates: {
    MutationGate: {
      enabled: true,
      enforcement: "enforced",
      providers: {
        claude: {
          enabled: true,
          enforcement: "enforced",
        },
        ollama: {
          enabled: true,
          enforcement: "advisory",
        },
      },
    },
    ToolFabric: {
      enabled: true,
      enforcement: "enforced",
      providers: {
        claude: {
          enabled: true,
          enforcement: "enforced",
        },
        ollama: {
          enabled: true,
          enforcement: "advisory",
        },
      },
    },
  },
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isGovernanceEnforcement(
  value: unknown,
): value is GovernanceEnforcement {
  return value === "advisory" || value === "enforced";
}

function normalizeProvider(provider?: string | null): string {
  const value =
    provider ?? process.env.OMG_PROVIDER ?? DEFAULT_CONFIG.defaultProvider;
  const normalized = value.trim().toLowerCase();
  return normalized || DEFAULT_CONFIG.defaultProvider;
}

function normalizeGateOverride(value: unknown): GateOverrideInput {
  if (!isRecord(value)) {
    return {};
  }

  return {
    ...(typeof value.enabled === "boolean" ? { enabled: value.enabled } : {}),
    ...(isGovernanceEnforcement(value.enforcement)
      ? { enforcement: value.enforcement }
      : {}),
  };
}

function normalizeGateConfig(
  gate: GovernanceGateName,
  value: unknown,
): GateConfigInput {
  const baseDefault = DEFAULT_CONFIG.gates[gate];
  const normalizedBase = normalizeGateOverride(value);
  const providers: Record<string, GateOverrideInput> = {};

  if (isRecord(value) && isRecord(value.providers)) {
    for (const [provider, override] of Object.entries(value.providers)) {
      const providerName = provider.trim().toLowerCase();
      if (providerName) {
        providers[providerName] = normalizeGateOverride(override);
      }
    }
  }

  const normalized: GateConfigInput = {
    ...((normalizedBase.enabled ?? baseDefault.enabled) !== undefined
      ? { enabled: normalizedBase.enabled ?? baseDefault.enabled }
      : {}),
    ...((normalizedBase.enforcement ?? baseDefault.enforcement)
      ? {
          enforcement: normalizedBase.enforcement ?? baseDefault.enforcement,
        }
      : {}),
    ...(Object.keys(providers).length > 0 ? { providers } : {}),
  };

  return normalized;
}

function normalizeConfig(value: unknown): GovernanceConfig {
  if (!isRecord(value)) {
    return DEFAULT_CONFIG;
  }

  const rawGates = isRecord(value.gates) ? value.gates : {};

  return {
    version: typeof value.version === "number" ? value.version : 1,
    defaultProvider:
      typeof value.defaultProvider === "string" && value.defaultProvider.trim()
        ? value.defaultProvider.trim().toLowerCase()
        : DEFAULT_CONFIG.defaultProvider,
    gates: {
      MutationGate: normalizeGateConfig("MutationGate", rawGates.MutationGate),
      ToolFabric: normalizeGateConfig("ToolFabric", rawGates.ToolFabric),
    },
  };
}

export class UserGovernanceControl {
  private readonly projectDir: string;
  private readonly configPath: string;
  private readonly snapshotPath: string;
  private auditTrail: AuditTrail | null = null;

  constructor(projectDir: string) {
    this.projectDir = projectDir;
    this.configPath = join(projectDir, ...GOVERNANCE_CONFIG_PATH);
    this.snapshotPath = new StateResolver(projectDir).resolve(
      "governance-config.snapshot.json",
    );
  }

  loadConfig(): GovernanceConfig {
    if (!existsSync(this.configPath)) {
      return DEFAULT_CONFIG;
    }

    const raw = readFileSync(this.configPath, "utf8");
    const parsed = loadYaml(raw);
    const config = normalizeConfig(parsed);

    this.recordConfigChange(raw);

    return config;
  }

  getGateControl(
    gate: GovernanceGateName,
    provider?: string | null,
  ): ResolvedGateControl {
    const config = this.loadConfig();
    const resolvedProvider = normalizeProvider(
      provider ?? config.defaultProvider,
    );
    const gateConfig = config.gates[gate] ?? DEFAULT_CONFIG.gates[gate];
    const providerOverride = gateConfig.providers?.[resolvedProvider] ?? {};

    return {
      gate,
      provider: resolvedProvider,
      enabled: providerOverride.enabled ?? gateConfig.enabled ?? true,
      enforcement:
        providerOverride.enforcement ??
        gateConfig.enforcement ??
        DEFAULT_ENFORCEMENT,
      source: existsSync(this.configPath) ? "file" : "default",
    };
  }

  getStatus(provider?: string | null): GovernanceStatus {
    const resolvedProvider = normalizeProvider(provider);
    return {
      provider: resolvedProvider,
      configPath: this.configPath,
      source: existsSync(this.configPath) ? "file" : "default",
      gates: GOVERNANCE_GATES.map((gate) =>
        this.getGateControl(gate, resolvedProvider),
      ),
    };
  }

  recordGateBypass(entry: {
    readonly gate: GovernanceGateName;
    readonly provider?: string | null;
    readonly tool: string;
    readonly reason: string;
    readonly context?: Readonly<Record<string, unknown>>;
  }): void {
    const control = this.getGateControl(entry.gate, entry.provider);
    if (control.enabled) {
      return;
    }

    this.recordAudit({
      actor: "user-governance",
      action: "governance.gate.bypass",
      details: {
        resource: entry.gate,
        gate: entry.gate,
        tool: entry.tool,
        provider: control.provider,
        decision: "allow",
        risk_level: "medium",
        reason: entry.reason,
        configPath: this.configPath,
        ...entry.context,
      },
    });
  }

  private recordConfigChange(raw: string): void {
    const digest = createHash("sha256").update(raw, "utf8").digest("hex");
    const previous = this.readSnapshot();
    if (previous?.digest === digest) {
      return;
    }

    this.recordAudit({
      actor: "user-governance",
      action: "governance.config.changed",
      details: {
        resource: this.configPath,
        decision: "recorded",
        risk_level: "info",
        previousDigest: previous?.digest ?? null,
        currentDigest: digest,
      },
    });

    atomicWriteJson(this.snapshotPath, {
      digest,
      configPath: this.configPath,
    } satisfies GovernanceSnapshot);
  }

  private recordAudit(entry: Parameters<AuditTrail["record"]>[0]): void {
    try {
      this.auditTrail ??= AuditTrail.create({ projectDir: this.projectDir });
      this.auditTrail.record(entry);
    } catch {}
  }

  private readSnapshot(): GovernanceSnapshot | null {
    if (!existsSync(this.snapshotPath)) {
      return null;
    }

    try {
      const raw = readFileSync(this.snapshotPath, "utf8");
      return JSON.parse(raw) as GovernanceSnapshot;
    } catch {
      return null;
    }
  }
}

export function getUserGovernanceControl(
  projectDir: string,
): UserGovernanceControl {
  return new UserGovernanceControl(projectDir);
}

export function formatGovernanceStatus(status: GovernanceStatus): string {
  const lines = [
    `Governance status (${status.provider})`,
    `Config: ${status.configPath} [${status.source}]`,
    "",
    "Gate           Enabled  Enforcement",
    "-------------  -------  -----------",
  ];

  for (const gate of status.gates) {
    lines.push(
      `${gate.gate.padEnd(13)}  ${String(gate.enabled).padEnd(7)}  ${gate.enforcement}`,
    );
  }

  return lines.join("\n");
}

export function getDefaultGovernanceConfig(): GovernanceConfig {
  return DEFAULT_CONFIG;
}
