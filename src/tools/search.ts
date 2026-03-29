export interface SearchResult {
  readonly title: string;
  readonly url: string;
  readonly snippet: string;
  readonly source: string;
}

export interface SearchProvider {
  readonly name: string;
  search(query: string, maxResults?: number): Promise<SearchResult[]>;
}

export interface SearchDeps {
  readonly isEnabled: () => boolean;
}

const defaultDeps: SearchDeps = {
  isEnabled: () => {
    const v = (typeof process !== "undefined" ? process.env["OMG_WEB_SEARCH_ENABLED"] : undefined) ?? "";
    return ["1", "true", "yes"].includes(v.toLowerCase());
  },
};

export class SyntheticProvider implements SearchProvider {
  readonly name = "synthetic";

  async search(query: string, maxResults = 5): Promise<SearchResult[]> {
    const results: SearchResult[] = [];
    const count = Math.min(maxResults, 5);
    for (let i = 0; i < count; i++) {
      results.push({
        title: `Result ${String(i + 1)} for "${query}"`,
        url: `https://example.com/search?q=${encodeURIComponent(query)}&p=${String(i + 1)}`,
        snippet: `This is a synthetic result snippet for query "${query}", item ${String(i + 1)}.`,
        source: "synthetic",
      });
    }
    return results;
  }
}

export class BraveProvider implements SearchProvider {
  readonly name = "brave";
  private readonly apiKey: string;

  constructor(apiKey: string) {
    this.apiKey = apiKey;
  }

  async search(query: string, maxResults = 10): Promise<SearchResult[]> {
    if (!this.apiKey) return [];

    const url = `https://api.search.brave.com/res/v1/web/search?q=${encodeURIComponent(query)}&count=${String(maxResults)}`;

    const resp = await fetch(url, {
      headers: {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": this.apiKey,
      },
    });

    if (!resp.ok) return [];

    const data = await resp.json() as { web?: { results?: Array<{ title?: string; url?: string; description?: string }> } };
    const webResults = data.web?.results ?? [];

    return webResults.map((r) => ({
      title: r.title ?? "",
      url: r.url ?? "",
      snippet: r.description ?? "",
      source: "brave",
    }));
  }
}

export class ExaProvider implements SearchProvider {
  readonly name = "exa";
  private readonly apiKey: string;

  constructor(apiKey: string) {
    this.apiKey = apiKey;
  }

  async search(query: string, maxResults = 10): Promise<SearchResult[]> {
    if (!this.apiKey) return [];

    const resp = await fetch("https://api.exa.ai/search", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": this.apiKey,
      },
      body: JSON.stringify({
        query,
        numResults: maxResults,
        useAutoprompt: true,
      }),
    });

    if (!resp.ok) return [];

    const data = await resp.json() as { results?: Array<{ title?: string; url?: string; text?: string }> };
    const results = data.results ?? [];

    return results.map((r) => ({
      title: r.title ?? "",
      url: r.url ?? "",
      snippet: (r.text ?? "").slice(0, 300),
      source: "exa",
    }));
  }
}

export class WebSearch {
  private readonly deps: SearchDeps;
  private readonly providers: Map<string, SearchProvider>;
  private defaultProvider: string | null;

  private constructor(deps: SearchDeps) {
    this.deps = deps;
    this.providers = new Map();
    this.defaultProvider = null;
  }

  static create(deps?: Partial<SearchDeps>): WebSearch {
    return new WebSearch({ ...defaultDeps, ...deps });
  }

  registerProvider(provider: SearchProvider): void {
    this.providers.set(provider.name, provider);
    if (this.defaultProvider === null) {
      this.defaultProvider = provider.name;
    }
  }

  unregisterProvider(name: string): boolean {
    const removed = this.providers.delete(name);
    if (removed && this.defaultProvider === name) {
      const first = this.providers.keys().next();
      this.defaultProvider = first.done ? null : first.value;
    }
    return removed;
  }

  getProviders(): string[] {
    return [...this.providers.keys()];
  }

  async search(query: string, providerName?: string): Promise<{ results: SearchResult[] }> {
    if (!this.deps.isEnabled()) {
      return { results: [] };
    }

    const name = providerName ?? this.defaultProvider;
    if (!name) return { results: [] };

    const provider = this.providers.get(name);
    if (!provider) return { results: [] };

    try {
      const results = await provider.search(query);
      return { results };
    } catch {
      return { results: [] };
    }
  }
}
