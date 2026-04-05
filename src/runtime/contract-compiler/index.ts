import type { ContractHost, ContractSchema } from "./schema.js";
import { emitForHost, type HostArtifact } from "./host-emit.js";
import { validateContract } from "./validation.js";

export interface CompileContractResult {
  readonly valid: boolean;
  readonly blockers: readonly string[];
  readonly artifacts: readonly HostArtifact[];
}

export function compileContract(schema: ContractSchema, hosts: readonly ContractHost[] = schema.hosts): CompileContractResult {
  const validation = validateContract(schema);
  if (!validation.valid) {
    return {
      valid: false,
      blockers: validation.blockers,
      artifacts: [],
    };
  }

  const artifacts = hosts.map((host) => emitForHost(schema, host));
  return {
    valid: true,
    blockers: [],
    artifacts,
  };
}

export type { ContractHost, ContractSchema, ContractTool } from "./schema.js";
export { validateSchema } from "./schema.js";
export { emitForHost } from "./host-emit.js";
export { validateContract } from "./validation.js";
