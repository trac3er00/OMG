import { mkdir } from "node:fs/promises";
import { join } from "node:path";

export interface ScreenshotResult {
  filePath: string;
  url: string;
  flowName: string;
  timestamp: number;
}

export async function captureScreenshot(
  url: string,
  flowName: string,
): Promise<ScreenshotResult> {
  const timestamp = Date.now();
  const dir = ".omg/evidence";
  await mkdir(dir, { recursive: true });
  const filePath = join(dir, `wow-${flowName}-${timestamp}.png`);

  const { chromium } = await import("playwright");
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: "networkidle" });
  await page.screenshot({ path: filePath, fullPage: true });
  await browser.close();

  return { filePath, url, flowName, timestamp };
}

export async function isScreenshotAvailable(): Promise<boolean> {
  try {
    await import("playwright");
    return true;
  } catch {
    return false;
  }
}
