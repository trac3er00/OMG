---
description: "Set cognitive mode (research/architect/implement) for the current session."
allowed-tools: Read, Write, Edit, Bash
argument-hint: "[research|architect|implement|clear]"
---

# /OAL:mode — Set Cognitive Mode

Switch Claude's operating mode for the current session.

## Usage

```
/OAL:mode research     # Focus on reading, searching, synthesizing
/OAL:mode architect    # Focus on system design, no implementation
/OAL:mode implement    # Focus on coding with TDD and verification
/OAL:mode clear        # Clear current mode (return to default)
```

## What It Does

1. Writes `.oal/state/mode.txt` with the selected mode name
2. The `prompt-enhancer` hook reads this file and injects `@mode:` context on every subsequent prompt
3. The corresponding rule file (`rules/contextual/{mode}-mode.md`) activates

## Modes

| Mode | Focus | When to Use |
|------|-------|-------------|
| `research` | Read, search, synthesize | Exploring unfamiliar territory |
| `architect` | Design, plan, no code | Before starting a complex feature |
| `implement` | Code, test, verify | Active development sprint |

## Example

```
/OAL:mode architect
→ Sets mode to architect
→ Every prompt now gets: @mode:ARCHITECT — Map system first. Specs only, no implementation.

/OAL:mode clear
→ Removes .oal/state/mode.txt
→ Mode injection stops
```
