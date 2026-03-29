import { describe, expect, test } from "bun:test";
import { BrowserTool } from "./browser.js";

const enabledDeps = { isEnabled: () => true, generateId: () => "test-session-1" };
const disabledDeps = { isEnabled: () => false, generateId: () => "test-session-2" };

describe("BrowserTool", () => {
  test("create returns a BrowserTool instance", () => {
    const tool = BrowserTool.create(enabledDeps);
    expect(tool).toBeInstanceOf(BrowserTool);
  });

  test("navigate without consent is blocked", () => {
    const tool = BrowserTool.create(enabledDeps);
    const result = tool.navigate("https://example.com");
    expect(result.success).toBe(false);
    expect(result.error).toContain("Consent required");
  });

  test("navigate with consent produces tool-call spec", () => {
    const tool = BrowserTool.create(enabledDeps);
    tool.requireConsent("navigate");
    const result = tool.navigate("https://example.com");
    expect(result.success).toBe(true);
    expect(result.result?.tool).toBe("mcp_puppeteer_puppeteer_navigate");
    expect(result.result?.parameters.url).toBe("https://example.com");
  });

  test("navigate auto-prepends https:// when scheme missing", () => {
    const tool = BrowserTool.create(enabledDeps);
    tool.requireConsent("navigate");
    const result = tool.navigate("example.com");
    expect(result.success).toBe(true);
    expect(result.result?.parameters.url).toBe("https://example.com");
  });

  test("click without consent is blocked", () => {
    const tool = BrowserTool.create(enabledDeps);
    const result = tool.click("#btn");
    expect(result.success).toBe(false);
    expect(result.error).toContain("Consent required");
  });

  test("click with consent produces spec", () => {
    const tool = BrowserTool.create(enabledDeps);
    tool.requireConsent("click");
    const result = tool.click("#btn");
    expect(result.success).toBe(true);
    expect(result.result?.tool).toBe("mcp_puppeteer_puppeteer_click");
    expect(result.result?.parameters.selector).toBe("#btn");
  });

  test("screenshot without consent is blocked", () => {
    const tool = BrowserTool.create(enabledDeps);
    const result = tool.screenshot("snap");
    expect(result.success).toBe(false);
    expect(result.error).toContain("Consent required");
  });

  test("screenshot with consent produces spec", () => {
    const tool = BrowserTool.create(enabledDeps);
    tool.requireConsent("screenshot");
    const result = tool.screenshot("snap", ".hero");
    expect(result.success).toBe(true);
    expect(result.result?.parameters.name).toBe("snap");
    expect(result.result?.parameters.selector).toBe(".hero");
  });

  test("evaluate without consent is blocked", () => {
    const tool = BrowserTool.create(enabledDeps);
    const result = tool.evaluate("document.title");
    expect(result.success).toBe(false);
    expect(result.error).toContain("Consent required");
  });

  test("evaluate with consent produces spec", () => {
    const tool = BrowserTool.create(enabledDeps);
    tool.requireConsent("evaluate");
    const result = tool.evaluate("document.title");
    expect(result.success).toBe(true);
    expect(result.result?.parameters.script).toBe("document.title");
  });

  test("all operations blocked when feature disabled", () => {
    const tool = BrowserTool.create(disabledDeps);
    tool.requireConsent("navigate");
    tool.requireConsent("click");
    tool.requireConsent("screenshot");
    tool.requireConsent("evaluate");

    expect(tool.navigate("https://x.com").success).toBe(false);
    expect(tool.click("#a").success).toBe(false);
    expect(tool.screenshot("s").success).toBe(false);
    expect(tool.evaluate("1+1").success).toBe(false);
  });

  test("revokeConsent removes previously granted consent", () => {
    const tool = BrowserTool.create(enabledDeps);
    tool.requireConsent("navigate");
    expect(tool.hasConsent("navigate")).toBe(true);
    tool.revokeConsent("navigate");
    expect(tool.hasConsent("navigate")).toBe(false);
    expect(tool.navigate("https://x.com").success).toBe(false);
  });

  test("getSession tracks navigation history and screenshots", () => {
    const tool = BrowserTool.create(enabledDeps);
    tool.requireConsent("navigate");
    tool.requireConsent("screenshot");

    tool.navigate("https://a.com");
    tool.navigate("https://b.com");
    tool.screenshot("shot1");

    const session = tool.getSession();
    expect(session.sessionId).toBe("test-session-1");
    expect(session.currentUrl).toBe("https://b.com");
    expect(session.history).toEqual(["https://a.com", "https://b.com"]);
    expect(session.screenshots).toEqual(["shot1"]);
  });

  test("resetSession clears history", () => {
    const tool = BrowserTool.create(enabledDeps);
    tool.requireConsent("navigate");
    tool.navigate("https://a.com");
    tool.resetSession();

    const session = tool.getSession();
    expect(session.currentUrl).toBe("");
    expect(session.history).toEqual([]);
    expect(session.screenshots).toEqual([]);
  });
});
