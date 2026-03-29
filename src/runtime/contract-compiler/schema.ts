import type { HostType } from "../../types/config.js";

export type ContractHost = Extract<HostType, "claude" | "codex" | "gemini" | "kimi">;

export interface ContractTool {
  readonly description: string;
  readonly hosts: readonly ContractHost[];
}

export interface ContractSchema {
  readonly version: string;
  readonly capabilities: readonly string[];
  readonly hosts: readonly ContractHost[];
  readonly tools: Readonly<Record<string, ContractTool>>;
}

const SUPPORTED_HOSTS: readonly ContractHost[] = ["claude", "codex", "gemini", "kimi"];

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isContractHost(value: string): value is ContractHost {
  return SUPPORTED_HOSTS.includes(value as ContractHost);
}

function validateTools(tools: unknown, errors: string[]): void {
  if (!isObjectRecord(tools)) {
    errors.push("tools must be an object map");
    return;
  }

  for (const [toolName, toolValue] of Object.entries(tools)) {
    if (!isObjectRecord(toolValue)) {
      errors.push(`tools.${toolName} must be an object`);
      continue;
    }

    const description = toolValue.description;
    if (typeof description !== "string" || description.trim().length === 0) {
      errors.push(`tools.${toolName}.description must be a non-empty string`);
    }

    const hosts = toolValue.hosts;
    if (!Array.isArray(hosts) || hosts.length === 0) {
      errors.push(`tools.${toolName}.hosts must be a non-empty array`);
      continue;
    }

    for (const host of hosts) {
      if (typeof host !== "string" || !isContractHost(host)) {
        errors.push(`tools.${toolName}.hosts contains unsupported host '${String(host)}'`);
      }
    }
  }
}

export function validateSchema(schema: unknown): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (!isObjectRecord(schema)) {
    return { valid: false, errors: ["schema must be an object"] };
  }

  if (typeof schema.version !== "string" || schema.version.trim().length === 0) {
    errors.push("version must be a non-empty string");
  }

  if (!Array.isArray(schema.capabilities) || schema.capabilities.length === 0) {
    errors.push("capabilities must be a non-empty array");
  } else if (!schema.capabilities.every((capability) => typeof capability === "string" && capability.trim().length > 0)) {
    errors.push("capabilities must contain non-empty strings only");
  }

  if (!Array.isArray(schema.hosts) || schema.hosts.length === 0) {
    errors.push("hosts must be a non-empty array");
  } else {
    for (const host of schema.hosts) {
      if (typeof host !== "string" || !isContractHost(host)) {
        errors.push(`unsupported host '${String(host)}'`);
      }
    }
  }

  validateTools(schema.tools, errors);

  return { valid: errors.length === 0, errors };
}
