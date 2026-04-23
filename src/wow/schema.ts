export interface WowFlow {
  name: string;
  description: string;
  expectedArtifact: string;
  proofFloor: number;
  timeout: number;
  toolAllowlist: string[];
  deployable: boolean;
}

export function isWowFlow(v: unknown): v is WowFlow {
  if (typeof v !== "object" || v === null) return false;
  const f = v as Record<string, unknown>;
  return (
    typeof f.name === "string" &&
    typeof f.description === "string" &&
    typeof f.expectedArtifact === "string" &&
    typeof f.proofFloor === "number" &&
    typeof f.timeout === "number" &&
    Array.isArray(f.toolAllowlist) &&
    f.toolAllowlist.every((t) => typeof t === "string") &&
    typeof f.deployable === "boolean"
  );
}
