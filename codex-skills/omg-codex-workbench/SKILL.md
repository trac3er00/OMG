---
name: omg-codex-workbench
description: Use when Codex needs a Codex-only OMG situational view before acting, especially to inspect local project mode, installed OMG skills, provider availability, or the standalone OMG Codex HUD/workbench.
metadata:
  short-description: Codex-only OMG HUD and workbench entrypoint
---

# OMG Codex Workbench

This is a Codex-only OMG skill. Do not mirror Claude plugin behavior here.

## Workflow

1. Start with the standalone Codex HUD/workbench:
   - `omg-codex-hud --project "$PWD"`
   - `omg-codex-hud --project "$PWD" --json`
2. Use the HUD output to inspect:
   - current `.omg/state/mode.txt`
   - handoff and notes presence
   - installed OMG-managed Codex skills
   - local availability of `codex`, `gemini`, and `kimi`
3. Treat the HUD as a local status surface, not as a native Codex statusline hook.
4. If deeper orchestration is needed, move next to `omg-orchestrator` or `omg-provider-interop`.

## When To Read More

- Read [references/hud.md](references/hud.md) when you need the expected HUD fields and the Codex-only operating rules.
