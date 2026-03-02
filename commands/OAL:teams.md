---
description: OAL internal team routing (standalone). Replaces /omc-teams dependency.
allowed-tools: Read, Grep, Glob, Bash(git:*), Bash(rg:*), Bash(find:*), Bash(cat:*), Bash(python3:*)
argument-hint: "[codex|gemini|ccg|auto] 'problem statement'"
---

# /OAL:teams — Standalone Internal Router

Use OAL's internal router without requiring OMC.

## Input contract
- target: `auto|codex|gemini|ccg`
- problem: clear issue statement
- context: optional constraints
- files: optional focus paths
- expected_outcome: optional acceptance target

## Execution
Use internal CLI router:

```bash
OAL_CLI="${OAL_CLI_PATH:-$HOME/.claude/oal-runtime/scripts/oal.py}"
if [ ! -f "$OAL_CLI" ] && [ -f "scripts/oal.py" ]; then OAL_CLI="scripts/oal.py"; fi
python3 "$OAL_CLI" teams --target auto --problem "[problem]"
```

For explicit target:

```bash
python3 "$OAL_CLI" teams --target codex --problem "[problem]"
```

## Output schema
`TeamDispatchResult { status, findings[], actions[], evidence{} }`
