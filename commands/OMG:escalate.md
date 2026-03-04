---
description: Auto-route to Codex or Gemini using OMG standalone internal router.
allowed-tools: Read, Grep, Glob, Bash(git:*), Bash(rg:*), Bash(find:*), Bash(cat:*), Bash(python3:*)
argument-hint: "[codex|gemini|ccg|auto] 'task description' or just 'problem'"
---

# /OMG:escalate — Standalone Smart Escalation

## Auto-Routing
If no model specified:
- backend/security/debug/performance → `codex`
- ui/ux/layout/responsive → `gemini`
- full-stack/architecture/review-all → `ccg`

## Context package
Build from OMG canonical state:
- `.omg/state/profile.yaml`
- `.omg/state/ledger/failure-tracker.json`
- relevant files (`git diff --name-only`)

## Runtime entrypoint
Use the portable runtime installed by `OMG-setup.sh` (`~/.claude/omg-runtime/scripts/omg.py`).

```bash
OMG_CLI="${OMG_CLI_PATH:-$HOME/.claude/omg-runtime/scripts/omg.py}"
if [ ! -f "$OMG_CLI" ] && [ -f "scripts/omg.py" ]; then OMG_CLI="scripts/omg.py"; fi
```

## Execute
```bash
python3 "$OMG_CLI" teams --target auto --problem "[problem]"
```

Explicit target:
```bash
python3 "$OMG_CLI" teams --target codex --problem "[problem]"
python3 "$OMG_CLI" teams --target gemini --problem "[problem]"
python3 "$OMG_CLI" ccg --problem "[problem]"
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

No external legacy plugin is required.
