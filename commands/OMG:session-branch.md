---
description: "Create or switch OMG state branches."
allowed-tools: Read, Write, Edit, Bash(bun:*)
argument-hint: "--name <branch-name> [--from <snapshot_id>]"
---

# /OMG:session-branch

OMG state branches are stored under `.omg/state/session-snapshots/`.

## Examples

```bash
bun tools/session_snapshot.ts branches
bun tools/session_snapshot.ts switch experiment
bun tools/session_snapshot.ts branch my-branch --from 20260302_143000_baseline
bun tools/session_snapshot.ts switch baseline
```
