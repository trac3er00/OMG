---
description: "Fork OMG state from a specific snapshot checkpoint."
allowed-tools: Read, Write, Edit, Bash
argument-hint: "--from <snapshot_id> --name <fork-name>"
---

# /OMG:fork — Fork OMG State from Checkpoint

Create a new branch from a specific snapshot checkpoint. This is a convenience wrapper around `/OMG:branch` that always requires a source snapshot.

## Important

Forking is **OMG state only** — it restores a previous `.omg/state/` snapshot and creates a new named branch from it. It does **not** fork the conversation or create a parallel Claude session.

## Usage

```
/OMG:fork --from 20260302_143000_baseline --name "alt-approach"
```

## What It Does

1. Looks up the specified snapshot by ID
2. Restores that snapshot to `.omg/state/`
3. Creates a new branch with the given name pointing to that snapshot
4. Updates `.omg/state/current_branch.json`

## When to Use Fork vs Branch

| Action | Use Case |
|--------|----------|
| `/OMG:branch --name X` | Save current state as a named branch |
| `/OMG:fork --from S --name X` | Go back to snapshot S and start a new exploration path |

## Example

```
# List available snapshots to find a good fork point
python3 tools/session_snapshot.py list

# Fork from a previous checkpoint
/OMG:fork --from 20260302_100000_pre-refactor --name "approach-b"

# Continue working from that earlier state...
```

## Feature Flag

Forking shares the `OMG_BRANCHING_ENABLED` feature flag with `/OMG:branch` (default: `False`).

```bash
export OMG_BRANCHING_ENABLED=true
```
