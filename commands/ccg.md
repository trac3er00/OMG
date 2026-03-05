---
description: OMG CCG mode (tri-track synthesis) in standalone mode.
allowed-tools: Read, Grep, Glob, Bash(python3:*), Bash(git:*), Bash(rg:*), Bash(find:*), Bash(cat:*)
argument-hint: "problem statement"
---

# /OMG:ccg — Standalone CCG

Runs OMG internal tri-track routing and returns merged actions.

CCG execution standard:
- launch backend/frontend/architecture analysis in parallel sub-agents
- collect all tracks with `background_output`
- run `sequential-thinking` to merge tracks into one execution order

```bash
OMG_CLI="${OMG_CLI_PATH:-$HOME/.claude/omg-runtime/scripts/omg.py}"
if [ ! -f "$OMG_CLI" ] && [ -f "scripts/omg.py" ]; then OMG_CLI="scripts/omg.py"; fi
python3 "$OMG_CLI" ccg --problem "[problem]"
```

Use this when backend+frontend+architecture are coupled.
