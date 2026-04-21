---
name: omg-secure-worktree-pipeline
description: "Secure worker execution with merge-writer authorization gates, lock-aware cleanup, and deterministic cancellation on write denial."
---

# OMG Secure Worktree Pipeline

- Channel: `public`
- Execution modes: `automation, ephemeral_worktree, local_supervisor`
- MCP servers: `omg-control`
- Evidence outputs: `.omg/evidence/subagents/*.json, .omg/evidence/merge-writer-*.json, .omg/state/exec-kernel/*.json, .omg/state/merge-writer.lock`
