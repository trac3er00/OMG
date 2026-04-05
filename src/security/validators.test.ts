import { describe, test, expect } from "bun:test";
import {
  validateOpaqueIdentifier,
  ensurePathWithinDir,
  validateServerName,
  validateServerUrl,
  sanitizeRunId,
  tomlQuoteString,
} from "./validators.js";

describe("validateOpaqueIdentifier", () => {
  test("accepts valid ASCII identifier", () => {
    expect(validateOpaqueIdentifier("my-server.v1", "test")).toBe("my-server.v1");
  });

  test("accepts underscore", () => {
    expect(validateOpaqueIdentifier("my_server", "test")).toBe("my_server");
  });

  test("trims whitespace", () => {
    expect(validateOpaqueIdentifier("  hello  ", "test")).toBe("hello");
  });

  test("applies NFC Unicode normalization before validation", () => {
    const nfd = "cafe\u0301";
    expect(() => validateOpaqueIdentifier(nfd, "test")).toThrow();
  });

  test("rejects path traversal", () => {
    expect(() => validateOpaqueIdentifier("../../../etc/passwd", "test")).toThrow();
  });

  test("rejects empty string", () => {
    expect(() => validateOpaqueIdentifier("", "test")).toThrow();
  });

  test("rejects string over max length", () => {
    expect(() => validateOpaqueIdentifier("a".repeat(200), "test")).toThrow();
  });

  test("rejects special chars", () => {
    expect(() => validateOpaqueIdentifier("hello world", "test")).toThrow();
    expect(() => validateOpaqueIdentifier("hello@world", "test")).toThrow();
    expect(() => validateOpaqueIdentifier("hello/world", "test")).toThrow();
  });

  test("throws with field name in error message", () => {
    try {
      validateOpaqueIdentifier("", "my_field");
    } catch (e) {
      expect((e as Error).message).toContain("my_field");
    }
  });
});

describe("ensurePathWithinDir", () => {
  test("accepts path within base dir", () => {
    const result = ensurePathWithinDir("/base/dir", "/base/dir/subdir/file.txt");
    expect(result).toBe("/base/dir/subdir/file.txt");
  });

  test("accepts base dir itself", () => {
    expect(ensurePathWithinDir("/base/dir", "/base/dir")).toBe("/base/dir");
  });

  test("rejects path traversal via ..", () => {
    expect(() => ensurePathWithinDir("/base/dir", "/base/dir/../other/file")).toThrow();
  });

  test("rejects completely different path", () => {
    expect(() => ensurePathWithinDir("/base/dir", "/etc/passwd")).toThrow();
  });

  test("rejects sibling directory", () => {
    expect(() => ensurePathWithinDir("/base/dir", "/base/other")).toThrow();
  });

  test("resolves dot segments before checking", () => {
    const result = ensurePathWithinDir("/base/dir", "/base/dir/./subdir");
    expect(result).toBe("/base/dir/subdir");
  });
});

describe("validateServerName", () => {
  test("accepts valid server name", () => {
    expect(validateServerName("omg-control")).toBe("omg-control");
  });

  test("trims whitespace", () => {
    expect(validateServerName("  server  ")).toBe("server");
  });

  test("rejects empty", () => {
    expect(() => validateServerName("")).toThrow();
  });

  test("rejects too long", () => {
    expect(() => validateServerName("a".repeat(200))).toThrow();
  });
});

describe("validateServerUrl", () => {
  test("accepts https URL", () => {
    expect(validateServerUrl("https://example.com")).toBe("https://example.com");
  });

  test("accepts http URL", () => {
    expect(validateServerUrl("http://localhost:8787")).toBe("http://localhost:8787");
  });

  test("rejects file protocol", () => {
    expect(() => validateServerUrl("file:///etc/passwd")).toThrow();
  });

  test("rejects javascript protocol", () => {
    expect(() => validateServerUrl("javascript:alert(1)")).toThrow();
  });

  test("rejects empty", () => {
    expect(() => validateServerUrl("")).toThrow();
  });
});

describe("sanitizeRunId", () => {
  test("preserves alphanumeric and hyphens", () => {
    expect(sanitizeRunId("run-20240101-abcdef")).toBe("run-20240101-abcdef");
  });

  test("replaces unsafe chars with hyphens", () => {
    const result = sanitizeRunId("run/with/slashes");
    expect(result).not.toContain("/");
  });

  test("removes .. sequences", () => {
    const result = sanitizeRunId("run/../traversal");
    expect(result).not.toContain("..");
  });

  test("trims whitespace", () => {
    expect(sanitizeRunId("  run-id  ").trim()).toBe(sanitizeRunId("run-id"));
  });

  test("enforces max length", () => {
    const long = "a".repeat(300);
    const result = sanitizeRunId(long);
    expect(result.length).toBeLessThanOrEqual(128);
  });

  test("handles empty string", () => {
    const result = sanitizeRunId("");
    expect(typeof result).toBe("string");
  });
});

describe("tomlQuoteString", () => {
  test("wraps string in double quotes", () => {
    expect(tomlQuoteString("hello")).toBe('"hello"');
  });

  test("escapes backslashes", () => {
    expect(tomlQuoteString("a\\b")).toBe('"a\\\\b"');
  });

  test("escapes double quotes", () => {
    expect(tomlQuoteString('say "hello"')).toBe('"say \\\"hello\\\""');
  });

  test("handles empty string", () => {
    expect(tomlQuoteString("")).toBe('""');
  });
});
