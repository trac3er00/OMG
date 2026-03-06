---
description: OMG routing escalation in standalone Bun runtime.
allowed-tools: Read, Grep, Glob, Bash(git:*), Bash(rg:*), Bash(find:*), Bash(cat:*), Bash(bun:*)
argument-hint: "[codex|gemini|ccg|auto] 'problem statement'"
---

# /OMG:escalate

Use the portable runtime installed by `OMG-setup.sh`.

```bash
OMG_CLI="${OMG_CLI_PATH:-$HOME/.claude/omg-runtime/scripts/omg.ts}"
if [ ! -f "$OMG_CLI" ] && [ -f "scripts/omg.ts" ]; then OMG_CLI="scripts/omg.ts"; fi
```

Examples:

```bash
bun "$OMG_CLI" teams --target auto --problem "[problem]"
bun "$OMG_CLI" teams --target codex --problem "[problem]"
bun "$OMG_CLI" teams --target gemini --problem "[problem]"
bun "$OMG_CLI" ccg --problem "[problem]"
```
