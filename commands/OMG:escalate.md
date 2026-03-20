---
description: Auto-route to Codex, Gemini, or Kimi using OMG standalone internal router.
allowed-tools: Read, Grep, Glob, AskUserQuestion, Bash(git:*), Bash(rg:*), Bash(find:*), Bash(cat:*), Bash(python3:*)
argument-hint: "[codex|gemini|kimi|auto] 'task description'"
---

# /OMG:escalate — Standalone Smart Escalation

## Canonical Providers

When invoked without an explicit target, use `AskUserQuestion`:
- question: "Which model should handle this escalation?"
- header: "Target"
- options:
  - label: "codex", description: "Backend logic, security, debugging, algorithms, performance"
  - label: "gemini", description: "UI/UX, visual design, accessibility, responsive layouts"
  - label: "kimi", description: "Long-context analysis, document processing, research synthesis"
  - label: "auto (Recommended)", description: "Let router decide based on problem keywords"

Wait for user selection before dispatching.

## Auto-Routing
If `auto` selected or target matches keywords:
- backend/security/debug/performance → `codex`
- ui/ux/layout/responsive → `gemini`
- research/document/long-context → `kimi`
- full-stack/architecture/review-all → `ccg`

## Dispatch Strategy
The router selects the best dispatch method based on environment:

| Environment | Strategy | How It Works |
|-------------|----------|--------------|
| Claude Code | `agent` | Native Agent tool for parallel sub-agent dispatch |
| tmux available | `tmux` | Dedicated tmux sessions per provider |
| Fallback | `subprocess` | Direct subprocess calls (sequential) |

Detection order: Agent tool presence → `tmux` binary → subprocess fallback.
The active strategy is reported in `evidence.dispatch_strategy`.

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
python3 "$OMG_CLI" teams --target kimi --problem "[problem]"
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
