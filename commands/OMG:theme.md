---
description: "Interactive theme selection, preview, and auto-detection."
usage: "/OMG:theme [--list|--set <name>|--preview <name>|--auto]"
---

# /OMG:theme — Theme Selector

Interactive theme selection, preview, and auto-detection for OMG.

## Usage

```
/OMG:theme --list
/OMG:theme --preview catppuccin-mocha
/OMG:theme --set catppuccin-mocha
/OMG:theme --auto
```

## Interactive Selection

When invoked without arguments, use `AskUserQuestion` to present theme choices.
Dynamically populate options from available themes (show top 3-4 by popularity + auto):
- question: "Which theme do you want to apply?"
- header: "Theme"
- options: (dynamically populate, e.g.)
  - label: "auto (Recommended)", description: "Detect dark/light mode automatically"
  - label: "catppuccin-mocha", description: "Warm dark theme"
  - label: "catppuccin-latte", description: "Warm light theme"
  - label: "[next popular theme]", description: "[description]"
- Other themes accessible via Other.

Wait for user selection before applying.

## What It Does

1. `--list`: Returns a sorted list of available theme names.
2. `--preview <name>`: Returns preview info `{name, colors, ansi_preview: str}` without applying.
3. `--set <name>`: Applies and persists the theme, returns `{success, theme, applied_at}`.
4. `--auto`: Detects dark/light mode and returns appropriate default theme name.

## Feature Flag

Themes are gated behind `OMG_THEMES_ENABLED` (default: `False`).

Enable via environment variable:
```bash
export OMG_THEMES_ENABLED=true
```

Or in `settings.json`:
```json
{
  "_omg": {
    "features": {
      "THEMES": true
    }
  }
}
```
