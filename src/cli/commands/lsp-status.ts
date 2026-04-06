export async function runLspStatus(): Promise<void> {
  const { getLSPServerStatus } = await import("../../tools/lsp.js");
  const servers = getLSPServerStatus();

  console.log("\n🔧 LSP Server Status\n");

  for (const s of servers) {
    const status = s.running ? "✅ running" : "⚠️  not detected";
    console.log(`  ${s.serverName}: ${status}`);
    console.log(`    Languages: ${s.supportedLanguages.join(", ")}`);
    console.log(`    Capabilities: ${s.capabilities.join(", ")}`);
    console.log();
  }
}
