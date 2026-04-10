import { describe, test, expect } from "bun:test";
import {
  detectPlatform,
  checkPlatformCompat,
  type Platform,
} from "./compat.js";

describe("platform/compat", () => {
  test("platform-detected", () => {
    const platform = detectPlatform();
    const valid: Platform[] = ["linux", "darwin", "win32", "unknown"];
    expect(valid).toContain(platform);
  });

  test("compat-result", () => {
    const result = checkPlatformCompat();
    expect(result).toHaveProperty("platform");
    expect(result).toHaveProperty("nodeVersion");
    expect(result).toHaveProperty("pathSeparator");
    expect(result).toHaveProperty("homeDir");
    expect(result).toHaveProperty("supported");
  });

  test("node-version", () => {
    const result = checkPlatformCompat();
    expect(typeof result.nodeVersion).toBe("string");
    expect(result.nodeVersion.length).toBeGreaterThan(0);
    expect(result.nodeVersion).toStartWith("v");
  });

  test("supported", () => {
    const result = checkPlatformCompat();
    if (
      result.platform === "linux" ||
      result.platform === "darwin" ||
      result.platform === "win32"
    ) {
      expect(result.supported).toBe(true);
    }
  });

  test("path-separator-matches-platform", () => {
    const result = checkPlatformCompat();
    if (result.platform === "win32") {
      expect(result.pathSeparator).toBe("\\");
    } else {
      expect(result.pathSeparator).toBe("/");
    }
  });

  test("homeDir-is-non-empty", () => {
    const result = checkPlatformCompat();
    expect(result.homeDir.length).toBeGreaterThan(0);
  });
});
