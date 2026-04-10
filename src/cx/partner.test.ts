import { afterEach, describe, expect, test } from "bun:test";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import { FullSpectrumPartner } from "./partner.js";

const tempRoots: string[] = [];

function createProject(structure: Record<string, string>): string {
  const root = mkdtempSync(join(tmpdir(), "partner-"));
  tempRoots.push(root);

  for (const [file, content] of Object.entries(structure)) {
    const absolutePath = join(root, file);
    mkdirSync(join(absolutePath, ".."), { recursive: true });
    writeFileSync(absolutePath, content);
  }

  return root;
}

afterEach(() => {
  while (tempRoots.length > 0) {
    rmSync(tempRoots.pop()!, { recursive: true, force: true });
  }
});

describe("FullSpectrumPartner", () => {
  const partner = new FullSpectrumPartner();

  test("routes without auth produce a lower health score", () => {
    const root = createProject({
      "package.json": JSON.stringify({
        name: "api-app",
        dependencies: { express: "^5.0.0" },
      }),
      "bun.lock": "",
      "src/routes/users.ts": "export const usersRoute = true;",
      "src/controllers/users.controller.ts":
        "export const usersController = true;",
      "src/db/schema.ts": "export const schema = {};",
      "src/index.ts": "export const app = true;",
    });

    const analysis = partner.analyzeProject(root);

    expect(analysis.packageManager).toBe("bun");
    expect(analysis.projectType).toBe("backend");
    expect(analysis.healthScore).toBeLessThan(80);
    expect(
      analysis.gaps.some((gap) => gap.title === "Authentication missing"),
    ).toBe(true);
    expect(analysis.suggestedNextSteps).toHaveLength(3);
    expect(
      analysis.suggestedNextSteps.some((step) =>
        /add|run|review|clarify/i.test(step),
      ),
    ).toBe(true);
  });

  test("projects with key layers stay healthy and produce actionable steps", () => {
    const root = createProject({
      "package.json": JSON.stringify({
        name: "full-app",
        dependencies: {
          react: "^19.0.0",
          express: "^5.0.0",
          jsonwebtoken: "^9.0.0",
          zod: "^4.0.0",
          pino: "^9.0.0",
          "express-rate-limit": "^7.0.0",
          vitest: "^3.0.0",
        },
      }),
      "bun.lock": "",
      "README.md": "# Full app",
      Dockerfile: "FROM oven/bun",
      ".github/workflows/ci.yml": "name: ci",
      "src/routes/api.ts": "export const apiRoute = true;",
      "src/components/App.tsx": "export function App() { return null; }",
      "src/auth/jwt.ts": "export const auth = true;",
      "src/validation/schema.ts": "export const schema = {};",
      "src/error-handler.ts": "export const handleError = true;",
      "src/logger.ts": "export const logger = true;",
      "src/health.ts": "export const health = true;",
      "src/db/schema.ts": "export const dbSchema = {};",
      "src/app.test.ts": "export const testFile = true;",
      "src/accessibility/aria.ts": "export const aria = true;",
    });

    const analysis = partner.analyzeProject(root);

    expect(analysis.packageManager).toBe("bun");
    expect(analysis.projectType).toBe("fullstack");
    expect(analysis.healthScore).toBeGreaterThanOrEqual(90);
    expect(analysis.intentContext.analysis.domain).toBeDefined();
    expect(analysis.intentContext.analysis.intent).toBeDefined();
    expect(analysis.suggestedNextSteps).toHaveLength(3);
    expect(
      analysis.suggestedNextSteps.every((step) =>
        /run|review|use|add|clarify/i.test(step),
      ),
    ).toBe(true);
  });
});
