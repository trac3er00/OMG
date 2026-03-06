---
description: "Interactive setup wizard for OMG v2.0 — detect CLIs, verify auth, configure MCP memory server"
allowed-tools: Read, Write, Edit, Bash(python*:*), Bash(ls:*), Bash(grep:*)
argument-hint: "[optional: --non-interactive for CI mode]"
---

# /OMG:setup — Interactive Setup Wizard

Feature-gated: requires `OMG_SETUP_ENABLED=1` or `settings.json._omg.features.SETUP: true`.

## Overview

Guided setup for OMG v2.0 multi-CLI environment. Detects installed CLI tools,
verifies authentication, configures MCP memory servers, and sets user preferences.

## Wizard Flow

```
Step 1: Detect CLIs
  → Scan PATH for: codex, gemini, kimi
  → Report: installed / not found / version

Step 2: Check Auth
  → For each detected CLI, verify authentication
  → Report: authenticated / needs login / error
  → Suggest auth commands for unauthenticated CLIs

Step 3: Configure MCP
  → For each authenticated CLI, offer to write MCP server config
  → Uses provider.write_mcp_config() from provider registry
  → Confirm each write before proceeding

Step 4: Set Preferences
  → Preferred model routing (which CLI for which task type)
  → Default timeout for CLI invocations
  → Save to .omg/state/setup-preferences.json
```

## Modes

### Interactive (default)
Prompts the user at each step. Confirms before writing config files.

### Non-interactive (`--non-interactive`)
For CI/automation. Uses sensible defaults:
- Detects all CLIs silently
- Checks auth silently
- Skips MCP config writes (requires explicit opt-in)
- Uses default preferences

## Output

Returns a summary dict:
```json
{
  "status": "complete",
  "clis_detected": ["codex", "gemini"],
  "auth_status": {"codex": "ok", "gemini": "needs_login"},
  "mcp_configured": ["codex"],
  "preferences_saved": true
}
```

## Error Handling

- CLI detection failures are non-fatal (reported as "not found")
- Auth check failures are non-fatal (reported as "error")
- MCP config write failures are reported but don't abort the wizard
- The wizard always completes — partial results are valid

## Integration

- Uses `list_available_providers()` from `runtime/cli_provider.py` for CLI detection
- Uses individual `CLIProvider` instances for auth checks and MCP config writes
- Saves preferences to `.omg/state/setup-preferences.json`
- Can be re-run safely — idempotent operations
