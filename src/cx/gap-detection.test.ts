import { describe, expect, test } from "bun:test";
import { GapDetector } from "./gap-detection.js";
import type { ProjectScan } from "./gap-detection.js";

function makeScan(partial: Partial<ProjectScan> = {}): ProjectScan {
  return {
    files: [],
    directories: [],
    dependencies: [],
    hasPackageJson: true,
    ...partial,
  };
}

describe("GapDetector", () => {
  const detector = new GapDetector();

  describe("security: authentication missing", () => {
    test("detects missing auth when routes and controllers exist without auth layer", () => {
      const scan = makeScan({
        files: ["src/users.controller.ts", "src/orders.controller.ts"],
        directories: ["src/routes", "src/controllers", "src/models", "src/db"],
        dependencies: ["express", "pg", "prisma"],
      });

      const gaps = detector.detect(scan);

      const authGap = gaps.find(
        (g) =>
          g.category === "security" && g.title === "Authentication missing",
      );
      expect(authGap).toBeDefined();
      expect(authGap!.severity).toBe("critical");
      expect(authGap!.trigger).toContain("Routes/controllers");
    });

    test("does not flag auth gap when auth files exist", () => {
      const scan = makeScan({
        files: ["src/routes/users.ts", "src/middleware/auth.ts"],
        directories: ["src/routes", "src/auth"],
        dependencies: ["express", "jsonwebtoken"],
      });

      const gaps = detector.detect(scan);
      const authGap = gaps.find(
        (g) =>
          g.category === "security" && g.title === "Authentication missing",
      );
      expect(authGap).toBeUndefined();
    });

    test("does not flag auth gap when auth dependency exists", () => {
      const scan = makeScan({
        files: ["src/routes/index.ts"],
        directories: ["src/routes"],
        dependencies: ["express", "passport"],
      });

      const gaps = detector.detect(scan);
      const authGap = gaps.find(
        (g) =>
          g.category === "security" && g.title === "Authentication missing",
      );
      expect(authGap).toBeUndefined();
    });
  });

  describe("reliability: rate limiting missing", () => {
    test("detects missing rate limiting when API endpoints exist", () => {
      const scan = makeScan({
        files: ["src/api/users.ts", "src/api/products.ts"],
        directories: ["src/api", "src/handlers"],
        dependencies: ["express", "cors"],
      });

      const gaps = detector.detect(scan);

      const rateLimitGap = gaps.find(
        (g) =>
          g.category === "reliability" && g.title === "Rate limiting missing",
      );
      expect(rateLimitGap).toBeDefined();
      expect(rateLimitGap!.severity).toBe("high");
      expect(rateLimitGap!.trigger).toContain("rate limiting");
    });

    test("does not flag rate limiting when throttle dependency exists", () => {
      const scan = makeScan({
        files: ["src/routes/index.ts"],
        directories: ["src/routes"],
        dependencies: ["express", "express-rate-limit"],
      });

      const gaps = detector.detect(scan);
      const rateLimitGap = gaps.find(
        (g) =>
          g.category === "reliability" && g.title === "Rate limiting missing",
      );
      expect(rateLimitGap).toBeUndefined();
    });
  });

  describe("output limits", () => {
    test("returns at most 5 suggestions", () => {
      // given: project with many gaps (routes, no auth, no rate limit,
      //   no error handler, no tests, no deploy, no monitoring, no docs)
      const scan = makeScan({
        files: [
          "src/routes/users.ts",
          "src/index.ts",
          "src/db/connection.ts",
          "src/components/App.tsx",
        ],
        directories: [
          "src/routes",
          "src/controllers",
          "src/models",
          "src/db",
          "src/components",
        ],
        dependencies: ["express", "react", "pg"],
      });

      const gaps = detector.detect(scan);
      expect(gaps.length).toBeLessThanOrEqual(5);
    });

    test("custom maxSuggestions is respected", () => {
      const limited = new GapDetector({ maxSuggestions: 3 });
      const scan = makeScan({
        files: [
          "src/routes/index.ts",
          "src/index.ts",
          "src/components/App.tsx",
        ],
        directories: ["src/routes", "src/controllers", "src/components"],
        dependencies: ["express", "react"],
      });

      const gaps = limited.detect(scan);
      expect(gaps.length).toBeLessThanOrEqual(3);
    });
  });

  describe("severity ordering", () => {
    test("critical gaps appear before lower severity", () => {
      const scan = makeScan({
        files: ["src/routes/index.ts", "src/index.ts"],
        directories: ["src/routes"],
        dependencies: ["express"],
      });

      const gaps = detector.detect(scan);
      expect(gaps.length).toBeGreaterThan(0);

      if (gaps.length >= 2) {
        const severityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
        for (let i = 1; i < gaps.length; i++) {
          expect(severityOrder[gaps[i]!.severity]).toBeGreaterThanOrEqual(
            severityOrder[gaps[i - 1]!.severity],
          );
        }
      }
    });
  });

  describe("error-handling gap", () => {
    test("detects missing error handler when routes exist", () => {
      const scan = makeScan({
        files: ["src/routes/api.ts"],
        directories: ["src/routes"],
        dependencies: ["express"],
      });

      const gaps = detector.detect(scan);
      const errorGap = gaps.find((g) => g.category === "error-handling");
      expect(errorGap).toBeDefined();
      expect(errorGap!.title).toBe("Global error handler missing");
    });

    test("no error-handling gap when error boundary exists", () => {
      const scan = makeScan({
        files: ["src/routes/api.ts", "src/middleware/error-handler.ts"],
        directories: ["src/routes"],
        dependencies: ["express"],
      });

      const gaps = detector.detect(scan);
      const errorGap = gaps.find(
        (g) =>
          g.category === "error-handling" &&
          g.title === "Global error handler missing",
      );
      expect(errorGap).toBeUndefined();
    });
  });

  describe("testing gap", () => {
    test("detects missing tests when source files exist", () => {
      const scan = makeScan({
        files: [
          "src/index.ts",
          "src/utils.ts",
          "src/service.ts",
          "src/config.ts",
        ],
        directories: ["src"],
        dependencies: ["express"],
      });

      const gaps = detector.detect(scan);
      const testGap = gaps.find((g) => g.category === "testing");
      expect(testGap).toBeDefined();
    });

    test("no testing gap when test files exist", () => {
      const scan = makeScan({
        files: [
          "src/index.ts",
          "src/utils.ts",
          "src/utils.test.ts",
          "src/service.ts",
        ],
        directories: ["src"],
        dependencies: ["express"],
      });

      const gaps = detector.detect(scan);
      const testGap = gaps.find((g) => g.category === "testing");
      expect(testGap).toBeUndefined();
    });
  });

  describe("empty / minimal projects", () => {
    test("empty scan returns no gaps", () => {
      const scan = makeScan({
        hasPackageJson: false,
      });
      const gaps = detector.detect(scan);
      expect(gaps).toEqual([]);
    });

    test("project with only package.json and readme has minimal gaps", () => {
      const scan = makeScan({
        files: ["package.json", "README.md"],
        directories: [],
        dependencies: [],
      });
      const gaps = detector.detect(scan);
      const categories = gaps.map((g) => g.category);
      expect(categories).not.toContain("security");
      expect(categories).not.toContain("reliability");
    });
  });

  describe("gap shape", () => {
    test("each gap has all required fields", () => {
      const scan = makeScan({
        files: ["src/routes/index.ts"],
        directories: ["src/routes"],
        dependencies: ["express"],
      });

      const gaps = detector.detect(scan);
      for (const gap of gaps) {
        expect(gap.category).toBeDefined();
        expect(gap.severity).toBeDefined();
        expect(gap.title).toBeDefined();
        expect(gap.description).toBeDefined();
        expect(gap.trigger).toBeDefined();
        expect(gap.suggestion).toBeDefined();
        expect(typeof gap.category).toBe("string");
        expect(typeof gap.severity).toBe("string");
        expect(typeof gap.title).toBe("string");
        expect(typeof gap.trigger).toBe("string");
      }
    });
  });
});
