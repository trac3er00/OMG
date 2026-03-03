---
description: "Fork OAL state from a specific snapshot checkpoint."
allowed-tools: Read, Write, Edit, Bash
argument-hint: "--from <snapshot_id> --name <fork-name>"
---

# /OAL:fork — Fork OAL State from Checkpoint

Create a new branch from a specific snapshot checkpoint. This is a convenience wrapper around `/OAL:branch` that always requires a source snapshot.

## Important

Forking is **OAL state only** — it restores a previous `.oal/state/` snapshot and creates a new named branch from it. It does **not** fork the conversation or create a parallel Claude session.

## Usage

```
/OAL:fork --from 20260302_143000_baseline --name "alt-approach"
```

## What It Does

1. Looks up the specified snapshot by ID
2. Restores that snapshot to `.oal/state/`
3. Creates a new branch with the given name pointing to that snapshot
4. Updates `.oal/state/current_branch.json`

## When to Use Fork vs Branch

| Action | Use Case |
|--------|----------|
| `/OAL:branch --name X` | Save current state as a named branch |
| `/OAL:fork --from S --name X` | Go back to snapshot S and start a new exploration path |

## Example

```
# List available snapshots to find a good fork point
python3 tools/session_snapshot.py list

# Fork from a previous checkpoint
/OAL:fork --from 20260302_100000_pre-refactor --name "approach-b"

# Continue working from that earlier state...
```

## Feature Flag

Forking shares the `OAL_BRANCHING_ENABLED` feature flag with `/OAL:branch` (default: `False`).

```bash
export OAL_BRANCHING_ENABLED=true
```
