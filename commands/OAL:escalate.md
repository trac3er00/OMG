---
description: Auto-route to Codex or Gemini using OAL standalone internal router.
allowed-tools: Read, Grep, Glob, Bash(git:*), Bash(rg:*), Bash(find:*), Bash(cat:*), Bash(python3:*)
argument-hint: "[codex|gemini|ccg|auto] 'task description' or just 'problem'"
---

# /OAL:escalate — Standalone Smart Escalation

## Auto-Routing
If no model specified:
- backend/security/debug/performance → `codex`
- ui/ux/layout/responsive → `gemini`
- full-stack/architecture/review-all → `ccg`

## Context package
Build from OAL canonical state:
- `.oal/state/profile.yaml`
- `.oal/state/ledger/failure-tracker.json`
- relevant files (`git diff --name-only`)

## Runtime entrypoint
Use the portable runtime installed by `OAL-setup.sh` (`~/.claude/oal-runtime/scripts/oal.py`).

```bash
OAL_CLI="${OAL_CLI_PATH:-$HOME/.claude/oal-runtime/scripts/oal.py}"
if [ ! -f "$OAL_CLI" ] && [ -f "scripts/oal.py" ]; then OAL_CLI="scripts/oal.py"; fi
```

## Execute
```bash
python3 "$OAL_CLI" teams --target auto --problem "[problem]"
```

Explicit target:
```bash
python3 "$OAL_CLI" teams --target codex --problem "[problem]"
python3 "$OAL_CLI" teams --target gemini --problem "[problem]"
python3 "$OAL_CLI" ccg --problem "[problem]"
```

## Output
Returns `TeamDispatchResult` with:
- findings
- action plan
- evidence metadata

Evidence now includes provider health details (`cli_health`) with:
- binary availability
- auth readiness (`auth status` probe)
- `live_connection` boolean per provider

No external OMC plugin is required.
