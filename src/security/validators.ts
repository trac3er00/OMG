import { resolve } from "node:path";

const OPAQUE_IDENTIFIER_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const SERVER_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9_-]*$/;
const ALLOWED_URL_PROTOCOLS = new Set(["http:", "https:"]);

function normalizeIdentifier(value: string): string {
  return value.normalize("NFC").trim();
}

export function validateOpaqueIdentifier(
  value: string,
  fieldName: string,
  maxLength = 64,
): string {
  if (typeof value !== "string") {
    throw new Error(`Invalid ${fieldName}: must be a string`);
  }

  const normalized = normalizeIdentifier(value);
  if (!normalized) {
    throw new Error(`Invalid ${fieldName}: value is required`);
  }
  if (normalized.length > maxLength) {
    throw new Error(`Invalid ${fieldName}: exceeds ${maxLength} characters`);
  }
  if (normalized.includes("..") || !OPAQUE_IDENTIFIER_RE.test(normalized)) {
    throw new Error(
      `Invalid ${fieldName}: use only ASCII letters, numbers, dot, underscore, and dash`,
    );
  }
  return normalized;
}

export function ensurePathWithinDir(baseDir: string, candidatePath: string): string {
  const base = resolve(baseDir);
  const candidate = resolve(candidatePath);
  if (candidate !== base && !candidate.startsWith(`${base}/`)) {
    throw new Error(`Resolved path escapes base directory: ${candidate}`);
  }
  return candidate;
}

export function validateServerName(serverName: string, maxLength = 64): string {
  if (typeof serverName !== "string") {
    throw new Error("Invalid server_name: must be a string");
  }

  const normalized = normalizeIdentifier(serverName);
  if (!normalized) {
    throw new Error("Invalid server_name: value is required");
  }
  if (normalized.length > maxLength) {
    throw new Error(`Invalid server_name: exceeds ${maxLength} characters`);
  }
  if (!SERVER_NAME_RE.test(normalized)) {
    throw new Error("Invalid server_name: use only ASCII letters, numbers, underscore, and dash");
  }
  return normalized;
}

export function validateServerUrl(serverUrl: string): string {
  if (typeof serverUrl !== "string") {
    throw new Error("Invalid server_url: must be a string");
  }

  const normalized = serverUrl.trim();
  if (!normalized) {
    throw new Error("Invalid server_url: value is required");
  }
  if (normalized.includes("\n") || normalized.includes("\r")) {
    throw new Error("Invalid server_url: newline characters are not allowed");
  }

  let parsed: URL;
  try {
    parsed = new URL(normalized);
  } catch {
    throw new Error("Invalid server_url: must be an http or https URL");
  }

  if (!ALLOWED_URL_PROTOCOLS.has(parsed.protocol) || !parsed.host) {
    throw new Error("Invalid server_url: must be an http or https URL");
  }
  return normalized;
}

export function sanitizeRunId(value: string, maxLength = 128): string {
  const cleaned = String(value)
    .trim()
    .normalize("NFC")
    .replace(/[^A-Za-z0-9._-]+/g, "-")
    .replace(/\.\./g, "")
    .replace(/-{2,}/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, maxLength);

  return cleaned || "unknown";
}

export function tomlQuoteString(value: string): string {
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}
