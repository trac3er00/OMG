---
description: "Set canonical mode (chill/focused/exploratory) for the current session."
allowed-tools: Read, Write, Edit, Bash
argument-hint: "[chill|focused|exploratory|clear]"
---

# /OMG:mode — Set Canonical Mode

Switch Claude's operating mode for the current session.

## Usage

```
/OMG:mode chill        # Focus on low-intensity, conservative progress
/OMG:mode focused      # Focus on coding and execution
/OMG:mode exploratory  # Focus on discovery and synthesis
/OMG:mode clear        # Clear current mode (return to default)
```

## What It Does

1. Writes `.omg/state/mode.txt` with the selected mode name
2. The `prompt-enhancer` hook reads this file and injects `@mode:` context on every subsequent prompt
3. The corresponding rule file (`rules/contextual/{mode}-mode.md`) activates

## Canonical Modes

| Mode | Focus | When to Use |
|------|-------|-------------|
| `chill` | Conservative execution pace | Low-risk maintenance and steady progress |
| `focused` | Implementation-forward flow | Active feature work with verification |
| `exploratory` | Discovery, synthesis, and mapping | Unknown domains and research-heavy sessions |

## Example

```
/OMG:mode focused
→ Sets mode to focused
→ Every prompt now gets: @mode:FOCUSED — Implement deliberately with tight verification loops.

/OMG:mode clear
→ Removes .omg/state/mode.txt
→ Mode injection stops
```
