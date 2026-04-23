import { describe, expect, test } from "bun:test";
import { mkdtemp, readFile, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { runSaasFlow } from "./saas.js";

describe("SaaS Flow", () => {
  test("creates SaaS starter files and returns success", async () => {
    const outputDir = await mkdtemp(join(tmpdir(), "test-saas-"));
    const result = await runSaasFlow("create SaaS starter", outputDir);

    expect(result.flowName).toBe("saas");
    expect(result.success).toBe(true);
    expect(result.buildTime).toBeGreaterThanOrEqual(0);

    const packageJsonPath = join(outputDir, "package.json");
    const indexPath = join(outputDir, "src/index.js");
    const healthPath = join(outputDir, "src/routes/health.js");
    const authPath = join(outputDir, "src/routes/auth.js");
    const dbPath = join(outputDir, "src/config/db.js");

    expect((await stat(packageJsonPath)).isFile()).toBe(true);
    expect((await stat(indexPath)).isFile()).toBe(true);
    expect((await stat(healthPath)).isFile()).toBe(true);
    expect((await stat(authPath)).isFile()).toBe(true);
    expect((await stat(dbPath)).isFile()).toBe(true);

    const packageJson = await readFile(packageJsonPath, "utf8");
    const indexJs = await readFile(indexPath, "utf8");

    expect(packageJson).toContain('"healthEndpoint": "/health"');
    expect(packageJson).toContain('"dbConfig": "src/config/db.js"');
    expect(indexJs).toContain("app.get('/health', healthRoute);");
    expect(indexJs).toContain("app.post('/auth/login', authRoute);");
  });

  test("graceful failure when outputDir is invalid", async () => {
    const result = await runSaasFlow(
      "create SaaS starter",
      "/dev/null/invalid",
    );

    expect(result.flowName).toBe("saas");
    expect(result.success).toBe(false);
    expect(result.error).toBeDefined();
  });
});
