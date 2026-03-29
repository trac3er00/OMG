import { CANONICAL_VERSION } from "../canonical-taxonomy.js";
import type { ContractHost, ContractSchema } from "./schema.js";
import { validateSchema } from "./schema.js";

const REQUIRED_BASE_CAPABILITIES: readonly string[] = ["compilation_targets"];

const REQUIRED_HOST_CAPABILITIES: Readonly<Record<ContractHost, readonly string[]>> = {
  claude: ["hooks", "subagents", "skills"],
  codex: ["skills", "agents_fragments", "rules", "automations"],
  gemini: ["mcp", "skills", "automations"],
  kimi: ["mcp", "skills", "automations"],
};

function majorVersion(version: string): number | null {
  const major = Number.parseInt(version.split(".")[0] ?? "", 10);
  return Number.isNaN(major) ? null : major;
}

export function validateContract(contract: ContractSchema): { valid: boolean; blockers: string[] } {
  const blockers: string[] = [];
  const schemaValidation = validateSchema(contract);
  if (!schemaValidation.valid) {
    return { valid: false, blockers: schemaValidation.errors };
  }

  for (const requiredCapability of REQUIRED_BASE_CAPABILITIES) {
    if (!contract.capabilities.includes(requiredCapability)) {
      blockers.push(`missing required capability: ${requiredCapability}`);
    }
  }

  for (const host of contract.hosts) {
    const requiredForHost = REQUIRED_HOST_CAPABILITIES[host];
    for (const capability of requiredForHost) {
      if (!contract.capabilities.includes(capability)) {
        blockers.push(`host '${host}' requires capability '${capability}'`);
      }
    }
  }

  const contractMajor = majorVersion(contract.version);
  const runtimeMajor = majorVersion(CANONICAL_VERSION);
  if (contractMajor === null) {
    blockers.push(`invalid contract version format: '${contract.version}'`);
  } else if (runtimeMajor === null || contractMajor !== runtimeMajor) {
    blockers.push(`version compatibility failure: contract ${contract.version} != runtime ${CANONICAL_VERSION}`);
  }

  return {
    valid: blockers.length === 0,
    blockers,
  };
}
