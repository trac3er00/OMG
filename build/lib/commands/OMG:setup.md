---
description: "Native OMG setup and adoption flow for supported hosts"
allowed-tools: Read, Write, Edit, Bash(python*:*), Bash(ls:*), Bash(grep:*)
argument-hint: "[optional: --non-interactive, --mode omg-only|coexist, --preset safe|balanced|interop|labs|buffet|plugins-first]"
---

# /OMG:setup

Feature-gated: requires `OMG_SETUP_ENABLED=1` or `settings.json._omg.features.SETUP: true`.

## Overview

Native OMG setup for Claude Code, Codex, and other supported CLIs.
The command keeps migration logic internal and focuses the user on a small adoption flow:

1. Detect supported CLIs.
2. Detect overlapping ecosystems.
3. Recommend an adoption mode.
4. Apply an OMG preset.
5. Configure MCP and save preferences.

Setup now runs foreign-plugin discovery in `interop` and `coexist` modes, reporting compatibility findings and potential overlaps.

## Wizard Flow

```text
Step 1: Detect CLIs
  - codex
  - gemini
  - kimi

Step 2: Detect adoption context
  - OMC-style markers
  - OMX-style markers
  - Superpowers-style markers

Step 3: Choose mode
  - OMG-only (recommended)
  - coexist

Step 4: Choose preset
  - safe
  - balanced
  - interop
  - labs
  - buffet
  - plugins-first (alias for interop)

Step 5: Configure MCP and persist preferences
  - writes .mcp.json
  - writes .omg/state/cli-config.yaml
  - writes .omg/state/adoption-report.json
```

## Modes

`OMG-only`
- Recommended default.
- OMG becomes the main hooks, HUD, MCP, and orchestration layer.

`coexist`
- Advanced mode.
- OMG avoids destructive overlap and keeps third-party command namespaces intact where possible.

## Output

The command emits a final summary that includes:

- CLI detection results
- auth status
- MCP configuration status
- selected preset
- selected adoption mode
- adoption report path

## Public Path

The public OMG journey is:

1. install for your host
2. run `/OMG:setup`
3. run `/OMG:crazy <goal>`
