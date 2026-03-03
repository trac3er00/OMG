---
description: "Create or manage OAL state branches for experimental workflows."
allowed-tools: Read, Write, Edit, Bash
argument-hint: "--name <branch-name> [--from <snapshot_id>]"
---

# /OAL:branch — Branch OAL State

Create a named branch of the current OAL state for experimentation or parallel exploration.

## Important

Branching is **OAL state only** — it captures and restores `.oal/state/` directory contents. It does **not** fork the conversation, context window, or Claude session. Think of it as a checkpoint you can name and switch between.

## Usage

```
/OAL:branch --name "experiment"
/OAL:branch --name "refactor-v2" --from 20260302_143000_baseline
```

## What It Does

1. Creates a snapshot of the current `.oal/state/` directory (or restores a specified snapshot)
2. Writes branch metadata to `.oal/state/branches/<name>.json`
3. Updates `.oal/state/current_branch.json` to track the active branch

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

Branching is gated behind `OAL_BRANCHING_ENABLED` (default: `False`).

Enable via environment variable:
```bash
export OAL_BRANCHING_ENABLED=true
```

Or in `settings.json`:
```json
{
  "_oal": {
    "features": {
      "BRANCHING": true
    }
  }
}
```

## Example Workflow

```
# 1. Create a baseline branch
/OAL:branch --name "baseline"

# 2. Do some experimental work...
# 3. Create experiment branch to save progress
/OAL:branch --name "experiment-auth"

# 4. Switch back to baseline if experiment didn't work
python3 tools/session_snapshot.py switch baseline
```
