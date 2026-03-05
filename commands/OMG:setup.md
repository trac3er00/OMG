---
description: "Interactive setup wizard for OMG v3 — detect CLIs, verify auth, select plan, configure MCPs, set bypass mode"
allowed-tools: Read, Write, Edit, Bash(python*:*), Bash(ls:*), Bash(grep:*)
argument-hint: "[optional: --non-interactive for CI mode]"
---

# /OMG:setup — Interactive Setup Wizard

Feature-gated: requires `OMG_SETUP_ENABLED=1` or `settings.json._omg.features.SETUP: true`.

## Overview

Guided setup for OMG v3 multi-CLI environment. Detects installed CLI tools,
verifies authentication, detects Claude plan, selects MCP servers, configures
bypass-all mode, and finalizes preferences.

All wizard logic lives in `hooks/setup_wizard.py`. Call the Python functions
directly via `python3 hooks/setup_wizard.py` or import them as needed.

## Wizard Flow

```
Step 1: Detect CLIs
  → Scan PATH for: codex, gemini, opencode, kimi
  → Report: installed / not found / version

Step 2: Check Auth + CLI Login Help
  → For each detected CLI, verify authentication
  → Ask: "Do you have subscriptions or API access to ChatGPT, Gemini, or Kimi?"
  → Call get_cli_auth_instructions(provider) for each unauthenticated CLI
  → Show auth instructions and wait for user to complete login
  → Report: authenticated / needs login / error

Step 3: Claude Plan Detection
  → Ask: "Which Claude plan do you have? [Max/Pro]"
  → Call configure_plan_type(plan_type) with the user's answer
  → If Pro: configure model routing (planning→opus, coding→sonnet, commit→haiku)
  → If Max: use default routing (all roles → claude-sonnet)
  → Saves plan_type and model_routing to settings.json._omg

Step 4: MCP Selection
  → Show catalog of 11 available MCPs with descriptions and categories
  → Default 5 are pre-selected: context7, filesystem, websearch, chrome-devtools, omg-memory
  → Let user toggle additional MCPs on/off
  → Call select_mcps(selected_ids) with the final selection
  → Returns the MCP config dict ready for .mcp.json

Step 5: Bypass-All Mode
  → Display the full BYPASS_ALL_WARNING text
  → Ask: "Enable full vibe-code mode? (y/N)"
  → Call configure_bypass_all(enabled=True/False) based on answer
  → Updates settings.json._omg.bypass_all

Step 6: Configure MCP
  → Set settings.json._omg.setup_in_progress = true (exempts .mcp.json from config-guard)
  → Write .mcp.json with the MCPs selected in the selection step
  → Reset settings.json._omg.setup_in_progress = false

Step 7: Set Preferences
  → Confirm final settings summary with user
  → Save all preferences to settings.json
  → Report: setup complete
```

## MCP Catalog (11 servers)

| ID | Name | Category | Default | Description |
|----|------|----------|---------|-------------|
| `context7` | Context7 | productivity | ✅ | Upstash Context7 for context management |
| `filesystem` | Filesystem | system | ✅ | File operations via MCP filesystem server |
| `websearch` | Web Search | search | ✅ | Internet queries via web search MCP |
| `chrome-devtools` | Chrome DevTools | browser | ✅ | Browser automation via Chrome DevTools |
| `omg-memory` | OMG Memory | memory | ✅ | OMG shared memory server (HTTP, port 8765) |
| `github` | GitHub | vcs | ☐ | Repository operations via GitHub MCP |
| `puppeteer` | Puppeteer | browser | ☐ | Browser automation via Puppeteer |
| `brave-search` | Brave Search | search | ☐ | Web search via Brave Search MCP |
| `sequential-thinking` | Sequential Thinking | reasoning | ☐ | Step-by-step reasoning server |
| `grep-app` | Grep App | search | ☐ | Code search across public repositories |
| `memory-graph` | Memory Graph | memory | ☐ | Knowledge graph via MCP memory server |

## Python Functions (hooks/setup_wizard.py)

```python
# Auth instructions for a CLI provider (used in wizard step 2)
get_cli_auth_instructions(provider: str) -> dict[str, str]
# Returns: {"provider": ..., "instructions": ..., "url": ...}

# Configure Claude plan type and model routing (used in wizard step 3)
configure_plan_type(plan_type: str) -> dict[str, Any]
# plan_type: "max" or "pro"
# Returns: {"plan_type": ..., "model_routing": {...}, "saved": True}

# Select MCPs and build .mcp.json config (used in wizard step 4)
select_mcps(selected_ids: list[str] | None = None) -> dict[str, Any]
# selected_ids: list of MCP IDs, or None for defaults
# Returns: {"selected": [...], "config": {...}, "count": N}

# Configure bypass-all mode (used in wizard step 5)
configure_bypass_all(enabled: bool) -> dict[str, Any]
# Returns: {"bypass_all": True/False, "saved": True}
```

## Modes

### Interactive (default)
Prompts the user at each step. Confirms before writing config files.

### Non-interactive (`--non-interactive`)
For CI/automation. Uses sensible defaults:
- Detects all CLIs silently
- Checks auth silently
- Defaults to Max plan
- Uses default 5 MCPs
- Bypass-all defaults to off
- Skips confirmation prompts

## Output

Returns a summary dict:
```json
{
  "status": "complete",
  "clis_detected": ["codex", "gemini"],
  "auth_status": {"codex": "ok", "gemini": "needs_login"},
  "plan_type": "pro",
  "mcps_selected": ["context7", "filesystem", "websearch", "chrome-devtools", "omg-memory"],
  "bypass_all": false,
  "mcp_configured": true,
  "preferences_saved": true
}
```

## Error Handling

- CLI detection failures are non-fatal (reported as "not found")
- Auth check failures are non-fatal (reported as "error")
- MCP config write failures are reported but don't abort the wizard
- The wizard always completes — partial results are valid

## Integration

- Uses `hooks/setup_wizard.py` for all wizard logic
- Uses `hooks/_common.py` for `get_feature_flag("SETUP", default=False)`
- Writes `.mcp.json` with selected MCP servers
- Saves preferences to `settings.json._omg`
- Can be re-run safely — idempotent operations
