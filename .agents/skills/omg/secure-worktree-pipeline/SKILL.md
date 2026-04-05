---
name: omg-secure-worktree-pipeline
description: "Secure worker pipeline with merge-writer authorization gates, lock-aware cleanup, and fail-fast cancellation when protected write authorization fails."
---

# OMG Secure Worktree Pipeline

Dispatch workers through `runtime/subagent_dispatcher.py:submit_job` and gate writes with `_enforce_merge_writer_gate`. On authorization failure from `runtime/merge_writer.py:MergeWriter.require_authorization`, cancel job, clean worktree, and emit merge-writer evidence.

- Channel: `enterprise`
- Execution modes: `automation, ephemeral_worktree, local_supervisor`
- MCP servers: `omg-control`
- Evidence outputs: `.omg/evidence/subagents/*.json, .omg/evidence/merge-writer-*.json, .omg/state/exec-kernel/*.json, .omg/state/merge-writer.lock`
