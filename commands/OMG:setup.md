---
description: "Native OMG setup and adoption flow for supported hosts"
allowed-tools: Read, Write, Edit, AskUserQuestion, Bash(python*:*), Bash(ls:*), Bash(grep:*), Bash(bash:*OMG-setup*), Bash(chmod:*), Bash(mkdir:*), Bash(cp:*), Bash(ln:*)
argument-hint: "[optional: --non-interactive, --mode omg-only|coexist, --preset safe|balanced|interop|labs|buffet|production]"
---

# /OMG:setup

Feature-gated: requires `OMG_SETUP_ENABLED=1` or `settings.json._omg.features.SETUP: true`.

## Overview

Native OMG setup for Claude Code, Codex, and other supported CLIs.
The command keeps migration logic internal and focuses the user on a small adoption flow:

1. Detect supported CLIs and check their **authentication status**.
2. Help user authenticate unauthenticated CLIs (offer login guidance).
3. Detect overlapping ecosystems.
4. Ask about **subscription plan** (per provider) to configure token optimization.
5. Recommend an adoption mode.
6. Apply an OMG preset.
7. Configure **OpusPlan** (token optimization for budget-constrained tiers).
8. Configure MCP and save preferences.

Setup now runs foreign-plugin discovery in `interop` and `coexist` modes, reporting compatibility findings and potential overlaps.

## Wizard Flow

```text
Step 1: Detect CLIs + Auth Status
  Run: python3 -c "from hooks.setup_wizard import detect_clis; ..."
  For each CLI (codex, gemini, kimi, opencode):
    - Check if binary is installed (shutil.which)
    - Check authentication status (provider.check_auth)
    - Display: installed & authenticated / installed but NOT authenticated / not installed

Step 2: Auth Help (for unauthenticated CLIs)
  If any CLI is detected but not authenticated → use AskUserQuestion:
    question: "<cli_name> is installed but not authenticated. OMG uses it for
               deep debugging (codex), UI review (gemini), etc.
               Would you like to connect it now?"
    options:
      - label: "Yes, help me authenticate"
      - label: "Skip for now"
  If yes:
    - Show the auth command from get_cli_auth_instructions(provider)
      (e.g. "codex login", "gemini auth login")
    - Show what subscription is required
      (e.g. "Requires ChatGPT Plus or OpenAI API key")
    - Tell user to run the command in their terminal, then come back
    - After user confirms, re-run detect_clis() to verify auth

Step 3: Subscription Plan (per provider) → use AskUserQuestion:
  question: "What is your Claude Code subscription plan?
             OMG optimizes agent limits, token usage, and model routing based on this."
  header: "Subscription"
  options:
    - label: "Free", description: "API key only — limited tokens"
    - label: "Pro ($20/mo)", description: "45 msgs/5hrs Opus, 200K context"
    - label: "Max ($100-200/mo)", description: "5-20x Pro usage, up to 1M context on Opus"
    - label: "Team ($25/user/mo)", description: "Team admin, higher limits"
    - label: "Enterprise", description: "Custom limits, SSO, SLA"

  For each OTHER detected+authed provider, also ask about their plan:
    e.g. "What is your Codex (OpenAI) subscription?"
      - Free / Plus ($20/mo) / Team / Enterprise

  Persist: write tier to settings.json._omg.subscription_tier
           write per-provider plans to .omg/state/cli-config.yaml

Step 4: Detect adoption context
  - OMC-style markers
  - OMX-style markers
  - Superpowers-style markers

Step 5: Choose mode → use AskUserQuestion:
  question: "Which adoption mode should OMG use?"
  header: "Mode"
  options:
    - label: "OMG-only (Recommended)", description: "OMG becomes the main hooks, HUD, MCP, and orchestration layer"
    - label: "Coexist", description: "Avoids destructive overlap, keeps third-party command namespaces intact"

Step 6: Choose preset → use AskUserQuestion:
  question: "Which preset should OMG apply?"
  header: "Preset"
  options:
    - label: "safe (Recommended)", description: "Minimum managed OMG surface"
    - label: "balanced", description: "Safe defaults plus extra productivity MCPs"
    - label: "labs", description: "Experimental and browser-heavy surfaces"
    - label: "buffet", description: "Full preset — enables every managed flag"
  (interop, production, plugins-first available via Other)

Step 7: Configure OpusPlan
  Run: python3 -c "from runtime.opus_plan import get_opus_plan, format_opus_plan_summary; ..."
  Based on the effective tier (highest across all providers):
    - Write opus_plan config to settings.json._omg.opus_plan
    - Show user what was configured:
      For free/pro (OpusPlan ACTIVE):
        - Max parallel agents: 1-2
        - Context compression: aggressive/moderate
        - Budget warnings at: 30-40% (earlier than default 50%)
        - Prefer /OMG:escalate over /OMG:ccg (tri-model is expensive)
        - Model routing: haiku(explore) → sonnet(implement) → opus(critical only)
      For max/team/enterprise (OpusPlan inactive):
        - Full agent concurrency
        - No compression
        - Standard warning thresholds

Step 8: Configure MCP and persist preferences
  - writes .mcp.json
  - writes .omg/state/cli-config.yaml
  - writes .omg/state/adoption-report.json
```

