import { readFile } from "node:fs/promises";
import { basename, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { CommandModule } from "yargs";

type HookEntry = {
  readonly hooks?: ReadonlyArray<{
    readonly type?: string;
    readonly command?: string;
    readonly timeout?: number;
  }>;
  readonly matcher?: string;
};

type SettingsFile = {
  readonly hooks?: Record<string, ReadonlyArray<HookEntry>>;
};

const SETTINGS_PATH = resolve(
  fileURLToPath(new URL("../../../settings.json", import.meta.url)),
);

function extractScriptPath(commandText: string): string {
  const tokens = [...commandText.matchAll(/"([^"]+)"|'([^']+)'|(\S+)/g)]
    .map((match) => match[1] ?? match[2] ?? match[3])
    .filter((value): value is string => Boolean(value));

  return tokens.at(-1) ?? commandText;
}

async function loadSettings(): Promise<SettingsFile> {
  const raw = await readFile(SETTINGS_PATH, "utf8");
  return JSON.parse(raw) as SettingsFile;
}

function printHooks(settings: SettingsFile): void {
  console.log("OMG Hooks");
  console.log("");

  const lifecycleOrder = [
    "PreToolUse",
    "PostToolUse",
    "SessionStart",
    "SessionEnd",
    "PostToolUseFailure",
  ];
  const hooks = settings.hooks ?? {};
  const lifecycles = [
    ...lifecycleOrder.filter((name) => name in hooks),
    ...Object.keys(hooks).filter((name) => !lifecycleOrder.includes(name)),
  ];

  for (const lifecycle of lifecycles) {
    const groupsForLifecycle = hooks[lifecycle] ?? [];
    console.log(`${lifecycle}:`);

    for (const group of groupsForLifecycle) {
      for (const hook of group.hooks ?? []) {
        const scriptPath = hook.command ? extractScriptPath(hook.command) : "";
        const scriptName = scriptPath ? basename(scriptPath) : "(unknown)";
        console.log(`  ${scriptName} - ${scriptPath}`);
      }
    }

    console.log("");
  }
}

export const hooksListCommand: CommandModule = {
  command: "list",
  describe: "List registered OMG hooks",
  handler: async (): Promise<void> => {
    const settings = await loadSettings();
    printHooks(settings);
  },
};
