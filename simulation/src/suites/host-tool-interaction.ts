/**
 * Host tool interaction simulation suite.
 *
 * Validates that OMG hooks handle host AI native tool events correctly.
 * Host-native tools (AskUserQuestion, TodoWrite) are owned by the host
 * runtime — OMG observes their events via hooks but does not control them.
 *
 * Pairs with tests/production/test_host_tool_interaction.py for local
 * pytest-based verification.
 */

import { existsSync } from "node:fs";
import { join } from "node:path";

/** Hook files involved in host-native tool event handling. */
export const HOST_TOOL_HOOKS = [
  "firewall.py",
  "todo-state-tracker.py",
  "pre-tool-inject.py",
  "post-tool-output.py",
] as const;

export type HostToolHook = (typeof HOST_TOOL_HOOKS)[number];

export interface HookPresenceEntry {
  readonly hook: HostToolHook;
  readonly present: boolean;
}

export interface HostToolInteractionResult {
  readonly firewallPresent: boolean;
  readonly todoTrackerPresent: boolean;
  readonly preToolInjectPresent: boolean;
  readonly postToolOutputPresent: boolean;
  readonly allPresent: boolean;
  readonly hookDetails: readonly HookPresenceEntry[];
  readonly duration_ms: number;
}

/**
 * Run the host tool interaction suite.
 *
 * Checks that all hooks involved in host-native tool event handling
 * are present on disk. This is a prerequisite for the full pytest-based
 * interaction tests in test_host_tool_interaction.py.
 */
export async function runHostToolInteractionSuite(options?: {
  rootDir?: string;
}): Promise<HostToolInteractionResult> {
  const start = Date.now();
  const root = options?.rootDir ?? process.cwd();
  const hooksDir = join(root, "hooks");

  const hookDetails: HookPresenceEntry[] = HOST_TOOL_HOOKS.map((hook) => ({
    hook,
    present: existsSync(join(hooksDir, hook)),
  }));

  const firewallPresent = hookDetails.find(
    (h) => h.hook === "firewall.py",
  )!.present;
  const todoTrackerPresent = hookDetails.find(
    (h) => h.hook === "todo-state-tracker.py",
  )!.present;
  const preToolInjectPresent = hookDetails.find(
    (h) => h.hook === "pre-tool-inject.py",
  )!.present;
  const postToolOutputPresent = hookDetails.find(
    (h) => h.hook === "post-tool-output.py",
  )!.present;

  return {
    firewallPresent,
    todoTrackerPresent,
    preToolInjectPresent,
    postToolOutputPresent,
    allPresent: hookDetails.every((h) => h.present),
    hookDetails,
    duration_ms: Date.now() - start,
  };
}
