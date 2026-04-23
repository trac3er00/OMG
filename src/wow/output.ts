export interface WowResult {
  url?: string;
  screenshot?: string; // file path
  proofScore?: number;
  buildTime?: number; // ms
  flowName: string;
  success: boolean;
  error?: string;
}

/** Format result as structured object */
export function formatResult(result: WowResult): WowResult {
  return { ...result };
}

/** Format result as human-readable string */
export function formatResultHuman(result: WowResult): string {
  const lines: string[] = [];
  if (result.success) {
    if (result.url) lines.push(`✅ Deployed: ${result.url}`);
    if (result.proofScore !== undefined) lines.push(`📊 ProofScore: ${result.proofScore}/100`);
    if (result.screenshot) lines.push(`📸 Screenshot: ${result.screenshot}`);
    if (result.buildTime !== undefined) lines.push(`⏱  Build time: ${(result.buildTime / 1000).toFixed(1)}s`);
  } else {
    lines.push(`❌ Failed: ${result.error ?? "Unknown error"}`);
  }
  return lines.join("\n");
}

/** Print result to stdout (JSON if --json flag, human-readable otherwise) */
export function printResult(result: WowResult, json: boolean = false): void {
  if (json) {
    console.log(JSON.stringify(formatResult(result), null, 2));
  } else {
    console.log(formatResultHuman(result));
  }
}