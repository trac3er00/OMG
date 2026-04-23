import { expect, test } from "bun:test";
import { runAdminFlow } from "./admin.js";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

test("runAdminFlow creates admin dashboard", async () => {
  const outputDir = "/tmp/test-admin-" + Date.now();
  const result = await runAdminFlow("create admin dashboard", outputDir);

  expect(result.success).toBe(true);
  expect(result.flowName).toBe("admin");

  const appJsxPath = join(outputDir, "src/App.jsx");
  expect(existsSync(appJsxPath)).toBe(true);
  const appJsxContent = readFileSync(appJsxPath, "utf-8");
  expect(appJsxContent).toContain("DataTable");

  const dataTableJsxPath = join(outputDir, "src/components/DataTable.jsx");
  expect(existsSync(dataTableJsxPath)).toBe(true);
});
