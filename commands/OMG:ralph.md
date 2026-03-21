---
description: "Ralph autonomous loop — start, stop, and status."
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
argument-hint: "start|stop|status [goal description]"
---

# /OMG:ralph — Autonomous Loop Control

Unified Ralph loop management. Subsumes `/OMG:ralph-start` and `/OMG:ralph-stop`.

## Sub-Commands

### `start [goal]` — Start Autonomous Loop

Starts a Ralph loop that autonomously works until all tasks complete or max iterations reached.

```
/OMG:ralph start fix all failing tests
/OMG:ralph start implement the payment module
```

1. Ask user for a goal if not provided
2. Create `.omg/state/ralph-loop.json` with `active: true`
3. Confirm: "Ralph loop started. Will continue working on: [goal]"

### `stop` — Stop Autonomous Loop

```
/OMG:ralph stop
```

1. Read `.omg/state/ralph-loop.json`
2. Set `active: false` (preserves iteration count)
3. Report: "Ralph loop stopped after N iterations. Goal was: [original_prompt]"

### `status` — Check Loop Status

```
/OMG:ralph status
```

Reports current loop state: active/inactive, iteration count, goal, started time.

## State File

`.omg/state/ralph-loop.json`:

```json
{
  "active": true,
  "iteration": 0,
  "max_iterations": 50,
  "original_prompt": "fix all failing tests",
  "started_at": "2026-02-28T10:00:00Z",
  "checklist_path": ".omg/state/_checklist.md"
}
```

## Stop Conditions

- Reaches `max_iterations` (50 default)
- User runs `/OMG:ralph stop`
- User deletes `.omg/state/ralph-loop.json`
