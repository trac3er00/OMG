---
description: "Set canonical mode (chill/focused/exploratory/tdd) for the current session."
allowed-tools: Read, Write, Edit, Bash
argument-hint: "[chill|focused|exploratory|tdd|clear]"
---

# /OMG:mode — Set Canonical Mode

Switch Claude's operating mode for the current session.

## Usage

```
/OMG:mode chill        # Focus on low-intensity, conservative progress
/OMG:mode focused      # Focus on coding and execution
/OMG:mode exploratory  # Focus on discovery and synthesis
/OMG:mode tdd          # Test-Driven Development (RED-GREEN-REFACTOR)
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
| `tdd` | RED-GREEN-REFACTOR cycle | Feature development with strict test discipline |

## Example

```
/OMG:mode focused
→ Sets mode to focused
→ Every prompt now gets: @mode:FOCUSED — Implement deliberately with tight verification loops.

/OMG:mode clear
→ Removes .omg/state/mode.txt
→ Mode injection stops
```

## TDD Mode

When `/OMG:mode tdd` is active, the RED-GREEN-REFACTOR cycle is enforced:

1. **RED**: Write a failing test first — no source code changes allowed without a test
2. **GREEN**: Write minimal code to make the test pass
3. **REFACTOR**: Clean up while keeping tests green

The stop-gate blocks "done" claims without evidence of the full cycle. The proof chain verifies test files were modified before source files.
