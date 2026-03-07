---
description: "Set cognitive mode (research/architect/implement) for the current session."
allowed-tools: Read, Write, Edit, Bash
argument-hint: "[research|architect|implement|clear]"
---

# /OMG:mode — Set Cognitive Mode

Switch Claude's operating mode for the current session.

## Usage

```
/OMG:mode research     # Focus on reading, searching, synthesizing
/OMG:mode architect    # Focus on system design, no implementation
/OMG:mode implement    # Focus on coding with TDD and verification
/OMG:mode clear        # Clear current mode (return to default)
```

## What It Does

1. Writes `.omg/state/mode.txt` with the selected mode name
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
/OMG:mode architect
→ Sets mode to architect
→ Every prompt now gets: @mode:ARCHITECT — Map system first. Specs only, no implementation.

/OMG:mode clear
→ Removes .omg/state/mode.txt
→ Mode injection stops
```
