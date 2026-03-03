---
description: OMG internal team routing (standalone). Replaces /omc-teams dependency.
allowed-tools: Read, Grep, Glob, Bash(git:*), Bash(rg:*), Bash(find:*), Bash(cat:*), Bash(python3:*)
argument-hint: "[codex|gemini|ccg|auto] 'problem statement'"
---

# /OMG:teams — Standalone Internal Router

Use OMG's internal router without requiring OMC.

## Input contract
- target: `auto|codex|gemini|ccg`
- problem: clear issue statement
- context: optional constraints
- files: optional focus paths
- expected_outcome: optional acceptance target

## Execution
Use internal CLI router:

```bash
OMG_CLI="${OMG_CLI_PATH:-$HOME/.claude/omg-runtime/scripts/omg.py}"
if [ ! -f "$OMG_CLI" ] && [ -f "scripts/omg.py" ]; then OMG_CLI="scripts/omg.py"; fi
python3 "$OMG_CLI" teams --target auto --problem "[problem]"
```

For explicit target:

```bash
python3 "$OMG_CLI" teams --target codex --problem "[problem]"
```

## Output schema
`TeamDispatchResult { status, findings[], actions[], evidence{} }`

## Full-power sub-agent protocol
- For non-trivial tasks, launch multiple sub-agents in parallel (`run_in_background=true`) for independent tracks.
- Collect all task outputs before responding (`background_output` per task id).
- Run a `sequential-thinking` merge step to produce one dependency-ordered execution plan.
