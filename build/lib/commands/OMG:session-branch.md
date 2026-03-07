---
description: "Create or manage OMG state branches for experimental workflows."
allowed-tools: Read, Write, Edit, Bash
argument-hint: "--name <branch-name> [--from <snapshot_id>]"
---

# /OMG:session-branch — Branch OMG State

Create a named branch of the current OMG state for experimentation or parallel exploration.

## Important

Branching is **OMG state only** — it captures and restores `.omg/state/` directory contents. It does **not** fork the conversation, context window, or Claude session. Think of it as a checkpoint you can name and switch between.

## Usage

```
/OMG:session-branch --name "experiment"
/OMG:session-branch --name "refactor-v2" --from 20260302_143000_baseline
```

## What It Does

1. Creates a snapshot of the current `.omg/state/` directory (or restores a specified snapshot)
2. Writes branch metadata to `.omg/state/branches/<name>.json`
3. Updates `.omg/state/current_branch.json` to track the active branch

## Branch Metadata

Each branch stores:

| Field | Description |
|-------|-------------|
| `name` | Branch name |
| `snapshot_id` | Associated snapshot ID |
| `created_at` | ISO timestamp of creation |
| `parent_branch` | Branch that was active when this branch was created |
| `status` | Branch status (`active`) |

## Managing Branches

```
# List all branches
python3 tools/session_snapshot.py branches

# Switch to a branch (restores its snapshot)
python3 tools/session_snapshot.py switch experiment

# Create branch from specific snapshot
python3 tools/session_snapshot.py branch my-branch --from 20260302_143000_baseline
```

## Feature Flag

Branching is gated behind `OMG_BRANCHING_ENABLED` (default: `False`).

Enable via environment variable:
```bash
export OMG_BRANCHING_ENABLED=true
```

Or in `settings.json`:
```json
{
  "_omg": {
    "features": {
      "BRANCHING": true
    }
  }
}
```

## Example Workflow

```
# 1. Create a baseline branch
/OMG:session-branch --name "baseline"

# 2. Do some experimental work...
# 3. Create experiment branch to save progress
/OMG:session-branch --name "experiment-auth"

# 4. Switch back to baseline if experiment didn't work
python3 tools/session_snapshot.py switch baseline
```