## Provider Capabilities Reference

When showing the user their plan details, use `runtime.opus_plan.format_provider_capabilities()`:

| Provider | Plan | Context | Models | Agents | Cost |
|----------|------|---------|--------|--------|------|
| Claude | Free | 200K | haiku, sonnet | No | $0 |
| Claude | Pro | 200K | haiku, sonnet, opus | Yes | $20/mo |
| Claude | Max | 1M | haiku, sonnet, opus | Yes | $100-200/mo |
| Claude | Team | 200K | haiku, sonnet, opus | Yes | $25/user/mo |
| Claude | Enterprise | 1M | haiku, sonnet, opus | Yes | Custom |
| Codex | Free | 128K | gpt-4.1 | No | $0 |
| Codex | Plus | 128K | gpt-4.1, o3, o4-mini | Yes | $20/mo |
| Gemini | Free | 1M | gemini-2.5-pro, flash | Yes | $0 |
| Gemini | Pro | 1M | gemini-2.5-pro, flash | Yes | $20/mo |

## OpusPlan

OpusPlan is automatically activated for token-constrained tiers (free, pro).
It optimizes OMG's behavior to maximize value within limited token budgets:

- **Fewer parallel agents** — reduces concurrent token consumption
- **Earlier budget warnings** — alerts at 30-40% instead of 50%
- **Model routing** — cheap tasks use haiku, balanced tasks use sonnet, only critical decisions use opus
- **Prefer escalation** — suggests `/OMG:escalate` (single-model) over `/OMG:ccg` (tri-model)
- **Context compression** — reduces injected context to save tokens

Users on Max, Team, or Enterprise tiers get full capabilities with no restrictions.

Runtime module: `runtime/opus_plan.py`
Key functions: `get_opus_plan(tier)`, `get_model_routing(tier, task_type)`, `should_prefer_escalate(tier)`

## Bypass Mode

For unattended setup (e.g. during Claude Code sessions), use `--bypass` to skip all prompts,
syntax checks, and post-install validation:

```bash
./OMG-setup.sh install --bypass
```

This sets `--non-interactive` and `--merge-policy=apply` automatically.

## Modes

`OMG-only`
- Recommended default.
- OMG becomes the main hooks, HUD, MCP, and orchestration layer.

`coexist`
- Advanced mode.
- OMG avoids destructive overlap and keeps third-party command namespaces intact where possible.

## Output

The command emits a final summary that includes:

- CLI detection results with auth status per provider
- subscription tier (per provider)
- OpusPlan status (active/inactive) with configured limits
- MCP configuration status
- selected preset
- selected adoption mode
- adoption report path

## Public Path

The public OMG journey is:

1. install for your host
2. run `doctor --fix`
3. run `/OMG:setup` (detects CLIs, auth, subscription, configures OpusPlan)
4. run `/OMG:ship <goal>`
