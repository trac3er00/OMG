---
description: "Merge OMG state branches together with conflict detection."
allowed-tools: Read, Write, Edit, Bash(bun:*)
argument-hint: "--from <source-branch> [--into <target-branch>] [--preview]"
---

# /OMG:session-merge

Merge one OMG state branch into another with preview support.

## Examples

```bash
bun tools/session_snapshot.ts merge-preview experiment --into main
bun tools/session_snapshot.ts merge experiment --into main
bun tools/session_snapshot.ts merge experiment
bun tools/session_snapshot.ts branches
```
