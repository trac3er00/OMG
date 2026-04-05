export interface SanitizeResult {
  readonly sanitized: string;
  readonly bidiRemoved: boolean;
  readonly invisibleRemoved: boolean;
  readonly homoglyphsNormalized: boolean;
}

const BIDI_CHARS = /[\u202A-\u202E\u2066-\u2069\u200F\u061C]/g;
const INVISIBLE_CHARS = /[\u200B-\u200D\uFEFF\u2028\u2029\u00AD]/g;
const NULL_BYTES = /\u0000/g;

export function sanitizeContent(content: string): SanitizeResult {
  const text = String(content ?? "");
  const normalized = text.normalize("NFC");
  const bidiRemoved = (normalized.match(BIDI_CHARS) ?? []).length > 0;
  const invisibleRemoved = (normalized.match(INVISIBLE_CHARS) ?? []).length > 0 || normalized.includes("\u0000");

  const sanitized = normalized
    .replace(BIDI_CHARS, "")
    .replace(INVISIBLE_CHARS, "")
    .replace(NULL_BYTES, "")
    .normalize("NFC");

  return {
    sanitized,
    bidiRemoved,
    invisibleRemoved,
    homoglyphsNormalized: sanitized !== text,
  };
}
