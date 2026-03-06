---
description: "Fork OMG state from a specific snapshot checkpoint."
allowed-tools: Read, Write, Edit, Bash(bun:*)
argument-hint: "--from <snapshot_id> --name <fork-name>"
---

# /OMG:session-fork

Forking is OMG state only. It restores `.omg/state/` snapshot data and starts a new named branch from that checkpoint.

## Example

```bash
bun tools/session_snapshot.ts list
/OMG:session-fork --from 20260302_100000_pre-refactor --name "approach-b"
```
