import { mkdir } from "node:fs/promises";
import { join } from "node:path";

export interface ScreenshotResult {
  filePath: string;
  url: string;
  flowName: string;
  timestamp: number;
}

// Playwright is an optional peer dep; variable-expression import keeps
// TypeScript from resolving it at compile time (no @types/playwright needed).
interface PlaywrightPage {
  goto(url: string, options?: { waitUntil?: string }): Promise<unknown>;
  screenshot(options: { path: string; fullPage?: boolean }): Promise<unknown>;
}
interface PlaywrightBrowser {
  newPage(): Promise<PlaywrightPage>;
  close(): Promise<void>;
}
interface PlaywrightChromium {
  launch(options?: { headless?: boolean }): Promise<PlaywrightBrowser>;
}
interface PlaywrightModule {
  chromium: PlaywrightChromium;
}

const PLAYWRIGHT_MODULE = "playwright";

export async function captureScreenshot(
  url: string,
  flowName: string,
): Promise<ScreenshotResult> {
  const timestamp = Date.now();
  const dir = ".omg/evidence";
  await mkdir(dir, { recursive: true });
  const filePath = join(dir, `wow-${flowName}-${timestamp}.png`);

  const pw = (await import(PLAYWRIGHT_MODULE)) as PlaywrightModule;
  const browser = await pw.chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: "networkidle" });
  await page.screenshot({ path: filePath, fullPage: true });
  await browser.close();

  return { filePath, url, flowName, timestamp };
}

export async function isScreenshotAvailable(): Promise<boolean> {
  try {
    await import(PLAYWRIGHT_MODULE);
    return true;
  } catch {
    return false;
  }
}
