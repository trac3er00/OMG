---
description: OMG internal staged team routing (standalone). /OMG:team canonical, /OMG:teams compatibility alias.
allowed-tools: Read, Grep, Glob, AskUserQuestion, Bash(git:*), Bash(rg:*), Bash(find:*), Bash(cat:*), Bash(python3:*)
argument-hint: "[codex|gemini|kimi|auto] 'problem statement'"
---

# /OMG:teams — Standalone Internal Router

Canonical alias: `/OMG:team`
Compatibility alias: `/OMG:teams`

Use OMG's internal router for multi-model dispatch.

## Canonical Providers

When invoked without an explicit target, use `AskUserQuestion`:
- question: "Which dispatch target should handle this?"
- header: "Target"
- options:
  - label: "auto (Recommended)", description: "Let router decide based on problem keywords"
  - label: "codex", description: "Backend logic, security, debugging, algorithms"
  - label: "gemini", description: "UI/UX, visual design, accessibility"
  - label: "kimi", description: "Long-context analysis, document processing"
- (ccg available via Other)

Wait for user selection before dispatching. `claude` is always the host orchestrator (not selectable).

## Input contract
- target: `auto|codex|gemini|kimi|ccg`
- problem: clear issue statement
- context: optional constraints
- files: optional focus paths
- expected_outcome: optional acceptance target

## Execution
Use internal CLI router (canonical):

```bash
OMG_CLI="${OMG_CLI_PATH:-$HOME/.claude/omg-runtime/scripts/omg.py}"
if [ ! -f "$OMG_CLI" ] && [ -f "scripts/omg.py" ]; then OMG_CLI="scripts/omg.py"; fi
python3 "$OMG_CLI" team --target auto --problem "[problem]"
```

Compatibility alias (legacy):

```bash
python3 "$OMG_CLI" teams --target auto --problem "[problem]"
```

For explicit target:

```bash
python3 "$OMG_CLI" team --target codex --problem "[problem]"
```

## Staged flow
- `team-plan`: resolve context packet and clarification/council gate before dispatch
- `team-exec`: launch workers only when context is resolved
- `team-verify`: run verification and critic synthesis
- `team-fix`: surface blockers/next actions for follow-up iteration

## Output schema
`TeamDispatchResult { status, findings[], actions[], evidence{} }`

## Dispatch Strategy Reporting
The router auto-detects the best dispatch method and reports it:

| Strategy | Detection | Behavior |
|----------|-----------|----------|
| `agent` | Claude Code Agent tool available | Native parallel sub-agents |
| `tmux` | `tmux` binary in PATH | Parallel tmux sessions |
| `subprocess` | Fallback | Sequential subprocess calls |

The active strategy appears in the output:
```
evidence: {
  dispatch_strategy: "agent",  // or "tmux" or "subprocess"
  cli_health: { ... }
}
```

## Full-power sub-agent protocol
- For non-trivial tasks, launch multiple sub-agents in parallel (`run_in_background=true`) for independent tracks.
- Collect all task outputs before responding (`background_output` per task id).
- Run a `sequential-thinking` merge step to produce one dependency-ordered execution plan.
