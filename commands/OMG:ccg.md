---
description: OMG CCG mode (tri-track synthesis) in standalone Bun runtime.
allowed-tools: Read, Grep, Glob, Bash(bun:*), Bash(git:*), Bash(rg:*), Bash(find:*), Bash(cat:*)
argument-hint: "problem statement"
---

# /OMG:ccg

Runs OMG internal tri-track routing and returns merged actions.

```bash
OMG_CLI="${OMG_CLI_PATH:-$HOME/.claude/omg-runtime/scripts/omg.ts}"
if [ ! -f "$OMG_CLI" ] && [ -f "scripts/omg.ts" ]; then OMG_CLI="scripts/omg.ts"; fi
bun "$OMG_CLI" ccg --problem "[problem]"
```

Use this when backend, frontend, and orchestration work are tightly coupled.
