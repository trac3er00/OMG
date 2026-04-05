import { KeyObject, createPrivateKey, createPublicKey, randomUUID, sign as nodeSign, verify as nodeVerify } from "node:crypto";

export type AuthRole = "admin" | "agent" | "readonly";
export type TokenType = "access" | "refresh";

const ROLE_RANK: Readonly<Record<AuthRole, number>> = {
  readonly: 0,
  agent: 1,
  admin: 2,
};

const DEFAULT_TTL_SECONDS = 15 * 60;
const REFRESH_TTL_SECONDS = 24 * 60 * 60;

interface JwtHeader {
  readonly alg: "EdDSA";
  readonly typ: "JWT";
}

export interface JwtPayload {
  readonly role: AuthRole;
  readonly sub?: string;
  readonly jti?: string;
  readonly iat?: number;
  readonly exp?: number;
  readonly tokenType?: TokenType;
  readonly [key: string]: unknown;
}

export interface JwtValidationResult {
  readonly valid: boolean;
  readonly payload?: JwtPayload;
  readonly error?: string;
}

export interface GenerateTokenOptions {
  readonly ttlSeconds?: number;
  readonly tokenType?: TokenType;
}

export interface RefreshTokenResult {
  readonly ok: boolean;
  readonly token?: string;
  readonly error?: string;
}

const revokedTokenIds = new Set<string>();

function toBase64Url(input: Buffer): string {
  return input.toString("base64url");
}

function fromBase64Url(input: string): Buffer {
  return Buffer.from(input, "base64url");
}

function toKeyObject(key: KeyObject | string | Buffer, kind: "private" | "public"): KeyObject {
  if (key instanceof KeyObject) {
    return key;
  }

  return kind === "private" ? createPrivateKey(key) : createPublicKey(key);
}

function isRole(value: unknown): value is AuthRole {
  return value === "admin" || value === "agent" || value === "readonly";
}

function normalizePayload(payload: JwtPayload, options: GenerateTokenOptions): JwtPayload {
  const nowSeconds = Math.floor(Date.now() / 1000);
  const ttlSeconds = options.ttlSeconds ?? DEFAULT_TTL_SECONDS;
  const issuedAt = typeof payload.iat === "number" ? payload.iat : nowSeconds;
  const expiresAt = typeof payload.exp === "number" ? payload.exp : issuedAt + ttlSeconds;

  return {
    ...payload,
    tokenType: payload.tokenType ?? options.tokenType ?? "access",
    jti: payload.jti ?? randomUUID(),
    iat: issuedAt,
    exp: expiresAt,
  };
}

function stripTemporalClaims(payload: JwtPayload): JwtPayload {
  const nextEntries = Object.entries(payload).filter(([key]) => key !== "jti" && key !== "iat" && key !== "exp");
  return Object.fromEntries(nextEntries) as JwtPayload;
}

export function generateToken(
  payload: JwtPayload,
  privateKey: KeyObject | string | Buffer,
  options: GenerateTokenOptions = {},
): string {
  if (!isRole(payload.role)) {
    throw new Error("payload.role must be one of: admin, agent, readonly");
  }

  const header: JwtHeader = { alg: "EdDSA", typ: "JWT" };
  const normalizedPayload = normalizePayload(payload, options);
  const encodedHeader = toBase64Url(Buffer.from(JSON.stringify(header), "utf8"));
  const encodedPayload = toBase64Url(Buffer.from(JSON.stringify(normalizedPayload), "utf8"));
  const signingInput = `${encodedHeader}.${encodedPayload}`;
  const signer = toKeyObject(privateKey, "private");
  const signature = nodeSign(null, Buffer.from(signingInput, "utf8"), signer);
  return `${signingInput}.${toBase64Url(signature)}`;
}

export function validateToken(token: string, publicKey: KeyObject | string | Buffer): JwtValidationResult {
  try {
    const [encodedHeader, encodedPayload, encodedSignature] = token.split(".");
    if (!encodedHeader || !encodedPayload || !encodedSignature) {
      return { valid: false, error: "Malformed JWT" };
    }

    const parsedHeader = JSON.parse(fromBase64Url(encodedHeader).toString("utf8")) as JwtHeader;
    if (parsedHeader.alg !== "EdDSA" || parsedHeader.typ !== "JWT") {
      return { valid: false, error: "Unsupported JWT header" };
    }

    const parsedPayload = JSON.parse(fromBase64Url(encodedPayload).toString("utf8")) as JwtPayload;
    if (!isRole(parsedPayload.role)) {
      return { valid: false, error: "Invalid role in payload" };
    }

    const verifier = toKeyObject(publicKey, "public");
    const signature = fromBase64Url(encodedSignature);
    const signingInput = `${encodedHeader}.${encodedPayload}`;
    const validSignature = nodeVerify(null, Buffer.from(signingInput, "utf8"), verifier, signature);
    if (!validSignature) {
      return { valid: false, error: "Invalid signature" };
    }

    const nowSeconds = Math.floor(Date.now() / 1000);
    if (typeof parsedPayload.exp === "number" && nowSeconds >= parsedPayload.exp) {
      return { valid: false, error: "Token expired" };
    }

    if (typeof parsedPayload.jti === "string" && revokedTokenIds.has(parsedPayload.jti)) {
      return { valid: false, error: "Token revoked" };
    }

    return { valid: true, payload: parsedPayload };
  } catch {
    return { valid: false, error: "Token validation failed" };
  }
}

export function hasRequiredRole(payload: JwtPayload, requiredRole: AuthRole): boolean {
  const current = ROLE_RANK[payload.role];
  const required = ROLE_RANK[requiredRole];
  return current >= required;
}

export function revokeToken(token: string): boolean {
  const pieces = token.split(".");
  if (pieces.length !== 3) {
    return false;
  }

  try {
    const payload = JSON.parse(fromBase64Url(pieces[1] ?? "").toString("utf8")) as JwtPayload;
    if (typeof payload.jti !== "string" || payload.jti.length === 0) {
      return false;
    }
    revokedTokenIds.add(payload.jti);
    return true;
  } catch {
    return false;
  }
}

export function revokeTokenId(tokenId: string): void {
  revokedTokenIds.add(tokenId);
}

export function refreshToken(
  token: string,
  privateKey: KeyObject | string | Buffer,
  publicKey: KeyObject | string | Buffer,
): RefreshTokenResult {
  const validation = validateToken(token, publicKey);
  if (!validation.valid || !validation.payload) {
    return { ok: false, error: validation.error ?? "Unable to refresh invalid token" };
  }

  if (validation.payload.tokenType === "refresh") {
    return { ok: false, error: "Refresh token cannot be refreshed" };
  }

  const revoked = revokeToken(token);
  if (!revoked) {
    return { ok: false, error: "Failed to revoke current token" };
  }

  const baseClaims = stripTemporalClaims(validation.payload);
  const nextToken = generateToken({ ...baseClaims, tokenType: "refresh" }, privateKey, {
    ttlSeconds: REFRESH_TTL_SECONDS,
    tokenType: "refresh",
  });

  return { ok: true, token: nextToken };
}

export function clearRevocations(): void {
  revokedTokenIds.clear();
}
