---
description: "Merge OAL state branches together with conflict detection."
allowed-tools: Read, Write, Edit, Bash
argument-hint: "--from <source-branch> [--into <target-branch>] [--preview]"
---

# /OAL:merge — Merge OAL State Branches

Merge one OAL state branch into another with automatic conflict detection.

## Important

Merging is **OAL state only** — it merges branch metadata (`.oal/state/branches/<name>.json`). It does **not** merge conversations, context windows, or file system state. Think of it as combining the tracked state from two named branches.

## Usage

```
/OAL:merge --from "experiment"
/OAL:merge --from "experiment" --into "main"
/OAL:merge --from "experiment" --preview
```

## What It Does

1. Loads the source and target branch metadata as flat JSON dicts
2. Detects conflicts (keys present in both branches with different values)
3. If `--preview`: returns conflict report without applying changes
4. If no conflicts: applies source changes on top of target (last-write-wins)
5. Marks the source branch as `status: "merged"` in its metadata file
6. Updates `.oal/state/current_branch.json` to the target branch

## Conflict Detection

A **value_conflict** occurs when both branches have the same key but different values. When conflicts are found, the merge is **aborted** — you must resolve conflicts manually before merging.

Conflict report format:

```json
{
  "key": "snapshot_id",
  "source_value": "20260302_150000_experiment",
  "target_value": "20260302_140000_main",
  "conflict_type": "value_conflict"
}
```

## Preview Mode

Use `--preview` to see what a merge would do without applying changes:

```
python3 tools/session_snapshot.py merge-preview experiment --into main
```

Returns:

```json
{
  "source": "experiment",
  "target": "main",
  "conflicts": [],
  "changes": 2,
  "preview": true
}
```

## CLI Commands

```
# Merge source into target
python3 tools/session_snapshot.py merge experiment --into main

# Preview merge without applying
python3 tools/session_snapshot.py merge-preview experiment --into main

# Merge into default target (main)
python3 tools/session_snapshot.py merge experiment
```

## Feature Flag

Merging is gated behind `OAL_MERGE_ENABLED` (default: `False`).

Enable via environment variable:
```bash
export OAL_MERGE_ENABLED=true
```

Or in `settings.json`:
```json
{
  "_oal": {
    "features": {
      "MERGE": true
    }
  }
}
```

## Merge Behavior

| Scenario | Result |
|----------|--------|
| No conflicts | Source state overlaid on target (last-write-wins) |
| Conflicts found | Merge aborted, conflicts returned |
| Source branch missing | Error returned |
| Target branch missing | Error returned |
| Feature flag disabled | `{"skipped": true}` |

## After Merge

- The **target** branch is updated with merged state
- The **source** branch status changes to `"merged"` (not deleted)
- `current_branch.json` is updated to the target branch
- Source branch remains accessible for reference

## Example Workflow

```
# 1. Create branches
/OAL:branch --name "main"
/OAL:branch --name "experiment"

# 2. Do experimental work on "experiment" branch...

# 3. Preview the merge
/OAL:merge --from "experiment" --preview

# 4. If no conflicts, apply the merge
/OAL:merge --from "experiment" --into "main"

# 5. Verify merge
python3 tools/session_snapshot.py branches
```
