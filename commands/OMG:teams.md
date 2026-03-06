---
description: OMG internal team routing (standalone Bun runtime).
allowed-tools: Read, Grep, Glob, Bash(git:*), Bash(rg:*), Bash(find:*), Bash(cat:*), Bash(bun:*)
argument-hint: "[codex|gemini|ccg|auto] 'problem statement'"
---

# /OMG:teams

Use OMG's internal router through the Bun CLI.

## Input contract

- target: `auto|codex|gemini|ccg`
- problem: clear issue statement
- context: optional constraints
- files: optional focus paths
- expected_outcome: optional acceptance target

## Execution

```bash
OMG_CLI="${OMG_CLI_PATH:-$HOME/.claude/omg-runtime/scripts/omg.ts}"
if [ ! -f "$OMG_CLI" ] && [ -f "scripts/omg.ts" ]; then OMG_CLI="scripts/omg.ts"; fi
bun "$OMG_CLI" teams --target auto --problem "[problem]"
bun "$OMG_CLI" teams --target codex --problem "[problem]"
```

## Output schema

`TeamDispatchResult { status, target, phases[], actions[], evidence{} }`
