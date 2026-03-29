import { describe, expect, test } from "bun:test";
import { SyntheticProvider, WebSearch } from "./search.js";
import type { SearchProvider, SearchResult } from "./search.js";

const enabledDeps = { isEnabled: () => true };
const disabledDeps = { isEnabled: () => false };

describe("WebSearch", () => {
  test("create returns a WebSearch instance", () => {
    const ws = WebSearch.create(enabledDeps);
    expect(ws).toBeInstanceOf(WebSearch);
  });

  test("search returns empty when disabled", async () => {
    const ws = WebSearch.create(disabledDeps);
    ws.registerProvider(new SyntheticProvider());
    const { results } = await ws.search("test");
    expect(results).toEqual([]);
  });

  test("search returns empty when no providers registered", async () => {
    const ws = WebSearch.create(enabledDeps);
    const { results } = await ws.search("test");
    expect(results).toEqual([]);
  });

  test("search with synthetic provider returns structured results", async () => {
    const ws = WebSearch.create(enabledDeps);
    ws.registerProvider(new SyntheticProvider());
    const { results } = await ws.search("hello world");

    expect(results.length).toBeGreaterThan(0);
    const first = results[0];
    expect(first).toBeDefined();
    expect(typeof first?.title).toBe("string");
    expect(typeof first?.url).toBe("string");
    expect(typeof first?.snippet).toBe("string");
    expect(first?.source).toBe("synthetic");
    expect(first?.title).toContain("hello world");
  });

  test("search uses specified provider over default", async () => {
    const ws = WebSearch.create(enabledDeps);

    const mockProvider: SearchProvider = {
      name: "mock",
      search: async (query: string): Promise<SearchResult[]> => [
        { title: `Mock: ${query}`, url: "https://mock.com", snippet: "mock", source: "mock" },
      ],
    };

    ws.registerProvider(new SyntheticProvider());
    ws.registerProvider(mockProvider);

    const { results } = await ws.search("test", "mock");
    expect(results).toHaveLength(1);
    expect(results[0]?.source).toBe("mock");
  });

  test("registerProvider sets first as default", () => {
    const ws = WebSearch.create(enabledDeps);
    ws.registerProvider(new SyntheticProvider());
    expect(ws.getProviders()).toContain("synthetic");
  });

  test("unregisterProvider removes provider", () => {
    const ws = WebSearch.create(enabledDeps);
    ws.registerProvider(new SyntheticProvider());
    expect(ws.unregisterProvider("synthetic")).toBe(true);
    expect(ws.getProviders()).toEqual([]);
  });

  test("unregisterProvider returns false for unknown", () => {
    const ws = WebSearch.create(enabledDeps);
    expect(ws.unregisterProvider("nonexistent")).toBe(false);
  });

  test("search handles provider errors gracefully", async () => {
    const ws = WebSearch.create(enabledDeps);
    const failProvider: SearchProvider = {
      name: "fail",
      search: async () => { throw new Error("boom"); },
    };
    ws.registerProvider(failProvider);
    const { results } = await ws.search("test");
    expect(results).toEqual([]);
  });

  test("search with unknown provider returns empty", async () => {
    const ws = WebSearch.create(enabledDeps);
    ws.registerProvider(new SyntheticProvider());
    const { results } = await ws.search("test", "unknown-provider");
    expect(results).toEqual([]);
  });

  test("getProviders returns all registered names", () => {
    const ws = WebSearch.create(enabledDeps);
    ws.registerProvider(new SyntheticProvider());
    ws.registerProvider({ name: "other", search: async () => [] });
    expect(ws.getProviders()).toEqual(["synthetic", "other"]);
  });
});

describe("SyntheticProvider", () => {
  test("returns requested number of results", async () => {
    const provider = new SyntheticProvider();
    const results = await provider.search("test", 3);
    expect(results).toHaveLength(3);
  });

  test("caps at 5 results", async () => {
    const provider = new SyntheticProvider();
    const results = await provider.search("test", 100);
    expect(results).toHaveLength(5);
  });

  test("results have correct structure", async () => {
    const provider = new SyntheticProvider();
    const results = await provider.search("typescript");
    expect(results.length).toBeGreaterThan(0);
    for (const r of results) {
      expect(typeof r.title).toBe("string");
      expect(r.url).toContain("https://");
      expect(typeof r.snippet).toBe("string");
      expect(r.source).toBe("synthetic");
    }
  });
});
