import { expect, test, describe } from "bun:test";
import { runLandingFlow } from "./landing.js";
import { stat } from "node:fs/promises";
import { join } from "node:path";

describe("Landing Flow", () => {
  test("creates landing page files and returns success", async () => {
    const outputDir =
      "/tmp/test-landing-" + Math.random().toString(36).slice(2);
    const result = await runLandingFlow("make a landing page", outputDir);

    expect(result.flowName).toBe("landing");
    expect(result.success).toBe(true);
    expect(result.buildTime).toBeGreaterThanOrEqual(0);

    const htmlStat = await stat(join(outputDir, "index.html"));
    expect(htmlStat.isFile()).toBe(true);

    const cssStat = await stat(join(outputDir, "styles.css"));
    expect(cssStat.isFile()).toBe(true);
  });

  test("graceful failure when outputDir is invalid", async () => {
    const result = await runLandingFlow(
      "make a landing page",
      "/dev/null/invalid",
    );

    expect(result.flowName).toBe("landing");
    expect(result.success).toBe(false);
    expect(result.error).toBeDefined();
  });
});
