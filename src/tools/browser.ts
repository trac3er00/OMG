export interface BrowserResult<T = unknown> {
  readonly success: boolean;
  readonly result: T | null;
  readonly error: string | null;
}

export interface BrowserSession {
  readonly sessionId: string;
  readonly currentUrl: string;
  readonly history: readonly string[];
  readonly screenshots: readonly string[];
}

export interface ToolCallSpec {
  readonly tool: string;
  readonly parameters: Readonly<Record<string, string>>;
}

export interface ConsentGrant {
  readonly action: string;
  readonly grantedAt: number;
}

export interface BrowserDeps {
  readonly isEnabled: () => boolean;
  readonly generateId: () => string;
}

const defaultDeps: BrowserDeps = {
  isEnabled: () => {
    const v = (typeof process !== "undefined" ? process.env["OMG_BROWSER_ENABLED"] : undefined) ?? "";
    return ["1", "true", "yes"].includes(v.toLowerCase());
  },
  generateId: () => Math.random().toString(36).slice(2, 14),
};

export class BrowserTool {
  private readonly deps: BrowserDeps;
  private sessionId: string;
  private currentUrl: string;
  private history: string[];
  private screenshotNames: string[];
  private readonly consents: Map<string, ConsentGrant>;

  private constructor(deps: BrowserDeps) {
    this.deps = deps;
    this.sessionId = deps.generateId();
    this.currentUrl = "";
    this.history = [];
    this.screenshotNames = [];
    this.consents = new Map();
  }

  static create(deps?: Partial<BrowserDeps>): BrowserTool {
    return new BrowserTool({ ...defaultDeps, ...deps });
  }

  requireConsent(action: string): void {
    this.consents.set(action, {
      action,
      grantedAt: Date.now(),
    });
  }

  hasConsent(action: string): boolean {
    return this.consents.has(action);
  }

  revokeConsent(action: string): void {
    this.consents.delete(action);
  }

  private guardEnabled(): BrowserResult | null {
    if (!this.deps.isEnabled()) {
      return {
        success: false,
        result: null,
        error: "Browser feature is disabled (OMG_BROWSER_ENABLED=false)",
      };
    }
    return null;
  }

  private guardConsent(action: string): BrowserResult | null {
    if (!this.hasConsent(action)) {
      return {
        success: false,
        result: null,
        error: `Consent required for action: ${action}. Call requireConsent("${action}") first.`,
      };
    }
    return null;
  }

  navigate(url: string): BrowserResult<ToolCallSpec> {
    const disabledErr = this.guardEnabled();
    if (disabledErr) return disabledErr as BrowserResult<ToolCallSpec>;

    const consentErr = this.guardConsent("navigate");
    if (consentErr) return consentErr as BrowserResult<ToolCallSpec>;

    if (!url || typeof url !== "string") {
      return { success: false, result: null, error: "URL must be a non-empty string" };
    }

    let normalised = url;
    if (!normalised.startsWith("http://") && !normalised.startsWith("https://")) {
      normalised = `https://${normalised}`;
    }

    const spec: ToolCallSpec = {
      tool: "mcp_puppeteer_puppeteer_navigate",
      parameters: { url: normalised },
    };

    this.currentUrl = normalised;
    this.history.push(normalised);

    return { success: true, result: spec, error: null };
  }

  click(selector: string): BrowserResult<ToolCallSpec> {
    const disabledErr = this.guardEnabled();
    if (disabledErr) return disabledErr as BrowserResult<ToolCallSpec>;

    const consentErr = this.guardConsent("click");
    if (consentErr) return consentErr as BrowserResult<ToolCallSpec>;

    if (!selector || typeof selector !== "string") {
      return { success: false, result: null, error: "Selector must be a non-empty string" };
    }

    const spec: ToolCallSpec = {
      tool: "mcp_puppeteer_puppeteer_click",
      parameters: { selector },
    };

    return { success: true, result: spec, error: null };
  }

  screenshot(name: string, selector?: string): BrowserResult<ToolCallSpec> {
    const disabledErr = this.guardEnabled();
    if (disabledErr) return disabledErr as BrowserResult<ToolCallSpec>;

    const consentErr = this.guardConsent("screenshot");
    if (consentErr) return consentErr as BrowserResult<ToolCallSpec>;

    if (!name || typeof name !== "string") {
      return { success: false, result: null, error: "Name must be a non-empty string" };
    }

    const params: Record<string, string> = { name };
    if (selector) params["selector"] = selector;

    const spec: ToolCallSpec = {
      tool: "mcp_puppeteer_puppeteer_screenshot",
      parameters: params,
    };

    this.screenshotNames.push(name);

    return { success: true, result: spec, error: null };
  }

  evaluate(script: string): BrowserResult<ToolCallSpec> {
    const disabledErr = this.guardEnabled();
    if (disabledErr) return disabledErr as BrowserResult<ToolCallSpec>;

    const consentErr = this.guardConsent("evaluate");
    if (consentErr) return consentErr as BrowserResult<ToolCallSpec>;

    if (!script || typeof script !== "string") {
      return { success: false, result: null, error: "Script must be a non-empty string" };
    }

    const spec: ToolCallSpec = {
      tool: "mcp_puppeteer_puppeteer_evaluate",
      parameters: { script },
    };

    return { success: true, result: spec, error: null };
  }

  getSession(): BrowserSession {
    return {
      sessionId: this.sessionId,
      currentUrl: this.currentUrl,
      history: [...this.history],
      screenshots: [...this.screenshotNames],
    };
  }

  resetSession(): void {
    this.currentUrl = "";
    this.history = [];
    this.screenshotNames = [];
  }
}
