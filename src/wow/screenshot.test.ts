import { describe, it, expect, mock } from "bun:test";
import { captureScreenshot, isScreenshotAvailable } from "./screenshot.js";

mock.module("playwright", () => {
  return {
    chromium: {
      launch: mock(() =>
        Promise.resolve({
          newPage: mock(() =>
            Promise.resolve({
              goto: mock(() => Promise.resolve()),
              screenshot: mock(() => Promise.resolve()),
            }),
          ),
          close: mock(() => Promise.resolve()),
        }),
      ),
    },
  };
});

describe("screenshot", () => {
  it("isScreenshotAvailable returns boolean", async () => {
    const available = await isScreenshotAvailable();
    expect(typeof available).toBe("boolean");
  });

  it("captureScreenshot generates correct file path format", async () => {
    const result = await captureScreenshot("http://example.com", "test-flow");

    expect(result.url).toBe("http://example.com");
    expect(result.flowName).toBe("test-flow");
    expect(result.filePath).toMatch(/\.omg\/evidence\/wow-test-flow-\d+\.png/);
    expect(typeof result.timestamp).toBe("number");
  });
});
