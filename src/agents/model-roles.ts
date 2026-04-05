import { existsSync, readFileSync } from "node:fs";
import { isAbsolute, resolve, join } from "node:path";
import { load as loadYaml } from "js-yaml";

export interface ModelRole {
  model: string;
  temperature: number;
  description?: string;
}

type RoleMap = Record<string, ModelRole>;

const DEFAULT_ROLES_PATH = join(import.meta.dir, "../../agents/_model_roles.yaml");

const BUILTIN_ROLES: RoleMap = {
  default: { model: "claude-opus-4-5", temperature: 1 },
  smol: { model: "claude-haiku-4-5", temperature: 0.7 },
  slow: { model: "claude-opus-4-5", temperature: 0.5 },
  plan: { model: "claude-sonnet-4-5", temperature: 0.8 },
  commit: { model: "claude-haiku-4-5", temperature: 0.3 },
};

const roleCache = new Map<string, RoleMap>();

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function resolveRolePath(path?: string): string {
  if (!path) return DEFAULT_ROLES_PATH;
  return isAbsolute(path) ? path : resolve(process.cwd(), path);
}

function parseRole(_name: string, value: unknown): ModelRole | undefined {
  if (!isRecord(value)) return undefined;
  const model = value.model;
  const temperature = value.temperature;
  if (typeof model !== "string" || typeof temperature !== "number") return undefined;

  const role: ModelRole = { model, temperature };
  if (typeof value.description === "string" && value.description.length > 0) {
    role.description = value.description;
  }

  return role;
}

function parseRolesDocument(document: unknown): RoleMap {
  const root = isRecord(document) && isRecord(document.roles) ? document.roles : document;
  if (!isRecord(root)) return { ...BUILTIN_ROLES };

  const roles: RoleMap = {};
  for (const [name, value] of Object.entries(root)) {
    const role = parseRole(name, value);
    if (role) roles[name] = role;
  }

  return Object.keys(roles).length > 0 ? roles : { ...BUILTIN_ROLES };
}

export function loadModelRoles(path?: string): RoleMap {
  const resolved = resolveRolePath(path);
  if (roleCache.has(resolved)) return roleCache.get(resolved)!;

  if (!existsSync(resolved)) {
    const fallback = { ...BUILTIN_ROLES };
    roleCache.set(resolved, fallback);
    return fallback;
  }

  const raw = readFileSync(resolved, "utf8");
  const parsed = loadYaml(raw);
  const roles = parseRolesDocument(parsed);
  roleCache.set(resolved, roles);
  return roles;
}

export function getRole(name: string): ModelRole {
  const roles = loadModelRoles();
  return roles[name] ?? roles.default ?? BUILTIN_ROLES.default;
}
