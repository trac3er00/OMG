---
name: omg-secure-worktree-pipeline
description: "Ephemeral worktree execution and supervisor-safe worker dispatch for production jobs."
---

# OMG Secure Worktree Pipeline

- Channel: `enterprise`
- Execution modes: `automation, ephemeral_worktree, local_supervisor`
- MCP servers: `omg-control`
- Evidence outputs: `.omg/evidence/subagents/*.json, .omg/evidence/merge-writer-*.json, .omg/state/exec-kernel/*.json, .omg/state/merge-writer.lock`
