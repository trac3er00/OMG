---
description: "Interactive theme selection, preview, and auto-detection."
usage: "/OAL:theme [--list|--set <name>|--preview <name>|--auto]"
---

# /OAL:theme — Theme Selector

Interactive theme selection, preview, and auto-detection for OAL.

## Usage

```
/OAL:theme --list
/OAL:theme --preview catppuccin-mocha
/OAL:theme --set catppuccin-mocha
/OAL:theme --auto
```

## What It Does

1. `--list`: Returns a sorted list of available theme names.
2. `--preview <name>`: Returns preview info `{name, colors, ansi_preview: str}` without applying.
3. `--set <name>`: Applies and persists the theme, returns `{success, theme, applied_at}`.
4. `--auto`: Detects dark/light mode and returns appropriate default theme name.

## Feature Flag

Themes are gated behind `OAL_THEMES_ENABLED` (default: `False`).

Enable via environment variable:
```bash
export OAL_THEMES_ENABLED=true
```

Or in `settings.json`:
```json
{
  "_oal": {
    "features": {
      "THEMES": true
    }
  }
}
```
