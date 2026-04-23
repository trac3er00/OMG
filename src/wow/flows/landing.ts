import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { WowResult } from "../output.js";
import { deploy } from "../../deploy/integrations.js";

const LANDING_HTML = `<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Landing Page</title><link rel="stylesheet" href="styles.css"></head>
<body><header><h1>Welcome</h1></header><main><p>Your landing page is ready.</p></main></body>
</html>`;

const LANDING_CSS = `* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: sans-serif; line-height: 1.6; }
header { background: #333; color: white; padding: 1rem; }
main { max-width: 800px; margin: 2rem auto; padding: 0 1rem; }`;

export async function runLandingFlow(_goal: string, outputDir: string): Promise<WowResult> {
  const startTime = Date.now();
  try {
    await mkdir(outputDir, { recursive: true });
    await writeFile(join(outputDir, "index.html"), LANDING_HTML);
    await writeFile(join(outputDir, "styles.css"), LANDING_CSS);
    
    const deployResult = await deploy(outputDir);
    const buildTime = Date.now() - startTime;
    
    const result: WowResult = {
      flowName: "landing",
      success: true,
      proofScore: deployResult.success ? 75 : 60,
      buildTime,
    };
    
    if (deployResult.url) {
      result.url = deployResult.url;
    }
    
    return result;
  } catch (error) {
    return {
      flowName: "landing",
      success: false,
      error: error instanceof Error ? error.message : String(error),
      buildTime: Date.now() - startTime,
    };
  }
}
