---
description: OAL CCG mode (tri-track synthesis) in standalone mode.
allowed-tools: Read, Grep, Glob, Bash(python3:*), Bash(git:*), Bash(rg:*), Bash(find:*), Bash(cat:*)
argument-hint: "problem statement"
---

# /OAL:ccg — Standalone CCG

Runs OAL internal tri-track routing and returns merged actions.

```bash
OAL_CLI="${OAL_CLI_PATH:-$HOME/.claude/oal-runtime/scripts/oal.py}"
if [ ! -f "$OAL_CLI" ] && [ -f "scripts/oal.py" ]; then OAL_CLI="scripts/oal.py"; fi
python3 "$OAL_CLI" ccg --problem "[problem]"
```

Use this when backend+frontend+architecture are coupled.
