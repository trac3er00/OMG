---
description: "Stop Ralph autonomous loop — deactivates the state file."
allowed-tools: Read, Write, Edit, Bash
argument-hint: ""
---

# /OMG:ralph-stop — Stop Ralph Autonomous Loop

## Purpose
Stops an active Ralph loop by deactivating the state file.

## Usage
```
/OMG:ralph-stop
```

## How it Works
1. Read `.omg/state/ralph-loop.json`
2. Set `active: false` in the state file (preserve iteration count for review)
3. Report: "Ralph loop stopped after N iterations. Gomg was: [original_prompt]"

## If No Active Loop
Report: "No active Ralph loop found. Nothing to stop."
