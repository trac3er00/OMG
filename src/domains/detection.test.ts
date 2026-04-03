import { describe, test, expect } from "bun:test";
import {
  SUPPORTED_DOMAINS,
  DomainDetectionResultSchema,
  detectDomain,
  type DetectionSignals,
} from "./detection.js";

const emptySignals: DetectionSignals = {
  dependencies: {},
  files: [],
  scripts: {},
};

describe("domains/detection", () => {
  test("SUPPORTED_DOMAINS includes 3 domains", () => {
    expect(SUPPORTED_DOMAINS.length).toBe(3);
    expect(SUPPORTED_DOMAINS).toContain("web_app");
    expect(SUPPORTED_DOMAINS).toContain("cli_tool");
    expect(SUPPORTED_DOMAINS).toContain("backend_api");
  });

  describe("detectDomain", () => {
    test("detects web_app from React dependency", () => {
      const signals: DetectionSignals = {
        dependencies: { react: "^18", "react-dom": "^18" },
        files: ["src/App.tsx"],
        scripts: { dev: "vite", build: "vite build" },
      };
      const result = detectDomain(signals);
      expect(result.primary_domain).toBe("web_app");
    });

    test("detects cli_tool from commander dependency", () => {
      const signals: DetectionSignals = {
        dependencies: { commander: "^11" },
        files: ["bin/cli.ts", "src/commands/deploy.ts"],
        scripts: { bin: "node dist/cli.js" },
      };
      const result = detectDomain(signals);
      expect(result.primary_domain).toBe("cli_tool");
    });

    test("detects backend_api from Dockerfile + openapi", () => {
      const signals: DetectionSignals = {
        dependencies: { express: "^4" },
        files: ["Dockerfile", "openapi.yaml", "routes/users.ts"],
        scripts: { start: "node server.js" },
      };
      const result = detectDomain(signals);
      expect(result.primary_domain).toBe("backend_api");
    });

    test("detects multiple domains (web + api)", () => {
      const signals: DetectionSignals = {
        dependencies: { react: "^18", express: "^4" },
        files: ["src/App.tsx", "Dockerfile", "routes/api.ts", "openapi.yaml"],
        scripts: {},
      };
      const result = detectDomain(signals);
      expect(result.all_domains.length).toBeGreaterThan(1);
      expect(result.all_domains).toContain("web_app");
      expect(result.all_domains).toContain("backend_api");
    });

    test("unknown for empty signals", () => {
      const result = detectDomain(emptySignals);
      expect(result.primary_domain).toBe("unknown");
    });

    test("confidence scores are 0-1", () => {
      const signals: DetectionSignals = {
        dependencies: { react: "^18" },
        files: [],
        scripts: {},
      };
      const result = detectDomain(signals);
      for (const score of Object.values(result.confidence_scores)) {
        expect(score).toBeGreaterThanOrEqual(0);
        expect(score).toBeLessThanOrEqual(1);
      }
    });

    test("result validates against schema", () => {
      const result = detectDomain(emptySignals);
      expect(DomainDetectionResultSchema.safeParse(result).success).toBe(true);
    });
  });
});
