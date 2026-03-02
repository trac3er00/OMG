---
description: "Start Ralph autonomous loop — continues working until all tasks complete or max iterations reached."
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
argument-hint: "[goal description]"
---

# /OAL:ralph-start — Start Ralph Autonomous Loop

## Purpose
Starts a Ralph loop that autonomously continues working until all tasks in the goal are complete or max iterations reached.

## Usage
```
/OAL:ralph-start [goal description]
```

## How it Works
1. Ask the user for a goal description if not provided
2. Create `.oal/state/ralph-loop.json` with:
   - `active: true`
   - `iteration: 0`
   - `max_iterations: 50`
   - `original_prompt: [goal]`
   - `started_at: [ISO8601 timestamp]`
   - `checklist_path: ".oal/state/_checklist.md"` (if exists)
3. Confirm: "Ralph loop started. Will continue working on: [goal]"

## State File Format
```json
{
  "active": true,
  "iteration": 0,
  "max_iterations": 50,
  "original_prompt": "fix all failing tests",
  "started_at": "2026-02-28T10:00:00Z",
  "checklist_path": ".oal/state/_checklist.md"
}
```

## Stop Condition
- Reaches max_iterations (50 by default)
- User runs `/OAL:ralph-stop`
- User deletes `.oal/state/ralph-loop.json`
