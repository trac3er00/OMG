---
description: "Manage OMG state branches — branch, fork, merge, switch, and list."
allowed-tools: Read, Write, Edit, Bash
argument-hint: "branch|fork|merge|switch|list [options]"
---

# /OMG:session — OMG State Branch Management

Unified session state management. Subsumes `/OMG:session-branch`, `/OMG:session-fork`, and `/OMG:session-merge`.

**Scope: This command operates on `.omg/state/` only. It does NOT modify git history, workspace files, or conversation history.**

## Sub-Commands

### `branch` — Create Named Branch

Save current `.omg/state/` as a named branch.

```
/OMG:session branch --name "experiment"
/OMG:session branch --name "refactor-v2" --from 20260302_143000_baseline
```

### `fork` — Fork from Checkpoint

Create a new branch from a specific snapshot checkpoint.

```
/OMG:session fork --from 20260302_143000_baseline --name "alt-approach"
```

### `merge` — Merge Branches

Merge one branch into another with conflict detection.

```
/OMG:session merge --from "experiment"
/OMG:session merge --from "experiment" --into "main"
/OMG:session merge --from "experiment" --preview
```

Conflict detection: aborts on `value_conflict` (same key, different values). Use `--preview` to check before applying.

### `switch` — Switch Active Branch

```
python3 tools/session_snapshot.py switch <branch-name>
```

### `list` — List Branches & Snapshots

```
python3 tools/session_snapshot.py status      # Current branch + snapshot count
python3 tools/session_snapshot.py branches    # All branches
python3 tools/session_snapshot.py list        # All snapshots
```

## CLI Commands

```bash
python3 tools/session_snapshot.py branch <name> [--from <snapshot_id>]
python3 tools/session_snapshot.py fork --from <snapshot_id> --name <name>
python3 tools/session_snapshot.py merge <source> [--into <target>]
python3 tools/session_snapshot.py merge-preview <source> [--into <target>]
python3 tools/session_snapshot.py switch <branch>
python3 tools/session_snapshot.py status
python3 tools/session_snapshot.py branches
```

## Feature Flags

| Feature | Flag | Default |
|---------|------|---------|
| Branch/Fork | `OMG_BRANCHING_ENABLED` | `False` |
| Merge | `OMG_MERGE_ENABLED` | `False` |

## Example Workflow

```
/OMG:session branch --name "baseline"
# Do experimental work...
/OMG:session branch --name "experiment-auth"
# Preview merge
/OMG:session merge --from "experiment-auth" --preview
# Apply merge
/OMG:session merge --from "experiment-auth" --into "baseline"
```
